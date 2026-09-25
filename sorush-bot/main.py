"""
Sorush Bot - Discord Bot Multifuncional

Bot com sistema de XP, estatísticas, jogos e utilidades.
Requer discord.py 2.0+ e Python 3.10+
"""
import asyncio
import datetime
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config import (
    BOT_PREFIX, BOT_DESCRIPTION, BOT_ACTIVITY, BOT_VERSION,
    DISCORD_TOKEN, APPLICATION_ID, validate_config, DATA_DIR
)
from services.core.message_formatter import create_error_handler
from services.connection import db_connection
from services.repositories import command_history_repo, guild_repo
from services.migrations import migrations

# Configuração de logging
def setup_logging() -> logging.Logger:
    """Configura logging com formato colorido"""
    log_format = '%(asctime)s │ %(levelname)-8s │ %(message)s'
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt='%H:%M:%S'
    )
    
    # Silenciar logs verbosos do discord.py
    for noisy in ('discord', 'discord.http', 'discord.gateway'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    
    return logging.getLogger('sorush')

logger = setup_logging()

# Constantes
EXCLUDED_FILES = {'database.py', 'utils.py', '__init__.py', 'message_formatter.py'}
EXCLUDED_COG_DIRS = {"economy", "fun", "gambling", "games"}
EXTRA_EXTENSIONS = [
    "services.xp.listeners",
]


def get_prefix(bot, message) -> list:
    """Gets the prefix for a server (dynamic) - uses database"""
    default = list(BOT_PREFIX)
    
    if not message.guild:
        return commands.when_mentioned_or(*default)(bot, message)
    
    try:
        guild_prefix = guild_repo.get_prefix(message.guild.id)
        # Schema default is "!", our bot default is "s!"
        if guild_prefix and guild_prefix not in ("!", "s!"):
            return commands.when_mentioned_or(guild_prefix)(bot, message)
    except Exception as e:
        logger.debug(f"Error getting prefix for guild {message.guild.id}: {e}")
    
    return commands.when_mentioned_or(*default)(bot, message)


class SorushBot(commands.Bot):
    """Classe principal do Sorush Bot"""
    
    def __init__(self):
        intents = discord.Intents.all()
        
        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            application_id=APPLICATION_ID,
            activity=discord.Game(name=BOT_ACTIVITY),
            description=BOT_DESCRIPTION,
            case_insensitive=True,
            strip_after_prefix=True,
            help_command=None
        )
        
        self.version = BOT_VERSION
        self.start_time: Optional[datetime.datetime] = None
        self._shutdown_event = asyncio.Event()
    
    @property
    def uptime(self) -> Optional[datetime.timedelta]:
        """Retorna o tempo online do bot"""
        if self.start_time:
            return datetime.datetime.now(datetime.timezone.utc) - self.start_time
        return None
    
    async def setup_hook(self):
        """Carrega todas as extensões (cogs) automaticamente"""
        import time
        start = time.perf_counter()
        
        # Setup error handler global
        create_error_handler(self)
        
        cogs_dir = Path(__file__).parent / "cogs"
        
        if not cogs_dir.exists():
            logger.error("Pasta 'cogs' não encontrada!")
            return
        
        loaded = []
        failed = []
        
        # Carrega todos os .py recursivamente (exceto os excluídos)
        for file in sorted(cogs_dir.glob("**/*.py")):
            if file.name.startswith("_") or file.name in EXCLUDED_FILES:
                continue

            relative = file.relative_to(cogs_dir)
            if relative.parts and relative.parts[0] in EXCLUDED_COG_DIRS:
                continue
            
            # Converte caminho para formato de módulo
            module_path = file.relative_to(Path(__file__).parent)
            module_name = str(module_path.with_suffix('')).replace(os.sep, '.')
            
            try:
                await self.load_extension(module_name)
                loaded.append(module_name.split('.')[-1])
            except Exception as e:
                failed.append((module_name, str(e)))
                logger.error(f"Falha ao carregar {module_name}: {e}")

        for module_name in EXTRA_EXTENSIONS:
            try:
                await self.load_extension(module_name)
                loaded.append(module_name.split('.')[-1])
            except Exception as e:
                failed.append((module_name, str(e)))
                logger.error(f"Falha ao carregar {module_name}: {e}")
        
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(f"✓ {len(loaded)} cogs carregados em {elapsed:.0f}ms")
        
        if failed:
            logger.warning(f"✗ {len(failed)} cogs falharam:")
            for name, error in failed:
                logger.warning(f"  └ {name}: {error[:80]}")
    
    async def sync_commands(self, guild: Optional[discord.Guild] = None) -> int:
        """Sincroniza slash commands manualmente"""
        try:
            if guild:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
            else:
                synced = await self.tree.sync()
            return len(synced)
        except discord.HTTPException as e:
            logger.error(f"Erro ao sincronizar: {e}")
            return 0
    
    async def on_ready(self):
        """Chamado quando o bot está pronto"""
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        
        total_users = sum(g.member_count or 0 for g in self.guilds)
        total_commands = len(self.commands) + len(self.tree.get_commands())
        
        logger.info("─" * 40)
        logger.info(f"🤎 {self.user} online!")
        logger.info(f"   Versão: {self.version}")
        logger.info(f"   Servidores: {len(self.guilds)}")
        logger.info(f"   Usuários: {total_users:,}")
        logger.info(f"   Comandos: {total_commands}")
        logger.info(f"   discord.py: {discord.__version__}")
        logger.info("─" * 40)
    
    async def on_command(self, ctx: commands.Context):
        """Log de comandos usados"""
        guild_name = ctx.guild.name if ctx.guild else "DM"
        logger.debug(f"CMD: {ctx.author} @ {guild_name} → {ctx.command}")
        try:
            if ctx.guild and ctx.command:
                command_history_repo.log_command_usage(ctx.guild.id, ctx.author.id, str(ctx.command))
        except Exception:
            logger.exception("Failed to log command usage to database")
    
    async def on_guild_join(self, guild: discord.Guild):
        """Log quando entra em um servidor"""
        logger.info(f"➕ Entrei em: {guild.name} ({guild.member_count} membros)")
    
    async def on_guild_remove(self, guild: discord.Guild):
        """Log quando sai de um servidor"""
        logger.info(f"➖ Saí de: {guild.name}")
    
    async def close(self):
        """Fecha o bot graciosamente"""
        logger.info("Encerrando bot...")
        
        # Fecha conexão do database
        try:
            db_connection.close()
        except Exception:
            pass
        
        await super().close()


# ======================== MAIN ========================

def main():
    """Função principal para iniciar o bot"""
    load_dotenv()
    
    # Banner com versão centralizada
    title = "🤎 SORUSH BOT 🤎"
    version = f"v{BOT_VERSION}"
    width = 31
    
    print()
    print(f"  ╔{'═' * width}╗")
    print(f"  ║{title:^{width}}║")
    print(f"  ║{version:^{width}}║")
    print(f"  ╚{'═' * width}╝")
    print()
    
    # Validar configurações
    try:
        validate_config()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    
    # Verificar versão do discord.py
    if discord.__version__ < "2.0":
        logger.error("Este bot requer discord.py 2.0 ou superior")
        sys.exit(1)
    
    # Inicializar database (schema + migrations)
    if not migrations.initialize_database():
        logger.error("Falha ao inicializar o database")
        sys.exit(1)

    # Criar bot
    bot = SorushBot()
    
    # Signal handlers para graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Sinal de interrupção recebido")
        asyncio.create_task(bot.close())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Iniciar bot
    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.error("Token inválido! Verifique seu .env")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Bot encerrado")


if __name__ == "__main__":
    main()
