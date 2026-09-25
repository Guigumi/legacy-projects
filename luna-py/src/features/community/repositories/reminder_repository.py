from __future__ import annotations

from core.repository import BaseRepository


class ReminderRepository(BaseRepository):
    """Acesso a dados de lembretes no banco."""

    async def create(
        self, user_id: int, channel_id: int, guild_id: int | None, message: str, remind_at: str
    ) -> int:
        cursor = await self.db.execute(
            """
            INSERT INTO reminders (user_id, channel_id, guild_id, message, remind_at, notified)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (user_id, channel_id, guild_id, message, remind_at),
        )
        await self.db.commit()
        return cursor.lastrowid or 0

    async def get_pending(self) -> list[dict]:
        rows = await self.db.fetchall(
            "SELECT * FROM reminders WHERE notified = 0 ORDER BY remind_at"
        )
        return [dict(r) for r in rows if r]

    async def mark_notified(self, reminder_id: int) -> None:
        await self.db.execute(
            "UPDATE reminders SET notified = 1 WHERE id = ?",
            (reminder_id,),
        )
        await self.db.commit()
