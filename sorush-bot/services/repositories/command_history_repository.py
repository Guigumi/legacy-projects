"""
Command History Repository
Handles command usage tracking
"""
import logging
from typing import Dict, List, Tuple
from services.repositories.base import BaseRepository
from services.repositories.user_repository import user_repo

logger = logging.getLogger(__name__)


class CommandHistoryRepository(BaseRepository):
    """Repository for command history operations"""

    def _get_table_name(self) -> str:
        return "command_history"

    def log_command_usage(self, guild_id: int, user_id: int, command_name: str) -> bool:
        """Log a command usage and increment user counter"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO command_history (guild_id, user_id, command_name)
                    VALUES (?, ?, ?)
                """, (guild_id, user_id, command_name))
            
            result = user_repo.increment_user(guild_id, user_id, commands_used=1)
            if result:
                logger.debug(f"✓ Logged command '{command_name}' from user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to log command usage '{command_name}' for user {user_id}: {e}", exc_info=True)
            return False

    def get_top_commands(self, guild_id: int, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most used commands in a server"""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT command_name, COUNT(*) as count
                FROM command_history
                WHERE guild_id = ?
                GROUP BY command_name
                ORDER BY count DESC
                LIMIT ?
            """, (guild_id, limit))
            return [(row['command_name'], row['count']) for row in cursor.fetchall()]

    def get_user_command_stats(self, guild_id: int, user_id: int) -> Dict[str, int]:
        """Get command usage stats for a user"""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT command_name, COUNT(*) as count
                FROM command_history
                WHERE guild_id = ? AND user_id = ?
                GROUP BY command_name
                ORDER BY count DESC
            """, (guild_id, user_id))
            return {row['command_name']: row['count'] for row in cursor.fetchall()}


command_history_repo = CommandHistoryRepository()
