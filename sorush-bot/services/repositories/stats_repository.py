"""
Stats Repository
Aggregated stats queries for bot and guilds
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple
from services.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class StatsRepository(BaseRepository):
    """Repository for aggregated statistics"""

    def _get_table_name(self) -> str:
        return "users"

    def get_global_user_stats(self) -> Dict[str, Any]:
        """Return overall stats across all guilds"""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_users,
                    COALESCE(SUM(messages), 0) as total_messages,
                    COALESCE(SUM(voice_mins), 0) as total_voice_mins,
                    COALESCE(SUM(xp), 0) as total_xp
                FROM users
            """)
            row = cursor.fetchone()
            return dict(row) if row else {
                'total_users': 0,
                'total_messages': 0,
                'total_voice_mins': 0,
                'total_xp': 0
            }

    def get_top_channels(self, guild_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Return top channels by messages"""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM channel_stats
                WHERE guild_id = ?
                ORDER BY messages DESC
                LIMIT ?
            """, (guild_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_top_commands(self, guild_id: int, limit: int = 5) -> List[Tuple[str, int]]:
        """Return top commands by usage"""
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

    def get_extended_guild_stats(self, guild_id: int) -> Dict[str, Any]:
        """Return extended server statistics"""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COUNT(*) as user_count,
                    SUM(messages) as total_messages,
                    SUM(voice_mins) as total_voice_mins,
                    SUM(xp) as total_xp,
                    AVG(messages) as avg_messages,
                    AVG(voice_mins) as avg_voice_mins
                FROM users WHERE guild_id = ?
            """, (guild_id,))
            stats = dict(cursor.fetchone())

            cursor.execute("""
                SELECT user_id, messages, voice_mins, xp
                FROM users WHERE guild_id = ?
                ORDER BY messages DESC LIMIT 5
            """, (guild_id,))
            stats['top_chatters'] = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT user_id, voice_mins
                FROM users WHERE guild_id = ?
                ORDER BY voice_mins DESC LIMIT 5
            """, (guild_id,))
            stats['top_voice'] = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT COUNT(*) as count FROM user_achievements WHERE guild_id = ?
            """, (guild_id,))
            stats['total_achievements'] = cursor.fetchone()['count']

            cursor.execute("""
                SELECT COUNT(*) as count FROM warnings WHERE guild_id = ?
            """, (guild_id,))
            stats['total_warnings'] = cursor.fetchone()['count']

            cursor.execute("""
                SELECT COUNT(*) as count FROM mod_logs WHERE guild_id = ?
            """, (guild_id,))
            stats['total_mod_actions'] = cursor.fetchone()['count']

            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as count
                FROM user_daily_stats
                WHERE guild_id = ? AND date = ?
            """, (guild_id, today))
            stats['active_today'] = cursor.fetchone()['count']

            cursor.execute("""
                SELECT 
                    SUM(chars_total) as total_chars,
                    SUM(words_total) as total_words,
                    SUM(emojis_used) as total_emojis,
                    SUM(reactions_given) as total_reactions,
                    SUM(commands_used) as total_commands,
                    SUM(games_played) as total_games
                FROM users WHERE guild_id = ?
            """, (guild_id,))
            row = cursor.fetchone()
            if row:
                stats.update(dict(row))

        stats['top_channels'] = self.get_top_channels(guild_id, 5)
        stats['top_commands'] = self.get_top_commands(guild_id, 5)
        return stats


stats_repo = StatsRepository()
