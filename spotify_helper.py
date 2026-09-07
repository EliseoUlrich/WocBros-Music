import asyncio
import json
import logging
import os
import re
import urllib.request

logger = logging.getLogger("DiscordBot.Spotify")

# Regex para URLs de Spotify
SPOTIFY_URL_REGEX = re.compile(
    r'https?://(?:open\.)?spotify\.com/(?:intl-[a-zA-Z]+/)?(track|playlist|album)/([a-zA-Z0-9]+)'
)
SPOTIFY_URI_REGEX = re.compile(r'spotify:(track|playlist|album):([a-zA-Z0-9]+)')
SPOTIFY_SHORT_REGEX = re.compile(r'https?://spotify\.link/[a-zA-Z0-9]+')


def is_spotify_url(url: str) -> bool:
    """Verifica si la cadena de texto es un enlace o URI de Spotify."""
    return bool(
        SPOTIFY_URL_REGEX.search(url)
        or SPOTIFY_URI_REGEX.search(url)
        or SPOTIFY_SHORT_REGEX.search(url)
    )


class SpotifyHelper:
    """Extrae metadatos de pistas, álbumes y playlists de Spotify."""

    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.sp = None

        if self.client_id and self.client_secret:
            try:
                import spotipy
                from spotipy.oauth2 import SpotifyClientCredentials
                auth_manager = SpotifyClientCredentials(
                    client_id=self.client_id,
                    client_secret=self.client_secret
                )
                self.sp = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Spotify API oficial configurada con Client ID y Secret.")
            except Exception as e:
                logger.warning(f"No se pudo inicializar spotipy oficial: {e}. Usando extractor embed.")

    def _resolve_url(self, url: str) -> tuple[str | None, str | None]:
        """Resuelve el tipo (track, playlist, album) y el ID del recurso."""
        # Resolver URLs acortadas de spotify.link
        if SPOTIFY_SHORT_REGEX.search(url):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req) as resp:
                    url = resp.geturl()
            except Exception as e:
                logger.error(f"Error al resolver enlace corto de Spotify: {e}")
                return None, None

        match = SPOTIFY_URL_REGEX.search(url)
        if match:
            return match.group(1), match.group(2)

        match_uri = SPOTIFY_URI_REGEX.search(url)
        if match_uri:
            return match_uri.group(1), match_uri.group(2)

        return None, None

    def _fetch_from_embed(self, entity_type: str, entity_id: str) -> dict:
        """Extrae la información a través del endpoint público de Spotify Embed (sin necesidad de API keys)."""
        embed_url = f"https://open.spotify.com/embed/{entity_type}/{entity_id}"
        req = urllib.request.Request(
            embed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
            }
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8')

        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if not match:
            raise ValueError("No se pudo extraer la información del recurso de Spotify.")

        data = json.loads(match.group(1))
        entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})

        title = entity.get('title') or entity.get('name') or "Spotify Playlist"
        author = entity.get('subtitle') or "Varios Artistas"

        # Extraer thumbnail si existe
        thumbnail = None
        images = entity.get('visualIdentity', {}).get('image', [])
        if images:
            thumbnail = images[0].get('url')

        tracks = []
        raw_tracks = entity.get('trackList', [])

        if entity_type == 'track':
            artists_list = entity.get('artists', [])
            artist_name = ", ".join([a.get('name', '') for a in artists_list if a.get('name')]) or author
            track_title = entity.get('title') or entity.get('name')
            dur_ms = entity.get('duration', 0)
            duration_sec = int(dur_ms / 1000) if dur_ms else None

            tracks.append({
                'title': f"{artist_name} - {track_title}",
                'track_name': track_title,
                'artist': artist_name,
                'search_query': f"ytsearch1:{artist_name} {track_title} audio",
                'duration': duration_sec,
                'webpage_url': f"https://open.spotify.com/track/{entity_id}",
                'thumbnail': thumbnail
            })
        else:
            for item in raw_tracks:
                if not item:
                    continue
                item_title = item.get('title', 'Desconocido')
                item_artist = item.get('subtitle', author)
                item_uri = item.get('uri', '')
                track_id = item_uri.split(':')[-1] if item_uri else ''
                dur_ms = item.get('duration', 0)
                duration_sec = int(dur_ms / 1000) if dur_ms else None

                tracks.append({
                    'title': f"{item_artist} - {item_title}",
                    'track_name': item_title,
                    'artist': item_artist,
                    'search_query': f"ytsearch1:{item_artist} {item_title} audio",
                    'duration': duration_sec,
                    'webpage_url': f"https://open.spotify.com/track/{track_id}" if track_id else f"https://open.spotify.com/{entity_type}/{entity_id}",
                    'thumbnail': thumbnail
                })

        return {
            'type': entity_type,
            'title': title,
            'author': author,
            'thumbnail': thumbnail,
            'tracks': tracks
        }

    def _fetch_from_api(self, entity_type: str, entity_id: str) -> dict:
        """Extrae la información usando la API oficial de Spotify (spotipy)."""
        tracks = []
        title = "Spotify"
        author = "Desconocido"
        thumbnail = None

        if entity_type == 'track':
            tr = self.sp.track(entity_id)
            title = tr['name']
            artists = ", ".join([a['name'] for a in tr.get('artists', [])])
            author = artists
            if tr.get('album', {}).get('images'):
                thumbnail = tr['album']['images'][0]['url']
            tracks.append({
                'title': f"{author} - {title}",
                'track_name': title,
                'artist': author,
                'search_query': f"ytsearch1:{author} {title} audio",
                'duration': int(tr['duration_ms'] / 1000),
                'webpage_url': tr['external_urls'].get('spotify', f"https://open.spotify.com/track/{entity_id}"),
                'thumbnail': thumbnail
            })

        elif entity_type == 'playlist':
            pl = self.sp.playlist(entity_id)
            title = pl.get('name', 'Playlist')
            author = pl.get('owner', {}).get('display_name', 'Spotify')
            if pl.get('images'):
                thumbnail = pl['images'][0]['url']

            results = pl['tracks']
            items = results['items']
            while results.get('next') and len(items) < 300:  # Límite seguro de 300 canciones por playlist
                results = self.sp.next(results)
                items.extend(results['items'])

            for item in items:
                tr = item.get('track')
                if not tr or not tr.get('name'):
                    continue
                artists = ", ".join([a['name'] for a in tr.get('artists', [])])
                track_thumb = tr.get('album', {}).get('images', [{}])[0].get('url', thumbnail)
                tracks.append({
                    'title': f"{artists} - {tr['name']}",
                    'track_name': tr['name'],
                    'artist': artists,
                    'search_query': f"ytsearch1:{artists} {tr['name']} audio",
                    'duration': int(tr['duration_ms'] / 1000),
                    'webpage_url': tr['external_urls'].get('spotify', ''),
                    'thumbnail': track_thumb
                })

        elif entity_type == 'album':
            alb = self.sp.album(entity_id)
            title = alb.get('name', 'Álbum')
            author = ", ".join([a['name'] for a in alb.get('artists', [])])
            if alb.get('images'):
                thumbnail = alb['images'][0]['url']

            results = alb['tracks']
            items = results['items']
            while results.get('next') and len(items) < 150:
                results = self.sp.next(results)
                items.extend(results['items'])

            for tr in items:
                if not tr or not tr.get('name'):
                    continue
                artists = ", ".join([a['name'] for a in tr.get('artists', [])]) or author
                tracks.append({
                    'title': f"{artists} - {tr['name']}",
                    'track_name': tr['name'],
                    'artist': artists,
                    'search_query': f"ytsearch1:{artists} {tr['name']} audio",
                    'duration': int(tr['duration_ms'] / 1000),
                    'webpage_url': tr['external_urls'].get('spotify', ''),
                    'thumbnail': thumbnail
                })

        return {
            'type': entity_type,
            'title': title,
            'author': author,
            'thumbnail': thumbnail,
            'tracks': tracks
        }

    async def get_tracks(self, url: str, loop: asyncio.AbstractEventLoop | None = None) -> dict:
        """Obtiene la lista de canciones de una URL de Spotify asíncronamente."""
        loop = loop or asyncio.get_event_loop()
        entity_type, entity_id = self._resolve_url(url)

        if not entity_type or not entity_id:
            raise ValueError("No se reconoció un enlace válido de Spotify (debe ser track, playlist o album).")

        def extract():
            if self.sp:
                try:
                    return self._fetch_from_api(entity_type, entity_id)
                except Exception as e:
                    logger.warning(f"Error con API oficial de Spotify ({e}), usando fallback embed...")
            return self._fetch_from_embed(entity_type, entity_id)

        return await loop.run_in_executor(None, extract)
