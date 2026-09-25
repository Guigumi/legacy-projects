"""
Repositório de AutoRole — CRUD para configurações de cargo automático.
"""

from __future__ import annotations

from config.settings import BotEmojis
from core.repository import BaseRepository


class AutoRoleRepository(BaseRepository):
    """Acesso a dados da tabela autorole."""

    async def get_autoroles(self, guild_id: int) -> list[dict]:
        """Retorna todas as configurações de autorole ativas do servidor."""
        rows = await self.db.fetchall(
            "SELECT * FROM autorole WHERE guild_id = ? AND enabled = 1",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def get_autorole(self, autorole_id: int) -> dict | None:
        """Retorna uma configuração de autorole pelo ID."""
        row = await self.db.fetchone(
            "SELECT * FROM autorole WHERE id = ?",
            (autorole_id,),
        )
        return dict(row) if row else None

    async def get_by_guild(self, guild_id: int) -> list[dict]:
        """Retorna TODAS as configurações (ativas e inativas) do servidor."""
        rows = await self.db.fetchall(
            "SELECT * FROM autorole WHERE guild_id = ? ORDER BY created_at",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def get_by_message(self, message_id: int) -> dict | None:
        """Busca autorole vinculado a uma mensagem (button/reaction)."""
        row = await self.db.fetchone(
            "SELECT * FROM autorole WHERE message_id = ? AND enabled = 1",
            (message_id,),
        )
        return dict(row) if row else None

    async def create(
        self,
        guild_id: int,
        role_id: int,
        mode: str,
        configured_by: int,
        *,
        delay_seconds: int = 0,
        channel_id: int | None = None,
        embed_title: str | None = None,
        embed_text: str | None = None,
        emoji: str = BotEmojis.STATUS_ENABLED,
    ) -> int:
        """Cria nova configuração de autorole. Retorna o ID."""
        cursor = await self.db.execute(
            """
            INSERT INTO autorole
                (guild_id, role_id, mode, delay_seconds, channel_id,
                 embed_title, embed_text, emoji, configured_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                role_id,
                mode,
                delay_seconds,
                channel_id,
                embed_title,
                embed_text,
                emoji,
                configured_by,
            ),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def update_message(self, autorole_id: int, message_id: int) -> None:
        """Atualiza o message_id após enviar a mensagem de button/reaction."""
        await self.db.execute(
            "UPDATE autorole SET message_id = ?, updated_at = datetime('now') WHERE id = ?",
            (message_id, autorole_id),
        )
        await self.db.commit()

    async def toggle(self, autorole_id: int, enabled: bool) -> None:
        """Ativa ou desativa um autorole."""
        await self.db.execute(
            "UPDATE autorole SET enabled = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if enabled else 0, autorole_id),
        )
        await self.db.commit()

    async def delete(self, autorole_id: int) -> None:
        """Remove uma configuração de autorole."""
        await self.db.execute(
            "DELETE FROM autorole WHERE id = ?",
            (autorole_id,),
        )
        await self.db.commit()

    async def delete_all(self, guild_id: int) -> int:
        """Remove todas as configurações de um servidor. Retorna quantidade removida."""
        cursor = await self.db.execute(
            "DELETE FROM autorole WHERE guild_id = ?",
            (guild_id,),
        )
        await self.db.commit()
        return cursor.rowcount
