import discord
from discord.ext import commands
from discord import Intents
from discord import FFmpegPCMAudio
import yt_dlp as youtube_dl
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

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'noplaylist': True  # Prevent downloading playlists
}

ffmpeg_options = {
    'options': '-vn',  # Disable video
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',  # Reconnect options
    'stderr': asyncio.subprocess.PIPE  # Capture stderr
}

# Global variable to store the queued songs
queued_songs = []
voice_client = None
currently_playing = ""

# Function to search YouTube for queued_songs
async def search_youtube(ctx, query):
    global queued_songs
    url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&part=snippet&type=video&q={query}&maxResults=5"
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
    except requests.RequestException as e:
        await ctx.send(f"Error occurred while searching YouTube: {str(e)}")
        return

    # Check if the response contains any items
    if 'items' not in data:
        await ctx.send("No search results found.")
        return

    # Display the search results
    result_str = "Search results:\n"
    for idx, item in enumerate(data['items'], start=1):
        result_str += f"{idx}. {item['snippet']['title']}\n"
    await ctx.send(result_str)

    # Prompt the user to select a number from 1 to 5
    await ctx.send("Please select a number from 1 to 5:")
    
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.isdigit() and 1 <= int(msg.content) <= 5
    
    try:
        msg = await bot.wait_for('message', timeout=30.0, check=check)
        selected_number = int(msg.content)
    except asyncio.TimeoutError:
        await ctx.send("You took too long to respond.")
        return
    except ValueError:
        await ctx.send("Invalid input. Please enter a number from 1 to 5.")
        return

    # Append the selected YouTube URL to the queued_songs list
    selected_item = data['items'][selected_number - 1]
    print(selected_item)
    track = []
    track.append(f'https://www.youtube.com/watch?v={selected_item['id']['videoId']}')
    track.append(selected_item['snippet']['title'])
    queued_songs.append(track)

# Function to play the next song in the queue
async def play_next(ctx):
    global queued_songs
    global currently_playing
    if not queued_songs:
        await ctx.send("The queue is empty.")
        if ctx.voice_client.is_connected():
            await leave(ctx)
        return

    # Get the next song from the queue
    next_song = queued_songs.pop(0)
    currently_playing = next_song[1]

    # Join voice channel if not already in one
    if ctx.voice_client is None or not ctx.voice_client.is_connected():
        await join(ctx)


    # Check if the next song is a YouTube URL or a Spotify track ID
    if "youtube.com" in next_song[0] or "youtu.be" in next_song[0]:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(next_song[0], download=False)
            # Filter formats to get audio-only formats
            audio_formats = [f for f in info['formats'] if 'acodec' in f and f['acodec'] != 'none']
            # Sort the formats by bitrate
            sorted_audio_formats = sorted(audio_formats, key=lambda x: int(x.get('abr', 0) or 0), reverse=True)
            # Get the URL of the highest bitrate audio stream
            audio_url = sorted_audio_formats[0]['url'] if sorted_audio_formats else None

            await ctx.send(f'Now playing: {next_song[1]}')

        await play_video(ctx, audio_url)
    else:
        await ctx.send(f'Now playing a preview of: {next_song[1]}')
        await play_spotify(ctx, next_song[0])

async def play_spotify(ctx, track_id):
    await play_video(ctx, track_id)
 

@bot.command()
async def join(ctx):
    # Check if the bot is already connected to a voice channel
    #if ctx.voice_client and ctx.voice_client.is_connected():
    #   await ctx.voice_client.disconnect()

    # Check if the author of the command is in a voice channel
    if ctx.author.voice is None:
        await ctx.send("You need to be in a voice channel to use this command.")
        return

    # Join the voice channel of the author of the command
    if ctx.voice_client is None:
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()
        return voice_client
    

# Function to play a video
async def play_video(ctx, video_url):
    voice_client = ctx.guild.voice_client

    def after_playing(e):
        print('done', e)
        asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

    voice_client.play(discord.FFmpegPCMAudio(video_url, **ffmpeg_options), after=after_playing)



@bot.command()
async def play(ctx, *, query):
    global queued_songs
    # Check if the bot is already connected to a voice channel
    if ctx.voice_client is None:
        await join(ctx)

    voice_client = ctx.voice_client
    # Check if the provided query is a YouTube URL
    if "youtube.com" in query or "youtu.be" in query:
        if "&list=" in query:  # Check if it's a playlist
            await ctx.send(f'This is a YouTube playlist. It might contain alot of songs. Do you want to add them to the queue (yes/no)')

            def check_response(msg):
                return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.lower() in ['yes', 'no']

            try:
                response_msg = await bot.wait_for('message', timeout=30.0, check=check_response)
                if response_msg.content.lower() == 'yes':  
                    await ctx.send("Whats the max songs you want to add, Please select a number from 2 to 50:")
    
                    def check(msg):
                        return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.isdigit() and 2 <= int(msg.content) <= 50

                    try:
                        msg = await bot.wait_for('message', timeout=30.0, check=check)
                        await extract_playlist_items(query, ctx, voice_client, msg.content)
                    except asyncio.TimeoutError:
                        await ctx.send("You took too long to respond. Only first song from the playlist added to the queue.")
                    except ValueError:
                        await ctx.send("Invalid input. Please enter a number from 2 to 50. Only first song from the playlist added to the queue")
                else:
                    # Add only the first song
                    await ctx.send("Only first song from the playlist added to the queue.")
            except asyncio.TimeoutError:
                await ctx.send("You took too long to respond. Adding only the first song from the playlist to the queue.")

            return

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(query, download=False)
            video_title = info_dict.get('title', None)
        track = []
        track.append(query)
        track.append(video_title)
        queued_songs.append(track)

        if voice_client.is_playing():
            await ctx.send("Song added to queue.")
        # If the bot is not currently playing, play the next song
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        return

    # Check if the provided query is a Spotify track URL
    if "open.spotify.com" in query:
        track = spotify.track(query)
        if 'preview_url' in track and track['preview_url'] is not None:
            await ctx.send("This track is only a preview. Do you want to search the full song on Youtube? (yes/no)")
            
            def check_response(msg):
                return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.lower() in ['yes', 'no']
            
            try:
                response_msg = await bot.wait_for('message', timeout=30.0, check=check_response)
                if response_msg.content.lower() == 'yes':
                    # Play the full song
                    await play(ctx, query=track['name'])
                    return
                else:
                    await ctx.send(f'Okay, a preview of {track['name']} will be played.')
                    # Play the preview
                    trackls = []
                    trackls.append(track['preview_url'])
                    await ctx.send(f'{track['name']} - {track['artists'][0]['name']}')
                    trackls.append(f'{track['name']} - {track['artists'][0]['name']}')
                    queued_songs.append(trackls)
            except asyncio.TimeoutError:
                await ctx.send("You took too long to respond. Playing the preview.")
                # Play the preview by default if no response is received
                trackls = []
                trackls.append(track['preview_url'])
                trackls.append(f'{track['name']} - {track['artists']}')
                queued_songs.append(trackls)
        else:
            await play(ctx, query=track['name'])
            return

        if voice_client.is_playing():
            await ctx.send("Song added to queue.")
        # If the bot is not currently playing, play the next song
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        return

    # Search YouTube if it's not a URL or Spotify track
    await search_youtube(ctx, query)
    if not queued_songs:
        await ctx.send("No queued songs found.")
        if ctx.voice_client.is_connected():
            await leave(ctx)
        return

    # If there are no queued songs, play the first one immediately
    if not voice_client.is_playing():
        await play_next(ctx)
    else:
        await ctx.send("Song added to queue.")

async def extract_playlist_items(playlist_url, ctx, voice_client, max_dl):
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(playlist_url, download=False)
        video_title = info_dict.get('title', None)
    track = []
    track.append(playlist_url)
    track.append(video_title)
    queued_songs.append(track)

    if not ctx.voice_client.is_playing():
            await play_next(ctx)
    playlist_items = []
    try:
        await ctx.send(f'This is a YouTube playlist. Downloading information needed for the rest of the songs.')
        ydl_opts_playlist = {
            #'quiet': True,
            'skip_download': True,
            'force_generic_extractor': True,
            'dump_single_json': True,  # Dump info for each video in JSON format
            'playlist_items': f'2-{max_dl}'  # Set x to the maximum number of songs you want to fetch
        }
        ydl = youtube_dl.YoutubeDL(ydl_opts_playlist)
        info = ydl.extract_info(playlist_url, download=False)
        if 'entries' in info:
            for entry in info['entries']:
                if entry:
                    track = []
                    track.append(f"https://www.youtube.com/watch?v={entry['id']}")
                    track.append(entry['title'])
                    queued_songs.append(track)

            await ctx.send(f"{len(info['entries'])} songs from the playlist have been added to the queue.")

    except Exception as e:
        print(f"Error extracting playlist items: {e}")

# Command to skip the current song and play the next one in the queue
@bot.command()
async def skip(ctx):
    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_playing():
        await ctx.send("There is no audio playing to skip.")
        return

    # Stop the currently playing audio
    voice_client.stop()
    await ctx.send("Skipping to next song.")

@bot.command()
async def next(ctx):
    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_playing():
        await ctx.send("There is no audio playing to skip.")
        return

    # Stop the currently playing audio
    voice_client.stop()
    await ctx.send("Skipping to next song.")


# Command to stop playback and clear queue
@bot.command()
async def stop(ctx):
    global queued_songs
    queued_songs.clear()
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    else:
        await ctx.send("I'm not connected to a voice channel.")

# Command to leave voice channel
@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    else:
        await ctx.send("I'm not connected to a voice channel.")

@bot.command()
async def queue(ctx):
    if queued_songs:
        name_queue = []
        count = 1
        await ctx.send(f'Currently Playing: {currently_playing}')
        await ctx.send(f'The queue contains {len(queued_songs)}')

        for song in queued_songs:
            name_queue.append(f'{count}. {song[1]}')
            count = count+1

        list_as_string = '\n'.join(name_queue)
        await ctx.send(list_as_string)
    else:
        await ctx.send("The queue is empty!")

@bot.command()
async def songs(ctx):
    if queued_songs:
        name_queue = []
        count = 1
        await ctx.send(f'Currently Playing: {currently_playing}')
        await ctx.send(f'The queue contains {len(queued_songs)}')

        for song in queued_songs:
            name_queue.append(f'{count}. {song[1]}')
            count = count+1

        list_as_string = '\n'.join(name_queue)
        await ctx.send(list_as_string)
    else:
        await ctx.send("The queue is empty!")



bot.run(DISCORD_TOKEN)
