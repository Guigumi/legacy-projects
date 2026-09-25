"""
Guild Repository
Handles all guild/server configuration operations
All per-server settings live in guild_config (single source of truth).
"""
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from services.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class GuildRepository(BaseRepository):
    """Repository for guild configuration operations"""
    
    def _get_table_name(self) -> str:
        return "guild_config"
    
    # ======================== CORE ========================
    
    def get_guild(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get guild configuration"""
        return self.find_one(guild_id=guild_id)
    
    def get_or_create_guild(self, guild_id: int, guild_name: Optional[str] = None) -> Dict[str, Any]:
        """Get or create guild configuration"""
        guild = self.get_guild(guild_id)
        if guild:
            return guild
        return self.create_guild(guild_id, guild_name)
    
    def create_guild(self, guild_id: int, guild_name: Optional[str] = None) -> Dict[str, Any]:
        """Create guild configuration with defaults"""
        now = datetime.now().isoformat()
        data = {
            "guild_id": guild_id,
            "guild_name": guild_name,
            "prefix": "!",
            "xp_enabled": 1,
            "xp_multiplier": 1.0,
            "log_enabled": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.create(**data)
        return self.get_guild(guild_id)
    
    def update_guild(self, guild_id: int, **updates) -> bool:
        """Update guild configuration"""
        self.get_or_create_guild(guild_id)
        updates['updated_at'] = datetime.now().isoformat()
        return self.update(filters={'guild_id': guild_id}, **updates)
    
    def delete_guild(self, guild_id: int) -> bool:
        """Delete guild configuration (when bot leaves)"""
        try:
            self.delete(guild_id=guild_id)
            logger.info(f"Deleted guild configuration for {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete guild {guild_id}: {e}")
            return False
    
    # ======================== PREFIX ========================
    
    def set_prefix(self, guild_id: int, prefix: str) -> bool:
        return self.update_guild(guild_id, prefix=prefix)
    
    def get_prefix(self, guild_id: int) -> str:
        guild = self.get_or_create_guild(guild_id)
        return guild.get('prefix', '!')
    
    # ======================== LOG CHANNEL ========================
    
    def set_log_channel(self, guild_id: int, channel_id: int, enabled: bool = True) -> bool:
        return self.update_guild(guild_id, log_channel_id=channel_id, log_enabled=1 if enabled else 0)
    
    def get_log_channel(self, guild_id: int) -> Optional[int]:
        guild = self.get_or_create_guild(guild_id)
        if guild.get('log_enabled'):
            return guild.get('log_channel_id')
        return None
    
    def get_log_events(self, guild_id: int) -> dict:
        """Get per-event log toggle dict"""
        guild = self.get_or_create_guild(guild_id)
        try:
            return json.loads(guild.get('log_events') or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_log_events(self, guild_id: int, events: dict) -> bool:
        return self.update_guild(guild_id, log_events=json.dumps(events))
    
    def is_log_event_enabled(self, guild_id: int, event: str) -> bool:
        events = self.get_log_events(guild_id)
        return events.get(event, True)  # default enabled
    
    def set_log_event(self, guild_id: int, event: str, enabled: bool) -> bool:
        events = self.get_log_events(guild_id)
        events[event] = enabled
        return self.set_log_events(guild_id, events)
    
    # ======================== WELCOME ========================
    
    def set_welcome_channel(self, guild_id: int, channel_id: int, message: Optional[str] = None) -> bool:
        return self.update_guild(guild_id, welcome_channel_id=channel_id, welcome_message=message)
    
    def get_welcome_channel(self, guild_id: int) -> Optional[int]:
        guild = self.get_or_create_guild(guild_id)
        return guild.get('welcome_channel_id')
    
    # ======================== XP SYSTEM ========================
    
    def set_xp_enabled(self, guild_id: int, enabled: bool) -> bool:
        return self.update_guild(guild_id, xp_enabled=1 if enabled else 0)
    
    def is_xp_enabled(self, guild_id: int) -> bool:
        guild = self.get_or_create_guild(guild_id)
        return bool(guild.get('xp_enabled', 1))
    
    def set_xp_multiplier(self, guild_id: int, multiplier: float) -> bool:
        if multiplier < 0.1 or multiplier > 10.0:
            return False
        return self.update_guild(guild_id, xp_multiplier=multiplier)
    
    def get_xp_multiplier(self, guild_id: int) -> float:
        guild = self.get_or_create_guild(guild_id)
        return float(guild.get('xp_multiplier', 1.0))
    
    def get_xp_config(self, guild_id: int) -> dict:
        """Full XP config dict used by xp_listeners and level cog"""
        guild = self.get_or_create_guild(guild_id)
        msg_xp = guild.get('xp_message_amount', -1)
        return {
            "message": int(msg_xp) if msg_xp is not None else -1,
            "voice": int(guild.get('xp_voice_amount', -1) or -1),
            "enabled": bool(guild.get('xp_enabled', 1)) and (msg_xp is not None and int(msg_xp) >= 0),
            "accumulate_roles": bool(guild.get('xp_accumulate_roles', 1)),
            "levelup_message": bool(guild.get('xp_levelup_message', 1)),
            "levelup_channel": guild.get('xp_levelup_channel_id'),
        }
    
    def set_xp_config(self, guild_id: int, message_xp: int, voice_xp: int) -> bool:
        return self.update_guild(guild_id, xp_message_amount=message_xp, xp_voice_amount=voice_xp)
    
    def set_xp_accumulate_roles(self, guild_id: int, accumulate: bool) -> bool:
        return self.update_guild(guild_id, xp_accumulate_roles=1 if accumulate else 0)
    
    def set_xp_levelup_message(self, guild_id: int, enabled: bool) -> bool:
        return self.update_guild(guild_id, xp_levelup_message=1 if enabled else 0)
    
    def set_xp_levelup_channel(self, guild_id: int, channel_id: Optional[int]) -> bool:
        return self.update_guild(guild_id, xp_levelup_channel_id=channel_id)
    
    # ======================== AUTOROLE ========================
    
    def get_autorole(self, guild_id: int) -> dict:
        guild = self.get_or_create_guild(guild_id)
        return {
            "role_id": guild.get('autorole_id'),
            "enabled": bool(guild.get('autorole_enabled', 0)),
        }
    
    def set_autorole(self, guild_id: int, role_id: int, enabled: bool = True) -> bool:
        return self.update_guild(guild_id, autorole_id=role_id, autorole_enabled=1 if enabled else 0)
    
    def disable_autorole(self, guild_id: int) -> bool:
        return self.update_guild(guild_id, autorole_enabled=0)
    
    # ======================== ECONOMY / DAILY ========================
    
    def get_daily_config(self, guild_id: int) -> dict:
        guild = self.get_or_create_guild(guild_id)
        return {
            "base": guild.get('daily_base', 500) or 500,
            "streak_bonus": guild.get('daily_streak_bonus', 50) or 50,
            "max_streak_bonus": guild.get('daily_max_streak_bonus', 1000) or 1000,
        }
    
    def set_daily_config(self, guild_id: int, base: int = None, streak_bonus: int = None, max_streak_bonus: int = None) -> bool:
        updates = {}
        if base is not None:
            updates['daily_base'] = base
        if streak_bonus is not None:
            updates['daily_streak_bonus'] = streak_bonus
        if max_streak_bonus is not None:
            updates['daily_max_streak_bonus'] = max_streak_bonus
        if not updates:
            return False
        return self.update_guild(guild_id, **updates)
    
    # ======================== GAMBLING ========================
    
    def get_gambling_config(self, guild_id: int) -> dict:
        guild = self.get_or_create_guild(guild_id)
        return {
            "enabled": bool(guild.get('gambling_enabled', 1)),
            "min_bet": guild.get('gambling_min_bet', 50) or 50,
            "max_bet": guild.get('gambling_max_bet', 50000) or 50000,
            "daily_loss_limit": guild.get('gambling_daily_loss_limit', 10000) or 10000,
            "house_edge": float(guild.get('gambling_house_edge', 0.02) or 0.02),
        }
    
    def set_gambling_config(self, guild_id: int, **kwargs) -> bool:
        mapping = {
            "enabled": "gambling_enabled",
            "min_bet": "gambling_min_bet",
            "max_bet": "gambling_max_bet",
            "daily_loss_limit": "gambling_daily_loss_limit",
            "house_edge": "gambling_house_edge",
        }
        updates = {}
        for key, col in mapping.items():
            if key in kwargs:
                val = kwargs[key]
                if key == "enabled":
                    val = 1 if val else 0
                updates[col] = val
        if not updates:
            return False
        return self.update_guild(guild_id, **updates)
    
    # ======================== SHOP ========================
    
    def is_shop_enabled(self, guild_id: int) -> bool:
        guild = self.get_or_create_guild(guild_id)
        return bool(guild.get('shop_enabled', 1))
    
    def set_shop_enabled(self, guild_id: int, enabled: bool) -> bool:
        return self.update_guild(guild_id, shop_enabled=1 if enabled else 0)
    
    # ======================== FEATURE TOGGLES ========================
    
    def is_feature_enabled(self, guild_id: int, feature: str) -> bool:
        """Check if a feature category is enabled. feature = economy|fun|moderation|notifications"""
        guild = self.get_or_create_guild(guild_id)
        col = f"feature_{feature}_enabled"
        return bool(guild.get(col, 1))
    
    def set_feature_enabled(self, guild_id: int, feature: str, enabled: bool) -> bool:
        col = f"feature_{feature}_enabled"
        return self.update_guild(guild_id, **{col: 1 if enabled else 0})


# Singleton instance
guild_repo = GuildRepository()
