import asyncio
import functools
import logging
import math
import os
import random
import discord
from discord.ext import commands
import yt_dlp

from spotify_helper import is_spotify_url, SpotifyHelper

logger = logging.getLogger("DiscordBot.Music")

# Opciones de yt-dlp optimizadas para extracción de audio en streaming
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extract_flat': 'in_playlist',
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # Vincula a IPv4 para evitar problemas de conexión con YouTube
    'js_runtimes': {'node': {}},  # Utiliza Node.js para resolver firmas de JavaScript
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class Song:
    """Representa una canción o pista de audio solicitada (YouTube o Spotify)."""
    def __init__(self, data: dict, requester: discord.Member, search_query: str = None, is_spotify: bool = False):
        self.requester = requester
        self.webpage_url = data.get('webpage_url') or data.get('url', '')
        self.stream_url = data.get('url') if not is_spotify else None
        self.title = data.get('title', 'Canción Desconocida')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader') or data.get('artist') or 'Desconocido'
        self.search_query = search_query or self.webpage_url
        self.is_spotify = is_spotify

    @property
    def formatted_duration(self) -> str:
        if not self.duration:
            return "🔴 En vivo / Desconocido"
        mins, secs = divmod(int(self.duration), 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def create_embed(self, title_prefix="🎶 Reproduciendo Ahora") -> discord.Embed:
        # Color verde para Spotify, blurple para YouTube
        color = discord.Color.from_rgb(30, 215, 96) if self.is_spotify else discord.Color.blurple()
        embed = discord.Embed(
            title=f"{title_prefix}: {self.title}",
            url=self.webpage_url,
            color=color
        )
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        embed.add_field(name="⏱️ Duración", value=self.formatted_duration, inline=True)
        embed.add_field(name="👤 Artista / Canal", value=self.uploader, inline=True)
        embed.add_field(name="🎧 Pedido por", value=self.requester.mention, inline=True)
        
        footer_text = "🟢 Fuente: Spotify" if self.is_spotify else "🔴 Fuente: YouTube"
        embed.set_footer(text=footer_text)
        return embed


class YTDLSource(discord.PCMVolumeTransformer):
    """Fuente de audio que encapsula FFmpeg y volumen."""
    def __init__(self, source: discord.AudioSource, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def create_source(cls, song: Song, *, loop: asyncio.AbstractEventLoop, volume: float = 0.5):
        loop = loop or asyncio.get_event_loop()
        ffmpeg_executable = os.getenv("FFMPEG_PATH", "ffmpeg")

        stream_url = song.stream_url
        # Si la pista viene de Spotify o no tiene stream directo, se busca en YouTube
        if not stream_url or "googlevideo.com" not in stream_url:
            query = song.search_query if song.is_spotify else song.webpage_url
            to_run = functools.partial(ytdl.extract_info, query, download=False)
            data = await loop.run_in_executor(None, to_run)
            if 'entries' in data:
                if not data['entries']:
                    raise ValueError(f"No se encontró audio en YouTube para: {song.title}")
                data = data['entries'][0]
            stream_url = data['url']
            
            # Completar duración o thumbnail si faltaban
            if not song.duration and data.get('duration'):
                song.duration = data.get('duration')
            if not song.thumbnail and data.get('thumbnail'):
                song.thumbnail = data.get('thumbnail')

        audio_source = discord.FFmpegPCMAudio(
            stream_url,
            executable=ffmpeg_executable,
            **FFMPEG_OPTIONS
        )
        return cls(audio_source, data=song.__dict__, volume=volume)


class GuildMusicPlayer:
    """Gestiona la reproducción de música y cola de reproducción de un servidor específico."""
    def __init__(self, ctx: commands.Context):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = ctx.cog

        self.queue: asyncio.Queue[Song] = asyncio.Queue()
        self.next = asyncio.Event()

        self.current: Song | None = None
        self.volume: float = 0.5
        self.voice_client: discord.VoiceClient = ctx.voice_client

        self.player_task = ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                # Esperar 5 minutos (300 s) por una nueva canción antes de desconectarse por inactividad
                async with asyncio.timeout(300):
                    song = await self.queue.get()
            except (asyncio.TimeoutError, TimeoutError):
                logger.info(f"Desconectando del servidor {self.guild.name} por inactividad.")
                if self.voice_client and self.voice_client.is_connected():
                    await self.channel.send("⏱️ Me he desconectado del canal de voz por inactividad.")
                    await self.voice_client.disconnect()
                return self.destroy()

            try:
                source = await YTDLSource.create_source(song, loop=self.bot.loop, volume=self.volume)
            except Exception as e:
                logger.error(f"Error al procesar pista de audio: {e}")
                await self.channel.send(f"❌ Error al intentar reproducir **{song.title}**: `{e}`")
                continue

            self.current = song

            def after_playback(error):
                if error:
                    logger.error(f"Error en reproducción de FFmpeg: {error}")
                self.bot.loop.call_soon_threadsafe(self.next.set)

            if self.voice_client and self.voice_client.is_connected():
                self.voice_client.play(source, after=after_playback)
                await self.channel.send(embed=song.create_embed())
            else:
                return self.destroy()

            await self.next.wait()

            # Limpiar recurso de audio
            if hasattr(source, 'cleanup'):
                source.cleanup()
            self.current = None

    def destroy(self):
        """Cancela la tarea del reproductor y elimina la referencia del servidor."""
        self.player_task.cancel()
        return self.cog.cleanup_player(self.guild)


class Music(commands.Cog):
    """Comandos de música para Discord con soporte para YouTube y Spotify."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, GuildMusicPlayer] = {}
        self.spotify = SpotifyHelper()

    def cleanup_player(self, guild: discord.Guild):
        if guild.id in self.players:
            del self.players[guild.id]

    def get_player(self, ctx: commands.Context) -> GuildMusicPlayer:
        """Obtiene o inicializa el reproductor del servidor."""
        if ctx.guild.id in self.players:
            player = self.players[ctx.guild.id]
            player.channel = ctx.channel
            player.voice_client = ctx.voice_client
            return player

        player = GuildMusicPlayer(ctx)
        self.players[ctx.guild.id] = player
        return player

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Detecta si el bot se quedó solo en el canal para desconectarse."""
        if member.id == self.bot.user.id and after.channel is None:
            # Bot fue desconectado manualmente
            if member.guild.id in self.players:
                self.players[member.guild.id].destroy()
            return

        # Si el bot está en un canal y se queda solo
        voice_client = member.guild.voice_client
        if voice_client and voice_client.channel:
            non_bots = [m for m in voice_client.channel.members if not m.bot]
            if len(non_bots) == 0:
                await voice_client.disconnect()
                if member.guild.id in self.players:
                    self.players[member.guild.id].destroy()

    @commands.hybrid_command(name="join", description="Conecta el bot a tu canal de voz actual.")
    async def join_channel(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("❌ Debes estar conectado a un canal de voz.", ephemeral=True)

        destination = ctx.author.voice.channel
        if ctx.voice_client:
            if ctx.voice_client.channel.id != destination.id:
                await ctx.voice_client.move_to(destination)
        else:
            await destination.connect()

        await ctx.send(f"🔊 Conectado a **{destination.name}**.")

    @commands.hybrid_command(name="play", description="Reproduce canciones o playlists de Spotify o YouTube.")
    async def play(self, ctx: commands.Context, *, busqueda: str):
        """Añade una canción o playlist (YouTube o Spotify) a la cola."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("❌ Debes estar en un canal de voz para reproducir música.", ephemeral=True)

        # Conectar al canal si aún no lo está
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        elif ctx.voice_client.channel.id != ctx.author.voice.channel.id:
            await ctx.voice_client.move_to(ctx.author.voice.channel)

        await ctx.defer()
        player = self.get_player(ctx)

        # --- CASO 1: ENLACE DE SPOTIFY ---
        if is_spotify_url(busqueda):
            try:
                data = await self.spotify.get_tracks(busqueda, loop=self.bot.loop)
            except Exception as e:
                logger.error(f"Error procesando Spotify: {e}", exc_info=True)
                return await ctx.send(f"❌ Error al obtener datos de Spotify: `{e}`")

            tracks = data.get('tracks', [])
            if not tracks:
                return await ctx.send("❌ No se encontraron pistas en el enlace de Spotify.")

            if data['type'] in ('playlist', 'album'):
                for t in tracks:
                    song = Song(t, ctx.author, search_query=t['search_query'], is_spotify=True)
                    await player.queue.put(song)
                tipo_str = "la playlist" if data['type'] == 'playlist' else "el álbum"
                await ctx.send(f"🟢 Añadidas **{len(tracks)}** canciones de {tipo_str} **{data['title']}** (Spotify) a la cola.")
            else:
                # Pista individual de Spotify
                t = tracks[0]
                song = Song(t, ctx.author, search_query=t['search_query'], is_spotify=True)
                await player.queue.put(song)
                if player.current:
                    await ctx.send(embed=song.create_embed(title_prefix="➕ Añadido a la cola"))
                else:
                    await ctx.send(f"🟢 Añadido: **{song.title}** (Spotify)")
            return

        # --- CASO 2: YOUTUBE O BÚSQUEDA GENERAL ---
        is_url = busqueda.startswith("http://") or busqueda.startswith("https://")
        query = busqueda if is_url else f"ytsearch1:{busqueda}"

        try:
            to_run = functools.partial(ytdl.extract_info, query, download=False)
            data = await self.bot.loop.run_in_executor(None, to_run)
        except Exception as e:
            return await ctx.send(f"❌ Error al buscar la canción en YouTube: `{e}`")

        if not data:
            return await ctx.send("❌ No se encontraron resultados para tu búsqueda.")

        if 'entries' in data and data['entries']:
            if not is_url:
                track = data['entries'][0]
                song = Song(track, ctx.author)
                await player.queue.put(song)
                if player.current:
                    await ctx.send(embed=song.create_embed(title_prefix="➕ Añadido a la cola"))
                else:
                    await ctx.send(f"🔍 Encontrado: **{song.title}**")
            else:
                added_count = 0
                for entry in data['entries']:
                    if entry:
                        song = Song(entry, ctx.author)
                        await player.queue.put(song)
                        added_count += 1
                playlist_title = data.get('title', 'Lista de reproducción')
                await ctx.send(f"📑 Añadidas **{added_count}** canciones de la playlist **{playlist_title}** a la cola.")
        else:
            song = Song(data, ctx.author)
            await player.queue.put(song)
            if player.current:
                await ctx.send(embed=song.create_embed(title_prefix="➕ Añadido a la cola"))
            else:
                await ctx.send(f"🔍 Añadido: **{song.title}**")

    @commands.hybrid_command(name="pause", description="Pausa la reproducción actual.")
    async def pause(self, ctx: commands.Context):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send("❌ No hay ninguna canción reproduciéndose.", ephemeral=True)
        if ctx.voice_client.is_paused():
            return await ctx.send("⚠️ La música ya está pausada.", ephemeral=True)

        ctx.voice_client.pause()
        await ctx.send("⏸️ Música pausada.")

    @commands.hybrid_command(name="resume", description="Reanuda la canción pausada.")
    async def resume(self, ctx: commands.Context):
        if not ctx.voice_client or not ctx.voice_client.is_paused():
            return await ctx.send("❌ La música no está pausada.", ephemeral=True)

        ctx.voice_client.resume()
        await ctx.send("▶️ Música reanudada.")

    @commands.hybrid_command(name="skip", description="Salta la canción actual.")
    async def skip(self, ctx: commands.Context):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send("❌ No hay ninguna canción para saltar.", ephemeral=True)

        ctx.voice_client.stop()
        await ctx.send("⏭️ Canción saltada.")

    @commands.hybrid_command(name="stop", description="Detiene la música y limpia la cola de reproducción.")
    async def stop(self, ctx: commands.Context):
        if ctx.guild.id in self.players:
            player = self.players[ctx.guild.id]
            while not player.queue.empty():
                try:
                    player.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            if ctx.voice_client:
                ctx.voice_client.stop()
            await ctx.send("⏹️ Música detenida y cola limpiada.")
        else:
            await ctx.send("❌ No hay reproductor activo en este servidor.", ephemeral=True)

    @commands.hybrid_command(name="queue", description="Muestra la lista de canciones en cola.")
    async def queue_list(self, ctx: commands.Context, pagina: int = 1):
        if ctx.guild.id not in self.players or self.players[ctx.guild.id].queue.empty():
            return await ctx.send("📭 La cola de reproducción está vacía.")

        player = self.players[ctx.guild.id]
        queue_list = list(player.queue._queue)

        items_per_page = 10
        total_pages = math.ceil(len(queue_list) / items_per_page) or 1
        pagina = max(1, min(pagina, total_pages))

        start_idx = (pagina - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_page_items = queue_list[start_idx:end_idx]

        embed = discord.Embed(
            title=f"📜 Cola de Reproducción - {ctx.guild.name}",
            color=discord.Color.gold()
        )

        if player.current:
            source_icon = "🟢 Spotify" if player.current.is_spotify else "🔴 YouTube"
            embed.description = f"**Reproduciendo ahora:** [{player.current.title}]({player.current.webpage_url}) (`{source_icon}`) | `{player.current.formatted_duration}`\n\n**Próximas:**"

        queue_str = ""
        for i, song in enumerate(current_page_items, start=start_idx + 1):
            icon = "🟢" if song.is_spotify else "🔴"
            queue_str += f"`{i}.` {icon} [{song.title}]({song.webpage_url}) - `{song.formatted_duration}` (por {song.requester.mention})\n"

        embed.add_field(name="En cola", value=queue_str or "Ninguna", inline=False)
        embed.set_footer(text=f"Página {pagina}/{total_pages} • Total en cola: {len(queue_list)} canciones")

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="shuffle", description="Mezcla aleatoriamente las canciones en la cola de reproducción.")
    async def shuffle(self, ctx: commands.Context):
        """Mezcla aleatoriamente las canciones que están en la cola."""
        if ctx.guild.id not in self.players or self.players[ctx.guild.id].queue.empty():
            return await ctx.send("📭 La cola de reproducción está vacía.", ephemeral=True)

        player = self.players[ctx.guild.id]
        count = player.queue.qsize()

        if count < 2:
            return await ctx.send("⚠️ Debe haber al menos 2 canciones en la cola para poder mezclar.", ephemeral=True)

        random.shuffle(player.queue._queue)
        await ctx.send(f"🔀 Se han mezclado aleatoriamente **{count}** canciones en la cola.")

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Muestra la información de la canción en curso.")
    async def now_playing(self, ctx: commands.Context):
        if ctx.guild.id not in self.players or not self.players[ctx.guild.id].current:
            return await ctx.send("❌ No hay ninguna canción reproduciéndose actualmente.", ephemeral=True)

        player = self.players[ctx.guild.id]
        await ctx.send(embed=player.current.create_embed())

    @commands.hybrid_command(name="volume", description="Ajusta el volumen de reproducción (1 - 100).")
    async def volume(self, ctx: commands.Context, nivel: int):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send("❌ No hay ninguna canción reproduciéndose.", ephemeral=True)

        if not 1 <= nivel <= 100:
            return await ctx.send("⚠️ El volumen debe estar entre 1 y 100.", ephemeral=True)

        player = self.get_player(ctx)
        player.volume = nivel / 100.0

        if ctx.voice_client.source:
            ctx.voice_client.source.volume = player.volume

        await ctx.send(f"🔊 Volumen ajustado a **{nivel}%**.")

    @commands.hybrid_command(name="disconnect", aliases=["leave"], description="Desconecta el bot del canal de voz.")
    async def disconnect(self, ctx: commands.Context):
        if not ctx.voice_client:
            return await ctx.send("❌ El bot no está conectado a ningún canal de voz.", ephemeral=True)

        if ctx.guild.id in self.players:
            self.players[ctx.guild.id].destroy()

        await ctx.voice_client.disconnect()
        await ctx.send("👋 Desconectado del canal de voz.")

    @commands.hybrid_command(name="help_music", description="Muestra la lista de comandos disponibles del bot de música.")
    async def help_music(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎵 Comandos del Bot de Música (YouTube & Spotify)",
            description="Puedes usar tanto comandos de barra diagonal (`/`) como el prefijo `!`",
            color=discord.Color.green()
        )
        embed.add_field(name="/play <búsqueda o enlace>", value="Reproduce enlaces de **Spotify** (Playlists, Álbumes, Canciones) o de **YouTube**, o busca por texto.", inline=False)
        embed.add_field(name="/pause", value="Pausa la reproducción actual.", inline=True)
        embed.add_field(name="/resume", value="Reanuda la música pausada.", inline=True)
        embed.add_field(name="/skip", value="Salta a la siguiente canción.", inline=True)
        embed.add_field(name="/stop", value="Detiene la música y vacía la cola.", inline=True)
        embed.add_field(name="/queue [página]", value="Muestra las canciones en cola.", inline=True)
        embed.add_field(name="/shuffle", value="Mezcla aleatoriamente la cola.", inline=True)
        embed.add_field(name="/nowplaying", value="Muestra la canción actual.", inline=True)
        embed.add_field(name="/volume <1-100>", value="Ajusta el nivel de volumen.", inline=True)
        embed.add_field(name="/disconnect", value="Desconecta el bot del canal de voz.", inline=True)
        embed.set_footer(text="¡Disfruta de la música en Discord!")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
