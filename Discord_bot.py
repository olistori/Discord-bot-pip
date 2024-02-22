import discord
from discord.ext import commands
from discord import Intents
from discord import FFmpegPCMAudio
import youtube_dl
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
import asyncio
from config import DISCORD_TOKEN, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, YOUTUBE_API_KEY

# Define intents
intents = discord.Intents.all()
intents.messages = True  # Enable message content intent
intents.typing = False
intents.presences = False
intents.message_content = True
intents.voice_states = True

# Setup bot
bot = commands.Bot(command_prefix='!', intents=intents)

# Connect to Spotify
spotify = spotipy.Spotify(
    client_credentials_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID, 
        client_secret=SPOTIFY_CLIENT_SECRET
    )
)

ffmpeg_options = {
    'options': '-vn',  # Disable video
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'  # Reconnect options
}

# Create FFmpegPCMAudio instance with options
audio_source = FFmpegPCMAudio('audio_file.mp3', **ffmpeg_options)

# Global variable to store the queued songs
queued_songs = []
voice_client = ""

# Function to search YouTube for videos
async def search_youtube(query):
    url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&part=snippet&type=video&q={query}"
    response = requests.get(url)
    data = response.json()
    videos = []
    for idx, item in enumerate(data['items'], start=1):
        videos.append({
            'title': item['snippet']['title'],
            'url': f"https://www.youtube.com/watch?v={item['id']['videoId']}"
        })
    return videos


# Function to play a Spotify track
async def play_spotify(ctx, track_id):
    track = spotify.track(track_id)
    if 'preview_url' in track and track['preview_url'] is not None:
        await play_video(ctx, track['preview_url'])
    else:
        await ctx.send("This track does not have a preview available.")

# Function to play the next song in the queue
async def play_next(ctx):
    if not queued_songs:
        await ctx.send("The queue is empty.")
        return

    # Get the next song from the queue
    next_song = queued_songs.pop(0)

    # Join voice channel if not already in one
    if ctx.voice_client is None or not ctx.voice_client.is_connected():
        await join(ctx)

    # Check if the next song is a YouTube URL or a Spotify track ID
    if "youtube.com" in next_song or "youtu.be" in next_song:
        await play_video(ctx, next_song)
    else:
        await play_spotify(ctx, next_song)

@bot.command()
async def join(ctx):
    # Check if the bot is already connected to a voice channel
    if ctx.voice_client and ctx.voice_client.is_connected():
        await ctx.voice_client.disconnect()

    # Check if the author of the command is in a voice channel
    if ctx.author.voice is None:
        await ctx.send("You need to be in a voice channel to use this command.")
        return

    # Join the voice channel of the author of the command
    if ctx.voice_client is None:
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()
        return voice_client

    ctx.voice_client.source = discord.FFmpegPCMAudio('audio_file.mp3', **ffmpeg_options)
    

# Function to play a video
async def play_video(ctx, video_url):
    voice_client = await join(ctx)
    voice_client.play(discord.FFmpegPCMAudio(video_url))


# Command to leave voice channel
@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    else:
        await ctx.send("I'm not connected to a voice channel.")

# Command to stop playback and clear queue
@bot.command()
async def stop(ctx):
    queued_songs.clear()
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    else:
        await ctx.send("I'm not connected to a voice channel.")

@bot.command()
async def play(ctx, *, query):
    # Check if the bot is already connected to a voice channel
    if ctx.voice_client is None:
        await join(ctx)

    # Check if the provided query is a YouTube URL
    if "youtube.com" in query or "youtu.be" in query:
        queued_songs.append(query)
        await ctx.send("Song added to queue.")
        # If the bot is not currently playing, play the next song
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        return

    # Check if the provided query is a Spotify track URL
    if "open.spotify.com" in query:
        # Extract the track ID from the URL
        track_id = query.split("/")[-1]
        queued_songs.append(track_id)
        await ctx.send("Song added to queue.")
        # If the bot is not currently playing, play the next song
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        return

    # Search YouTube if it's not a URL or Spotify track
    videos = await search_youtube(query)
    if not videos:
        await ctx.send("No videos found.")
        return

    # If there are no queued songs, play the first one immediately
    if not queued_songs:
        await play_video(ctx, videos[0]['url'])
    else:
        # Add the first search result to the queue
        queued_songs.append(videos[0]['url'])
        await ctx.send("Song added to queue.")

# Command to skip the current song and play the next one in the queue
@bot.command()
async def skip(ctx):
    await play_next(ctx)






bot.run(DISCORD_TOKEN)
