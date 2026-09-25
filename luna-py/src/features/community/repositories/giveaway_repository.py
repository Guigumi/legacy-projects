from __future__ import annotations

import aiosqlite
from core.repository import BaseRepository

class GiveawayRepository(BaseRepository):
    """Repositório para gerenciamento de sorteios."""

    async def create_giveaway(
        self, guild_id: int, channel_id: int, creator_id: int, 
        prize: str, winner_count: int, ends_at: str
    ) -> int:
        cursor = await self.db.execute(
            """
            INSERT INTO giveaways (guild_id, channel_id, creator_id, prize, winner_count, ends_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, creator_id, prize, winner_count, ends_at),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def get_giveaway(self, giveaway_id: int) -> dict | None:
        row = await self.db.fetchone(
            "SELECT * FROM giveaways WHERE id = ?", (giveaway_id,)
        )
        return dict(row) if row else None

    async def get_active_giveaways(self) -> list[dict]:
        rows = await self.db.fetchall(
            "SELECT * FROM giveaways WHERE ended = 0 AND cancelled = 0"
        )
        return [dict(r) for r in rows]

    async def add_participant(self, giveaway_id: int, user_id: int) -> bool:
        """Retorna True se foi adicionado, False se já estava."""
        try:
            await self.db.execute(
                "INSERT INTO giveaway_participants (giveaway_id, user_id) VALUES (?, ?)",
                (giveaway_id, user_id),
            )
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_participant(self, giveaway_id: int, user_id: int) -> None:
        await self.db.execute(
            "DELETE FROM giveaway_participants WHERE giveaway_id = ? AND user_id = ?",
            (giveaway_id, user_id),
        )
        await self.db.commit()

    async def get_participants(self, giveaway_id: int) -> list[int]:
        rows = await self.db.fetchall(
            "SELECT user_id FROM giveaway_participants WHERE giveaway_id = ?",
            (giveaway_id,),
        )
        return [r["user_id"] for r in rows]

    async def end_giveaway(self, giveaway_id: int, winners: str) -> None:
        """winners é uma string com os IDs dos ganhadores (JSON ou comma-separated)."""
        await self.db.execute(
            "UPDATE giveaways SET ended = 1, winners = ? WHERE id = ?",
            (winners, giveaway_id),
        )
        await self.db.commit()

    async def update_message_id(self, giveaway_id: int, message_id: int) -> None:
        await self.db.execute(
            "UPDATE giveaways SET message_id = ? WHERE id = ?",
            (message_id, giveaway_id),
        )
        await self.db.commit()

    async def cancel_giveaway(self, giveaway_id: int) -> None:
        await self.db.execute(
            "UPDATE giveaways SET cancelled = 1 WHERE id = ?",
            (giveaway_id,),
        )
        await self.db.commit()

    async def get_giveaways(self, guild_id: int) -> list[dict]:
        rows = await self.db.fetchall(
            "SELECT * FROM giveaways WHERE guild_id = ? ORDER BY id DESC LIMIT 50",
            (guild_id,),
        )
        return [dict(r) for r in rows]
