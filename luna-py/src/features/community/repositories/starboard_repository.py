from __future__ import annotations

from core.repository import BaseRepository


class StarboardRepository(BaseRepository):
    """Acesso a dados de Starboard no banco."""

    async def get_config(self, guild_id: int) -> dict | None:
        row = await self.db.fetchone(
            "SELECT * FROM starboard_config WHERE guild_id = ?",
            (guild_id,),
        )
        return dict(row) if row else None

    async def save_config(
        self, guild_id: int, channel_id: int, emoji: str, min_stars: int, enabled: int = 1
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO starboard_config (guild_id, channel_id, emoji, min_stars, enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                emoji = excluded.emoji,
                min_stars = excluded.min_stars,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (guild_id, channel_id, emoji, min_stars, enabled),
        )
        await self.db.commit()

    async def disable_starboard(self, guild_id: int) -> None:
        await self.db.execute(
            "UPDATE starboard_config SET enabled = 0, updated_at = datetime('now') WHERE guild_id = ?",
            (guild_id,),
        )
        await self.db.commit()

    async def get_starred_message(self, message_id: int) -> dict | None:
        row = await self.db.fetchone(
            "SELECT * FROM starboard_messages WHERE message_id = ?",
            (message_id,),
        )
        return dict(row) if row else None

    async def add_starred_message(
        self,
        message_id: int,
        starboard_message_id: int,
        guild_id: int,
        channel_id: int,
        star_count: int,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO starboard_messages (message_id, starboard_message_id, guild_id, channel_id, star_count, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (message_id, starboard_message_id, guild_id, channel_id, star_count),
        )
        await self.db.commit()

    async def update_starred_message_count(self, message_id: int, star_count: int) -> None:
        await self.db.execute(
            "UPDATE starboard_messages SET star_count = ?, updated_at = datetime('now') WHERE message_id = ?",
            (star_count, message_id),
        )
        await self.db.commit()

    async def delete_starred_message(self, message_id: int) -> None:
        await self.db.execute(
            "DELETE FROM starboard_messages WHERE message_id = ?",
            (message_id,),
        )
        await self.db.commit()
