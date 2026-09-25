"""
Repositories Package
Centralized data access layer with repository pattern
"""
from services.repositories.base import BaseRepository
from services.repositories.user_repository import user_repo, UserRepository
from services.repositories.guild_repository import guild_repo, GuildRepository
from services.repositories.transaction_repository import transaction_repo, TransactionRepository
from services.repositories.voice_repository import voice_repo, VoiceSessionRepository
from services.repositories.command_history_repository import command_history_repo, CommandHistoryRepository
from services.repositories.stats_repository import stats_repo, StatsRepository
from services.repositories.xp_role_repository import xp_role_repo, XPRoleRepository
from services.repositories.shop_repository import shop_item_repo, shop_purchase_repo, ShopItemRepository, ShopPurchaseRepository
from services.repositories.notification_repository import notification_repo, NotificationRepository

__all__ = [
    'BaseRepository',
    'UserRepository',
    'GuildRepository',
    'TransactionRepository',
    'XPRoleRepository',
    'ShopItemRepository',
    'ShopPurchaseRepository',
    'NotificationRepository',
    'user_repo',
    'guild_repo',
    'transaction_repo',
    'voice_repo',
    'command_history_repo',
    'stats_repo',
    'xp_role_repo',
    'shop_item_repo',
    'shop_purchase_repo',
    'notification_repo',
    'VoiceSessionRepository',
    'CommandHistoryRepository',
    'StatsRepository',
]
