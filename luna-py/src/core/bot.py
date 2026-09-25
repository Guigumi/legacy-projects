""" Luna Bot — classe principal. Inicializa DB, services, event bus e carrega cogs. """
from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

from config.settings import Defaults, now_brt
from core.database import Database
from core.events import EventBus
# As classes abaixo agora são injetadas pelo container
from core.di import DependencyContainer
from core.error_handlers import registry as error_registry, handle_unexpected_error

logger = logging.getLogger(__name__)

try:
    from core.utils.ephemeral import patch_ephemeral_autodelete
    _HAS_EPHEMERAL_PATCH = True
except ModuleNotFoundError as exc:
    if exc.name != "core.utils.ephemeral":
        raise
    _HAS_EPHEMERAL_PATCH = False

    def patch_ephemeral_autodelete() -> None:  # type: ignore[misc]
        return


# COGS_DIR agora é resolvido dinamicamente no _discover_cogs



async def _get_prefix(bot: LunaBot, message: discord.Message) -> list[str]:
    """Resolve o prefixo dinâmico por servidor via banco de dados."""
    if bot.user:
        prefixes = [f"<@!{bot.user.id}> ", f"<@{bot.user.id}> "]
    else:
        prefixes = []

    prefix = Defaults.PREFIX
    if message.guild and bot.db.is_connected:
        config = await bot.guild_service.get_config(message.guild.id)
        prefix = config.get("prefix", Defaults.PREFIX) if config else Defaults.PREFIX

    prefixes.append(prefix)
    if prefix.isalpha():
        lower_prefix = prefix.lower()
        if lower_prefix != prefix:
            prefixes.append(lower_prefix)
    return prefixes


class LunaBot(commands.AutoShardedBot):
    """Classe principal do Luna Bot injetada via DI."""

    container: DependencyContainer
    db: Database
    event_bus: EventBus
    start_time: Optional[datetime.datetime]

    def __init__(self, container: DependencyContainer) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True

        super().__init__(
            command_prefix=_get_prefix,
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=Defaults.ACTIVITY_STATUS,
            ),
            help_command=None,  # Usamos /help próprio
            case_insensitive=True,
        )

        if not _HAS_EPHEMERAL_PATCH:
            logger.warning("core.ephemeral ausente; respostas ephemerals usarão o comportamento padrão.")

        patch_ephemeral_autodelete()

        self.container = container
        self.db = container.db
        self.event_bus = container.event_bus
        self.start_time: datetime.datetime | None = None
        self._dev_mode: bool = False

        # Facade temporária para manter compatibilidade
        self.guild_service = container.guild_service
        self.xp_config_service = container.xp_config_service
        self.user_service = container.user_service
        self.tracking_service = container.tracking_service
        self.autorole_service = container.autorole_service
        self.notification_service = container.notification_service
        self.logging_service = container.logging_service
        self.welcome_service = container.welcome_service

        self.osu_service = container.osu_service
        self.steam_service = container.steam_service
        self.download_service = container.download_service
        self.updater_service = container.updater_service
        self.minecraft_service = container.minecraft_service
        self.giveaway_service = container.giveaway_service
        self.weekly_log_service = container.weekly_log_service
        self.roleplay_service = container.roleplay_service

        self.starboard_service = container.starboard_service
        self.reminder_service = container.reminder_service
        self.automod_service = container.automod_service
        self.ticket_service = container.ticket_service


    async def _discover_cogs(self) -> list[str]:
        """Varre a pasta features em busca de arquivos cogs/*.py e retorna o path pontuado."""
        cogs = []
        # Localiza src/features
        features_path = Path(__file__).parent.parent / "features"

        for cog_file in features_path.glob("**/cogs/*.py"):
            if cog_file.name.startswith("_"):
                continue

            # Converte path em path pontuado relativo ao SRC_DIR
            # features/admin/cogs/clear.py -> features.admin.cogs.clear
            try:
                parts = cog_file.with_suffix("").parts
                if "features" in parts:
                    idx = parts.index("features")
                    cog_path = ".".join(parts[idx:])
                    cogs.append(cog_path)
            except Exception:
                logger.exception("Erro ao processar path do cog: %s", cog_file)

        return sorted(cogs)

    async def setup_hook(self) -> None:
        """Chamado automaticamente pelo discord.py antes do bot ficar online."""
        # Conectar ao banco via container
        await self.container.init_db()

        # Descoberta dinâmica de cogs
        cogs = await self._discover_cogs()
        
        loaded = 0
        failed: list[str] = []
        for cog in cogs:
            try:
                await self.load_extension(cog)
                loaded += 1
            except Exception:
                failed.append(cog)
                logger.exception("Falha ao carregar cog: %s", cog)

        # Iniciar serviços de background
        self.weekly_log_service.set_bot(self)
        self.weekly_log_service.start()

        logger.info("Cogs: %s/%s carregados dinamicamente.", loaded, len(cogs))
        if failed:
            logger.warning("Cogs com falha: %s", ", ".join(failed))

    async def _cleanup_duplicate_global_slash_commands(self) -> int:
        """Remove comandos slash globais duplicados por nome e retorna quantos removeu."""
        if not self.application_id:
            return 0

        try:
            remote_commands = await self.tree.fetch_commands()
        except Exception:
            logger.exception("Falha ao buscar comandos globais para deduplicação.")
            return 0

        seen_names: set[str] = set()
        duplicate_commands: list[discord.app_commands.AppCommand] = []

        for cmd in remote_commands:
            if cmd.name in seen_names:
                duplicate_commands.append(cmd)
                continue
            seen_names.add(cmd.name)

        removed = 0
        for cmd in duplicate_commands:
            try:
                await self.http.delete_global_command(self.application_id, cmd.id)
                removed += 1
            except Exception:
                logger.exception(
                    "Falha ao remover comando global duplicado: %s (%s)",
                    cmd.name,
                    cmd.id,
                )

        if removed:
            logger.warning(
                "Deduplicação global: %s comando(s) duplicado(s) removido(s).",
                removed,
            )

        return removed

    async def _clear_guild_scoped_slash_commands(self) -> int:
        """Remove comandos guild-scoped antigos para evitar duplicação com globais."""
        cleared = 0
        for guild in self.guilds:
            try:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
                cleared += 1
            except Exception:
                logger.exception(
                    "Falha ao limpar comandos guild-scoped em %s (%s)",
                    guild.name,
                    guild.id,
                )

        if cleared:
            logger.debug(
                "Limpeza de comandos guild-scoped concluída em %s servidor(es).",
                cleared,
            )

        return cleared

    async def on_ready(self) -> None:
        first_ready = self.start_time is None
        if first_ready:
            self.start_time = now_brt()

        # Sincronizar slash commands apenas na primeira conexão
        slash_count = 0
        if first_ready:
            try:
                synced = await self.tree.sync()
                slash_count = len(synced)
                await self._clear_guild_scoped_slash_commands()
                removed = await self._cleanup_duplicate_global_slash_commands()
                if removed > 0:
                    synced = await self.tree.sync()
                    slash_count = len(synced)
            except Exception:
                logger.exception("Falha ao sincronizar slash commands.")

        logger.info(
            " Online | %s | Servidores: %s | Slash: %s",
            self.user or "?",
            len(self.guilds),
            slash_count,
        )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Log ao entrar em novo servidor."""
        logger.info("Entrou no servidor: %s (ID: %s)", guild.name, guild.id)

    async def close(self) -> None:
        await super().close()

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Tratamento global de erros para prefix commands usando handlers modulares."""
        handled = await error_registry.handle(self, ctx, error)
        if not handled:
            await handle_unexpected_error(self, ctx, error)
