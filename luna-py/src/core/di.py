import logging
import os

from core.database import Database
from core.events import EventBus

logger = logging.getLogger(__name__)

class DependencyContainer:
    """Container super simples de Injeção de Dependência.
    Imports são feitos localmente no __init__ para evitar dependências circulares
    com features que importam o core durante o load de módulos.
    """
    
    def __init__(self):
        from features.community.repositories import (
            AutoRoleRepository,
            GuildRepository,
            NotificationRepository,
            UserRepository,
            XPConfigRepository,
            WelcomeRepository,
            StarboardRepository,
            ReminderRepository,
            TicketRepository,
        )
        from features.fun.repositories.minecraft_repository import MinecraftRepository
        from features.fun.repositories.osu_repository import OsuRepository
        from features.admin.repositories import AutoModRepository
        from features.community.services import (
            AutoRoleService,
            GuildService,
            NotificationService,
            TrackingService,
            UserService,
            XPConfigService,
            WelcomeService,
            StarboardService,
            ReminderService,
            TicketService,
        )
        from features.listeners.services.logging_service import LoggingService
        from features.listeners.services.weekly_log_service import WeeklyLogService
        from features.community.repositories.giveaway_repository import GiveawayRepository
        from features.community.services.giveaway_service import GiveawayService
        from features.fun.integrations.download_service import DownloadService
        from features.fun.integrations.osu_service import OsuService
        from features.fun.integrations.steam_service import SteamService
        from features.admin.updater_service import UpdaterService
        from features.fun.services.minecraft_service import MinecraftService
        from features.fun.services.roleplay_service import RoleplayService
        from features.admin.services import AutoModService


        # Core
        self.db = Database()
        self.event_bus = EventBus()
        
        # Repositories
        self.user_repo = UserRepository(self.db)
        self.guild_repo = GuildRepository(self.db)
        self.autorole_repo = AutoRoleRepository(self.db)
        self.notification_repo = NotificationRepository(self.db)
        self.xp_config_repo = XPConfigRepository(self.db)
        self.welcome_repo = WelcomeRepository(self.db)
        self.starboard_repo = StarboardRepository(self.db)
        self.reminder_repo = ReminderRepository(self.db)
        self.automod_repo = AutoModRepository(self.db)
        self.ticket_repo = TicketRepository(self.db)

        self.osu_repo = OsuRepository(self.db)

        # Services
        self.guild_service = GuildService(self.guild_repo, self.event_bus)
        self.xp_config_service = XPConfigService(self.xp_config_repo, self.event_bus)
        self.welcome_service = WelcomeService(self.welcome_repo, self.event_bus)
        self.user_service = UserService(
            self.user_repo, self.event_bus, self.xp_config_service
        )
        self.tracking_service = TrackingService(
            self.user_repo,
            self.user_service,
            self.event_bus,
            self.xp_config_service,
            guild_service=self.guild_service,
        )
        self.autorole_service = AutoRoleService(self.autorole_repo, self.event_bus)
        self.notification_service = NotificationService(
            self.notification_repo, self.event_bus
        )
        self.giveaway_repo = GiveawayRepository(self.db)
        self.giveaway_service = GiveawayService(self.giveaway_repo, self.event_bus)
        self.logging_service = LoggingService(self.guild_service)
        self.weekly_log_service = WeeklyLogService(self.db, self.logging_service)

        self.starboard_service = StarboardService(self.starboard_repo)
        self.reminder_service = ReminderService(self.reminder_repo)
        self.automod_service = AutoModService(self.automod_repo)
        self.ticket_service = TicketService(self.ticket_repo)


        
        # External APIs
        _missing_apis: list[str] = []

        osu_id = os.getenv("OSU_CLIENT_ID")
        osu_secret = os.getenv("OSU_CLIENT_SECRET")
        if osu_id and osu_secret:
            try:
                self.osu_service = OsuService(int(osu_id), osu_secret, self.osu_repo)
            except (ValueError, TypeError):
                self.osu_service = None
                _missing_apis.append("osu (ID inválido)")
                logger.warning("OSU_CLIENT_ID inválido: %r", osu_id)
        else:
            self.osu_service = None
            _missing_apis.append("osu")

        steam_key = os.getenv("STEAM_API_KEY")
        if steam_key:
            self.steam_service = SteamService(steam_key)
        else:
            self.steam_service = None
            _missing_apis.append("steam")


        self.download_service = DownloadService()
        self.updater_service = UpdaterService()
        self.minecraft_repo = MinecraftRepository(self.db)
        self.minecraft_service = MinecraftService(self.event_bus, self.minecraft_repo)
        self.roleplay_service = RoleplayService()
        
        if _missing_apis:
            logger.warning("APIs off: %s", ", ".join(_missing_apis))

    async def init_db(self):
        await self.db.connect()

    async def close(self):
        if self.osu_service is not None:
            await self.osu_service.close()
        if self.steam_service is not None:
            await self.steam_service.close()
        if self.download_service is not None:
            await self.download_service.close()
        if self.minecraft_service is not None:
            import asyncio
            try:
                await asyncio.wait_for(self.minecraft_service.stop_server(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout ao parar o servidor Minecraft durante shutdown (30s).")
            except Exception as exc:
                logger.warning("Erro ao parar servidor Minecraft no shutdown: %s", exc)
            try:
                await self.minecraft_service.close()
            except Exception as exc:
                logger.warning("Erro ao fechar recursos do MinecraftService: %s", exc)
        if self.roleplay_service is not None:
            await self.roleplay_service.close()
        await self.db.close()
