"""
Notification Repository
Handles user keyword notifications in SQLite
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from services.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class NotificationRepository(BaseRepository):
    """Repository for user notification keywords"""
    
    def _get_table_name(self) -> str:
        return "user_notifications"
    
    def get_keywords(self, guild_id: int, user_id: int) -> List[str]:
        """Get all keywords for a user in a guild"""
        rows = self.find_all(guild_id=guild_id, user_id=user_id)
        return [row['keyword'] for row in rows]
    
    def add_keyword(self, guild_id: int, user_id: int, keyword: str) -> bool:
        """Add a notification keyword"""
        try:
            self.create(
                guild_id=guild_id, user_id=user_id,
                keyword=keyword.lower().strip(),
                created_at=datetime.now(timezone.utc).isoformat()
            )
            return True
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                return False  # Already exists
            logger.error(f"Failed to add keyword: {e}")
            return False
    
    def remove_keyword(self, guild_id: int, user_id: int, keyword: str) -> bool:
        """Remove a notification keyword"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(
                    "DELETE FROM user_notifications WHERE guild_id = ? AND user_id = ? AND keyword = ?",
                    (guild_id, user_id, keyword.lower().strip())
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to remove keyword: {e}")
            return False
    
    def clear_keywords(self, guild_id: int, user_id: int) -> int:
        """Clear all keywords for a user, returns count removed"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(
                    "DELETE FROM user_notifications WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to clear keywords: {e}")
            return 0
    
    def get_all_guild_keywords(self, guild_id: int) -> Dict[int, List[str]]:
        """Get all keywords for all users in a guild, returns {user_id: [keywords]}"""
        rows = self.find_all(guild_id=guild_id)
        result: Dict[int, List[str]] = {}
        for row in rows:
            uid = row['user_id']
            if uid not in result:
                result[uid] = []
            result[uid].append(row['keyword'])
        return result
    
    def keyword_count(self, guild_id: int, user_id: int) -> int:
        """Count keywords for a user"""
        return self.count(guild_id=guild_id, user_id=user_id)


# Singleton instance
notification_repo = NotificationRepository()
