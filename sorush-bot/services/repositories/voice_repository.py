"""
Voice Session Repository
Handles voice session tracking and aggregation
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from services.repositories.base import BaseRepository
from services.repositories.user_repository import user_repo

logger = logging.getLogger(__name__)


class VoiceSessionRepository(BaseRepository):
    """Repository for voice session operations"""

    def _get_table_name(self) -> str:
        return "voice_sessions"

    def start_voice_session(self, guild_id: int, user_id: int, channel_id: int,
                            is_streaming: bool = False, is_muted: bool = False,
                            is_deafened: bool = False) -> int:
        """Start a voice session and return the session id"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO voice_sessions
                    (guild_id, user_id, channel_id, started_at, was_streaming, was_muted, was_deafened)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (guild_id, user_id, channel_id, datetime.now().isoformat(),
                      1 if is_streaming else 0, 1 if is_muted else 0, 1 if is_deafened else 0))

                user = user_repo.get_or_create_user(guild_id, user_id)
                if not user.get('first_voice_at'):
                    user_repo.update_user(guild_id, user_id, first_voice_at=datetime.now().isoformat())

                user_repo.increment_user(guild_id, user_id, voice_sessions=1)
                session_id = cursor.lastrowid
                logger.info(f"✓ Started voice session {session_id} for user {user_id} in guild {guild_id}")
                return session_id
        except Exception as e:
            logger.error(f"Failed to start voice session for user {user_id}: {e}", exc_info=True)
            raise

    def end_voice_session(self, guild_id: int, user_id: int) -> Optional[int]:
        """End the current voice session and return duration in minutes"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT id, started_at, was_streaming, was_muted, was_deafened
                    FROM voice_sessions
                    WHERE guild_id = ? AND user_id = ? AND ended_at IS NULL
                    ORDER BY started_at DESC
                    LIMIT 1
                """, (guild_id, user_id))

                session = cursor.fetchone()
                if not session:
                    logger.debug(f"No active voice session found for user {user_id}")
                    return None

                started = datetime.fromisoformat(session['started_at'])
                duration_mins = int((datetime.now() - started).total_seconds() / 60)
                is_interrupted = duration_mins > 1440

                cursor.execute("""
                    UPDATE voice_sessions
                    SET ended_at = ?, duration_mins = ?, interrupted = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), duration_mins, 1 if is_interrupted else 0, session['id']))

                if not is_interrupted and duration_mins > 0:
                    user_repo.increment_user(
                        guild_id,
                        user_id,
                        voice_mins=duration_mins
                    )
                    user_repo.update_user(guild_id, user_id, last_voice_at=datetime.now().isoformat())

                    if session['was_streaming']:
                        user_repo.increment_user(guild_id, user_id, stream_mins=duration_mins)
                    if session['was_muted']:
                        user_repo.increment_user(guild_id, user_id, muted_mins=duration_mins)
                    if session['was_deafened']:
                        user_repo.increment_user(guild_id, user_id, deafened_mins=duration_mins)

                    user_repo.update_user_max(guild_id, user_id, max_call_time=duration_mins)
                    
                    logger.info(f"✓ Ended voice session {session['id']}: {duration_mins}min for user {user_id}")
                else:
                    logger.warning(f"Interrupted or too long voice session for user {user_id}: {duration_mins}min")
                
                return duration_mins
        except Exception as e:
            logger.error(f"Failed to end voice session for user {user_id}: {e}", exc_info=True)
            raise

            return duration_mins if not is_interrupted else 0

    def get_user_voice_sessions(self, guild_id: int, user_id: int,
                                limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent voice sessions for a user"""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM voice_sessions
                WHERE guild_id = ? AND user_id = ? AND ended_at IS NOT NULL
                ORDER BY started_at DESC
                LIMIT ?
            """, (guild_id, user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def recover_active_sessions(self) -> int:
        """Recover and close sessions left open after a crash"""
        recovered = 0
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT id, guild_id, user_id, started_at
                FROM voice_sessions
                WHERE ended_at IS NULL
            """)
            active_sessions = cursor.fetchall()

            for session in active_sessions:
                session_id = session['id']
                guild_id = session['guild_id']
                user_id = session['user_id']
                started_at = datetime.fromisoformat(session['started_at'])
                duration_mins = int((datetime.now() - started_at).total_seconds() / 60)
                is_interrupted = duration_mins > 1440

                cursor.execute("""
                    UPDATE voice_sessions
                    SET ended_at = ?, duration_mins = ?, interrupted = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), duration_mins, 1 if is_interrupted else 0, session_id))

                if not is_interrupted and duration_mins > 0:
                    user_repo.increment_user(guild_id, user_id, voice_mins=duration_mins)
                    recovered += 1

        return recovered


voice_repo = VoiceSessionRepository()
