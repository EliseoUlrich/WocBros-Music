import asyncio
import logging
import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("DiscordBot")

# Cargar variables de entorno desde .env
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("BOT_PREFIX", "!")

if not TOKEN:
    logger.error("¡ERROR! No se encontró DISCORD_TOKEN en el archivo .env.")
    logger.error("Por favor, abre el archivo .env y coloca el token de tu bot de Discord.")


class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Necesario para comandos de prefijo (ej. !play)
        intents.voice_states = True     # Necesario para rastrear canales de voz

        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX),
            intents=intents,
            help_command=None  # Usaremos un comando help personalizado más limpio
        )

    async def setup_hook(self):
        # Cargar cog de música
        try:
            await self.load_extension("cogs.music")
            logger.info("Módulo de música cargado correctamente.")
        except Exception as e:
            logger.error(f"Error al cargar el módulo de música: {e}", exc_info=True)

        # Sincronizar comandos de barra diagonal (/slash commands)
        try:
            synced = await self.tree.sync()
            logger.info(f"Sincronizados {len(synced)} comandos de aplicación (/slash commands).")
        except Exception as e:
            logger.error(f"Error al sincronizar comandos: {e}")

    async def on_ready(self):
        logger.info(f"Bot conectado como {self.user} (ID: {self.user.id})")
        # Establecer presencia del bot
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{PREFIX}play o /play"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)


async def main():
    if not TOKEN:
        print("\n" + "=" * 60)
        print("IMPORTANTE: Configura tu DISCORD_TOKEN en el archivo .env antes de iniciar.")
        print("=" * 60 + "\n")
        return

    bot = MusicBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot apagado por el usuario.")
