from __future__ import annotations

from core.repository import BaseRepository


class TicketRepository(BaseRepository):
    """Acesso ao banco de dados SQLite para o sistema de tickets."""

    async def get_config(self, guild_id: int) -> dict | None:
        """Retorna a configuração de tickets para uma guilda."""
        row = await self.db.fetchone(
            "SELECT * FROM ticket_config WHERE guild_id = ?",
            (guild_id,),
        )
        return dict(row) if row else None

    async def save_config(
        self,
        guild_id: int,
        category_id: int,
        support_role_id: int,
        log_channel_id: int | None,
    ) -> None:
        """Salva ou atualiza a configuração de tickets da guilda."""
        await self.db.execute(
            """
            INSERT INTO ticket_config (
                guild_id, category_id, support_role_id, log_channel_id, updated_at
            ) VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                category_id = excluded.category_id,
                support_role_id = excluded.support_role_id,
                log_channel_id = excluded.log_channel_id,
                updated_at = excluded.updated_at
            """,
            (guild_id, category_id, support_role_id, log_channel_id),
        )
        await self.db.commit()

    async def get_next_ticket_number(self, guild_id: int) -> int:
        """Incrementa de forma atômica e retorna o próximo número de ticket."""
        await self.db.execute(
            """
            INSERT INTO ticket_config (
                guild_id, category_id, support_role_id, last_ticket_number, enabled, updated_at
            ) VALUES (?, 0, 0, 1, 1, datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                last_ticket_number = last_ticket_number + 1,
                updated_at = excluded.updated_at
            """,
            (guild_id,),
        )
        await self.db.commit()
        
        row = await self.db.fetchone(
            "SELECT last_ticket_number FROM ticket_config WHERE guild_id = ?",
            (guild_id,),
        )
        return row["last_ticket_number"] if row else 1

    async def get_active_ticket_by_user(self, guild_id: int, creator_id: int) -> dict | None:
        """Busca se o usuário já possui um ticket ativo/aberto na guilda."""
        row = await self.db.fetchone(
            "SELECT * FROM tickets WHERE guild_id = ? AND creator_id = ? AND status != 'closed'",
            (guild_id, creator_id),
        )
        return dict(row) if row else None

    async def create_ticket(
        self,
        guild_id: int,
        channel_id: int,
        creator_id: int,
    ) -> None:
        """Cria um novo registro de ticket no banco de dados."""
        await self.db.execute(
            """
            INSERT INTO tickets (
                guild_id, channel_id, creator_id, status, created_at
            ) VALUES (?, ?, ?, 'open', datetime('now'))
            """,
            (guild_id, channel_id, creator_id),
        )
        await self.db.commit()

    async def get_ticket_by_channel(self, channel_id: int) -> dict | None:
        """Busca as informações de um ticket através de seu canal de ID."""
        row = await self.db.fetchone(
            "SELECT * FROM tickets WHERE channel_id = ? AND status != 'closed'",
            (channel_id,),
        )
        return dict(row) if row else None

    async def claim_ticket(self, channel_id: int, claimant_id: int) -> None:
        """Marca o ticket como assumido por um staff."""
        await self.db.execute(
            "UPDATE tickets SET claimant_id = ?, status = 'claimed' WHERE channel_id = ?",
            (claimant_id, channel_id),
        )
        await self.db.commit()

    async def close_ticket(self, channel_id: int, closed_by: int) -> None:
        """Marca o ticket como fechado."""
        await self.db.execute(
            """
            UPDATE tickets
            SET status = 'closed', closed_by = ?, closed_at = datetime('now')
            WHERE channel_id = ?
            """,
            (closed_by, channel_id),
        )
        await self.db.commit()
