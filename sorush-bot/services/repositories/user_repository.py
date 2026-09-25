"""
User Repository
Handles all user-related database operations
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from services.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository):
    """Repository for user data operations"""

    _VALID_STATS = {
        'messages',
        'voice_mins',
        'xp',
        'level',
        'chars_total',
        'words_total',
        'n_words_count',
        'mora'
    }
    
    def _get_table_name(self) -> str:
        return "users"
    
    def get_user(self, guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific user from a guild"""
        return self.find_one(guild_id=guild_id, user_id=user_id)
    
    def get_or_create_user(self, guild_id: int, user_id: int, 
                           user_name: Optional[str] = None,
                           guild_name: Optional[str] = None) -> Dict[str, Any]:
        """Get or create a user"""
        user = self.get_user(guild_id, user_id)
        if user:
            return user
        
        return self.create_user(guild_id, user_id, user_name, guild_name)
    
    def create_user(self, guild_id: int, user_id: int,
                    user_name: Optional[str] = None,
                    guild_name: Optional[str] = None) -> Dict[str, Any]:
        """Create a new user"""
        now = datetime.now().isoformat()
        data = {
            "guild_id": guild_id,
            "user_id": user_id,
            "user_name": user_name,
            "guild_name": guild_name,
            "created_at": now,
            "updated_at": now,
        }
        
        self.create(**data)
        return self.get_user(guild_id, user_id)
    
    def update_user(self, guild_id: int, user_id: int, **updates) -> bool:
        """
        Update user data with automatic updated_at timestamp
        
        Ensures user exists before updating.
        Returns True if successful, False otherwise.
        """
        # Ensure user exists first
        self.get_or_create_user(guild_id, user_id)
        
        updates['updated_at'] = datetime.now().isoformat()
        
        try:
            result = self.update(
                filters={'guild_id': guild_id, 'user_id': user_id},
                **updates
            )
            if not result:
                logger.warning(f"update_user returned rowcount 0 for user {user_id} in guild {guild_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {e}", exc_info=True)
            raise

    def increment_user(self, guild_id: int, user_id: int, **increments) -> bool:
        """
        Increment multiple numeric fields for a user
        Ensures user exists before incrementing
        """
        if not increments:
            return False

        # Ensure user exists
        self.get_or_create_user(guild_id, user_id)

        set_parts = []
        values = []
        for key, value in increments.items():
            set_parts.append(f"{key} = {key} + ?")
            values.append(value)

        set_parts.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.extend([guild_id, user_id])

        query = f"UPDATE users SET {', '.join(set_parts)} WHERE guild_id = ? AND user_id = ?"

        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, values)
                result = cursor.rowcount > 0
                if result:
                    logger.debug(f"Incremented {list(increments.keys())} for user {user_id}")
                else:
                    logger.warning(f"increment_user: No rows updated for user {user_id}")
                return result
        except Exception as e:
            logger.error(f"Failed to increment user {user_id} fields {list(increments.keys())}: {e}", exc_info=True)
            raise

    def update_user_max(self, guild_id: int, user_id: int, **updates) -> bool:
        """Update max values if the new value is higher"""
        if not updates:
            return False

        self.get_or_create_user(guild_id, user_id)

        set_parts = []
        values = []
        for key, value in updates.items():
            set_parts.append(f"{key} = MAX({key}, ?)")
            values.append(value)

        set_parts.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.extend([guild_id, user_id])

        query = f"UPDATE users SET {', '.join(set_parts)} WHERE guild_id = ? AND user_id = ?"

        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, values)
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update user max values: {e}")
            raise
    
    def increment_stat(self, guild_id: int, user_id: int, 
                      stat: str, amount: int = 1) -> bool:
        """Increment a numeric stat for a user"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(f"""
                    UPDATE users 
                    SET {stat} = {stat} + ?, updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                """, (amount, datetime.now().isoformat(), guild_id, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to increment {stat}: {e}")
            raise
    
    def add_xp(self, guild_id: int, user_id: int, amount: int) -> Dict[str, Any]:
        """Add XP and calculate level up"""
        user = self.get_or_create_user(guild_id, user_id)
        current_xp = user.get('xp', 0)
        current_level = user.get('level', 0)
        
        new_xp = current_xp + amount
        new_level = self._calculate_level(new_xp)
        
        level_up = new_level > current_level
        
        updates = {
            'xp': new_xp,
            'level': new_level,
        }
        
        # Track XP source (default to messages if not specified)
        xp_key = 'xp_from_messages'
        current_source = user.get(xp_key, 0)
        updates[xp_key] = current_source + amount
        
        self.update_user(guild_id, user_id, **updates)
        
        return {
            'old_level': current_level,
            'new_level': new_level,
            'level_up': level_up,
            'new_xp': new_xp,
            'xp_gained': amount,
        }
    
    @staticmethod
    def _calculate_level(xp: int) -> int:
        """Calculate level from total XP (exponential formula)"""
        # Level = floor(sqrt(xp / 100))
        # Adjust multiplier as needed for game balance
        import math
        return max(0, int(math.sqrt(xp / 100)))
    
    def _validate_stat(self, stat: str) -> str:
        return stat if stat in self._VALID_STATS else 'messages'

    def get_leaderboard(self, guild_id: int, stat: str = 'xp', 
                       limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get leaderboard for a specific stat"""
        stat = self._validate_stat(stat)
        query = f"""
            SELECT user_id, user_name, {stat}, level, messages, voice_mins
            FROM users
            WHERE guild_id = ?
            ORDER BY {stat} DESC
            LIMIT ? OFFSET ?
        """
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, limit, offset))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get leaderboard: {e}")
            raise
    
    def get_user_rank(self, guild_id: int, user_id: int, 
                     stat: str = 'xp') -> Optional[int]:
        """Get user's rank for a specific stat (returns None if stat not found or error occurs)"""
        try:
            stat = self._validate_stat(stat)
            query = f"""
                SELECT COUNT(*) + 1 as rank
                FROM users
                WHERE guild_id = ? AND {stat} > (
                    SELECT {stat} FROM users 
                    WHERE guild_id = ? AND user_id = ?
                )
            """
            
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, guild_id, user_id))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.debug(f"Failed to get user rank for stat '{stat}': {e}")
            return None
    
    def get_top_users(self, guild_id: int, stat: str = 'xp', 
                      limit: int = 5) -> List[Dict[str, Any]]:
        """Get top N users by stat"""
        return self.get_leaderboard(guild_id, stat, limit)

    def get_leaderboard_values(self, guild_id: int, field: str = 'messages', limit: int = 10) -> List[tuple]:
        """Return leaderboard as list of (user_id, value) tuples"""
        field = self._validate_stat(field)
        query = f"""
            SELECT user_id, {field} as value
            FROM users
            WHERE guild_id = ? AND {field} > 0
            ORDER BY {field} DESC
            LIMIT ?
        """

        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, limit))
                return [(row['user_id'], row['value']) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get leaderboard values: {e}")
            raise
    
    def get_active_users_count(self, guild_id: int) -> int:
        """Count users with at least some activity"""
        query = """
            SELECT COUNT(*) FROM users
            WHERE guild_id = ? AND (messages > 0 OR voice_mins > 0)
        """
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id,))
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to get active users count: {e}")
            raise
    
    def reset_daily_stats(self, guild_id: int, user_id: int) -> bool:
        """Reset daily-specific stats (for daily reset timer)"""
        return self.update_user(
            guild_id, user_id,
            gambling_daily_losses=0,
            gambling_daily_reset=datetime.now().isoformat()
        )

    def record_daily_activity(self, guild_id: int, user_id: int, **updates) -> bool:
        """Insert or update daily activity stats"""
        if not updates:
            return False

        today = datetime.now().strftime("%Y-%m-%d")
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT id FROM user_daily_stats
                    WHERE guild_id = ? AND user_id = ? AND date = ?
                """, (guild_id, user_id, today))

                exists = cursor.fetchone()
                if exists:
                    set_parts = []
                    values = []
                    for key, value in updates.items():
                        set_parts.append(f"{key} = {key} + ?")
                        values.append(value)

                    if set_parts:
                        values.extend([guild_id, user_id, today])
                        cursor.execute(f"""
                            UPDATE user_daily_stats
                            SET {', '.join(set_parts)}
                            WHERE guild_id = ? AND user_id = ? AND date = ?
                        """, values)
                        logger.debug(f"Updated daily activity for user {user_id} on {today}")
                else:
                    updates['guild_id'] = guild_id
                    updates['user_id'] = user_id
                    updates['date'] = today

                    columns = ", ".join(updates.keys())
                    placeholders = ", ".join(["?"] * len(updates))
                    cursor.execute(f"""
                        INSERT INTO user_daily_stats ({columns}) VALUES ({placeholders})
                    """, list(updates.values()))
                    
                    # Increment active days in main user table
                    cursor.execute("""
                        UPDATE users
                        SET active_days = active_days + 1, last_daily_activity = ?
                        WHERE guild_id = ? AND user_id = ?
                    """, (today, guild_id, user_id))
                    
                    logger.debug(f"Recorded new daily activity for user {user_id} on {today}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to record daily activity for user {user_id}: {e}", exc_info=True)
            raise

    def get_user_achievements(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        """
        Return achievements for a user
        
        Returns empty list if table doesn't exist or error occurs (gracefully handles unavailable achievements).
        """
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM user_achievements
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY earned_at DESC
                """, (guild_id, user_id))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.debug(f"Failed to get achievements (table may not exist): {e}")
            return []  # Return empty list if achievements table doesn't exist

    def get_user_full_stats(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        """
        Get complete user stats with safe defaults for status command
        
        Returns all data needed for status command with fallback values.
        This ensures status.py always gets valid data.
        """
        user = self.get_or_create_user(guild_id, user_id)
        
        if not user:
            logger.warning(f"User {user_id} in guild {guild_id} not found after create")
            return {}
        
        # Define default values for all possible fields
        defaults = {
            # Basic info
            'user_id': user_id,
            'guild_id': guild_id,
            'user_name': user.get('user_name', 'Unknown'),
            # Messages
            'messages': user.get('messages', 0),
            'chars_total': user.get('chars_total', 0),
            'words_total': user.get('words_total', 0),
            'max_chars_msg': user.get('max_chars_msg', 0),
            'n_words_count': user.get('n_words_count', 0),
            'emojis_used': user.get('emojis_used', 0),
            'attachments_sent': user.get('attachments_sent', 0),
            'links_shared': user.get('links_shared', 0),
            'replies_sent': user.get('replies_sent', 0),
            'mentions_made': user.get('mentions_made', 0),
            # Voice
            'voice_mins': user.get('voice_mins', 0),
            'max_call_time': user.get('max_call_time', 0),
            'voice_sessions': user.get('voice_sessions', 0),
            'stream_mins': user.get('stream_mins', 0),
            'muted_mins': user.get('muted_mins', 0),
            'deafened_mins': user.get('deafened_mins', 0),
            # XP and Level
            'xp': user.get('xp', 0),
            'level': user.get('level', 1),
            'xp_from_messages': user.get('xp_from_messages', 0),
            'xp_from_voice': user.get('xp_from_voice', 0),
            'xp_from_reactions': user.get('xp_from_reactions', 0),
            # Reactions
            'reactions_given': user.get('reactions_given', 0),
            'reactions_received': user.get('reactions_received', 0),
            # Activity
            'commands_used': user.get('commands_used', 0),
            'games_played': user.get('games_played', 0),
            'games_won': user.get('games_won', 0),
            'active_days': user.get('active_days', 0),
            'last_daily_activity': user.get('last_daily_activity'),
            # Timeline
            'first_message_at': user.get('first_message_at'),
            'first_voice_at': user.get('first_voice_at'),
            'last_message_at': user.get('last_message_at'),
            'last_voice_at': user.get('last_voice_at'),
            # Timestamps
            'created_at': user.get('created_at'),
            'updated_at': user.get('updated_at'),
        }
        
        return defaults


# Singleton instance
user_repo = UserRepository()
