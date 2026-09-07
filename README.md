# 🎵 Bot de Música para Discord (WocBrosMusicEsclav)

Un bot de música moderno y completo para Discord desarrollado en **Python 3** utilizando la librería `discord.py` (v2.x) y `yt-dlp`. Soporta tanto comandos de barra diagonal (**Slash Commands `/`**) como comandos con prefijo tradicional (por defecto `!`).

---

## 🚀 Características

- 🟢 **Soporte Completo para Spotify**: Reconoce **Playlists**, **Álbumes** y **Canciones** de Spotify (`open.spotify.com` o enlaces cortos `spotify.link`).
  - Funciona *out-of-the-box* sin necesidad obligatoria de credenciales.
  - Extrae las pistas y reproduce el audio correspondiente en tiempo real sin pausas.
- 🔴 **Reproducción desde YouTube y enlaces directos**: Busca por título o mediante URL de video/playlist.
- 📜 **Sistema de Cola Avanzado**: Cola por servidor con paginación interactiva y distinción visual (🟢 Spotify vs 🔴 YouTube).
- ⚡ **Comandos Híbridos**: Úsalo mediante `/play` o con `!play`.
- 🎚️ **Control de Volumen en Vivo**: Ajusta el volumen de 1 a 100 sin reiniciar la canción.
- ⏸️ **Controles de Reproductor**: Pausa, reanuda, salta canciones (`skip`) y detén la reproducción (`stop`).
- ⏱️ **Auto-desconexión Inteligente**: Si la cola se vacía o el bot se queda solo en el canal, se desconectará automáticamente para ahorrar recursos.
- 🛡️ **Manejo Robusto de Errores y Reconexiones**: Integración con FFmpeg y reconexión automática en streams inestables.

---

## 📋 Requisitos Previos

1. **Python 3.10 o superior** instalado en el sistema.
2. **FFmpeg**: Necesario para procesar el audio de los videos y enviarlo a Discord.
3. **Una aplicación de Discord** creada en el [Portal de Desarrolladores de Discord](https://discord.com/developers/applications).

---

## ⚙️ Configuración Paso a Paso

### 1. Crear la Aplicación y Bot en Discord
1. Ve al [Discord Developer Portal](https://discord.com/developers/applications).
2. Haz clic en **"New Application"** y asígnale un nombre (ej. `WocBros Music`).
3. Ve a la pestaña **"Bot"** en el menú izquierdo:
   - Haz clic en **"Reset Token"** para obtener tu **Token**. ¡Cópialo y guárdalo en un lugar seguro!
   - En la sección **"Privileged Gateway Intents"**, activa:
     - ✅ **Message Content Intent** (Indispensable para leer comandos con prefijo).
     - ✅ **Server Members Intent** (Recomendado).
4. Ve a la pestaña **"OAuth2"** > **"URL Generator"**:
   - En **SCOPES**, selecciona: `bot` y `applications.commands`.
   - En **BOT PERMISSIONS**, selecciona:
     - `Connect` (Conectarse a voz)
     - `Speak` (Hablar en voz)
     - `Send Messages` (Enviar mensajes)
     - `Embed Links` (Insertar enlaces)
     - `Read Message History` (Leer historial)
   - Copia la URL generada en la parte inferior y ábrela en tu navegador para invitar al bot a tu servidor.

---

### 2. Configurar las Variables de Entorno (`.env`)
Abre el archivo `.env` en la raíz de este proyecto y pega tu token:

```env
DISCORD_TOKEN=TU_TOKEN_DE_DISCORD_AQUI
BOT_PREFIX=!
```

> 💡 *Opcional*: Si FFmpeg no está en las variables de entorno de tu sistema (PATH), puedes agregar la ruta directa al ejecutable en el `.env`:
> ```env
> FFMPEG_PATH=C:\ruta\hacia\ffmpeg.exe
> ```

---

### 3. Crear Entorno Virtual e Instalar Dependencias

En una terminal en la carpeta del proyecto:

```powershell
# Crear entorno virtual (recomendado)
python -m venv venv

# Activar entorno virtual en Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Instalar librerías requeridas
pip install -r requirements.txt
```

---

### 4. Iniciar el Bot

```powershell
python main.py
```

Al iniciar correctamente, verás en la consola:
```
[INFO] DiscordBot: Módulo de música cargado correctamente.
[INFO] DiscordBot: Sincronizados X comandos de aplicación (/slash commands).
[INFO] DiscordBot: Bot conectado como WocBros Music#0000 (ID: ...)
```

---

## 🎮 Lista de Comandos

| Comando | Alias | Descripción |
|---|---|---|
| `/play <búsqueda o url>` | `!play` | Busca y reproduce una canción o agrega una playlist a la cola. |
| `/pause` | `!pause` | Pausa la canción actual. |
| `/resume` | `!resume` | Reanuda la reproducción en curso. |
| `/skip` | `!skip` | Salta a la siguiente canción en la cola. |
| `/stop` | `!stop` | Detiene la música y limpia la cola por completo. |
| `/queue [página]` | `!queue` | Muestra la lista de canciones en espera. |
| `/shuffle` | `!shuffle` | Mezcla aleatoriamente todas las canciones en la cola. |
| `/nowplaying` | `/np`, `!np` | Muestra los detalles de la pista que está sonando. |
| `/volume <1-100>` | `!volume` | Ajusta el volumen de la reproducción. |
| `/join` | `!join` | Hace que el bot se una a tu canal de voz actual. |
| `/disconnect` | `/leave`, `!leave` | Desconecta al bot del canal de voz. |
| `/help_music` | `!help_music` | Muestra un mensaje de ayuda con todos los comandos. |

---

## 🛠️ Estructura del Proyecto

```
WocBrosMusicEsclav/
│
├── cogs/
│   └── music.py         # Cog principal con el reproductor, cola y comandos
├── .env.example         # Plantilla de configuración de variables de entorno
├── .env                 # Variables de entorno con el token (no subir a git)
├── .gitignore           # Archivos ignorados por Git
├── requirements.txt     # Dependencias de Python (discord.py, yt-dlp, etc.)
├── main.py              # Punto de entrada y configuración del bot
└── README.md            # Documentación del proyecto
```
