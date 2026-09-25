"""
Repositório de Notificações — CRUD para agendamentos e membros.
"""

from __future__ import annotations

from typing import Optional

from core.repository import BaseRepository


class NotificationRepository(BaseRepository):
    """Acesso a dados das tabelas notifications e notification_members."""

    # ── Notificações ──────────────────────────────────────────

    async def create(
        self,
        guild_id: int,
        channel_id: int,
        creator_id: int,
        title: str,
        scheduled_at: str,
        *,
        description: str | None = None,
        remind_before: int = 0,
    ) -> Optional[int]:
        """Cria uma notificação agendada. Retorna o ID."""
        cursor = await self.db.execute(
            """
            INSERT INTO notifications
                (guild_id, channel_id, creator_id, title, description,
                 scheduled_at, remind_before)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                channel_id,
                creator_id,
                title,
                description,
                scheduled_at,
                remind_before,
            ),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def get(self, notification_id: int) -> dict | None:
        """Retorna uma notificação pelo ID."""
        row = await self.db.fetchone(
            "SELECT * FROM notifications WHERE id = ?",
            (notification_id,),
        )
        return dict(row) if row else None

    async def get_pending(self) -> list[dict]:
        """Retorna todas as notificações pendentes (não notificadas)."""
        rows = await self.db.fetchall(
            "SELECT * FROM notifications WHERE notified = 0 ORDER BY scheduled_at",
        )
        return [dict(r) for r in rows]

    async def get_by_guild(self, guild_id: int) -> list[dict]:
        """Retorna notificações pendentes de um servidor."""
        rows = await self.db.fetchall(
            "SELECT * FROM notifications WHERE guild_id = ? AND notified = 0 ORDER BY scheduled_at",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def get_by_creator(self, guild_id: int, creator_id: int) -> list[dict]:
        """Retorna notificações pendentes de um criador em um servidor."""
        rows = await self.db.fetchall(
            """SELECT * FROM notifications
               WHERE guild_id = ? AND creator_id = ? AND notified = 0
               ORDER BY scheduled_at""",
            (guild_id, creator_id),
        )
        return [dict(r) for r in rows]

    async def mark_notified(self, notification_id: int) -> None:
        """Marca notificação como enviada."""
        await self.db.execute(
            "UPDATE notifications SET notified = 1, updated_at = datetime('now') WHERE id = ?",
            (notification_id,),
        )
        await self.db.commit()

    async def mark_reminded(self, notification_id: int) -> None:
        """Marca que o lembrete prévio foi enviado."""
        await self.db.execute(
            "UPDATE notifications SET reminded = 1, updated_at = datetime('now') WHERE id = ?",
            (notification_id,),
        )
        await self.db.commit()

    async def update_remind_before(self, notification_id: int, minutes: int) -> None:
        """Atualiza os minutos de lembrete prévio."""
        await self.db.execute(
            "UPDATE notifications SET remind_before = ?, reminded = 0, updated_at = datetime('now') WHERE id = ?",
            (minutes, notification_id),
        )
        await self.db.commit()

    async def update(
        self,
        notification_id: int,
        title: str,
        scheduled_at: str,
        *,
        description: str | None = None,
        remind_before: int = 0,
    ) -> None:
        """Atualiza campos básicos de uma notificação."""
        await self.db.execute(
            """
            UPDATE notifications
               SET title = ?, description = ?, scheduled_at = ?, remind_before = ?, reminded = 0,
                   updated_at = datetime('now')
             WHERE id = ?
            """,
            (title, description, scheduled_at, remind_before, notification_id),
        )
        await self.db.commit()

    async def delete(self, notification_id: int) -> None:
        """Remove uma notificação."""
        await self.db.execute(
            "DELETE FROM notifications WHERE id = ?",
            (notification_id,),
        )
        await self.db.commit()

    # ── Membros ───────────────────────────────────────────────

    async def add_member(self, notification_id: int, user_id: int) -> None:
        """Adiciona um membro para ser mencionado."""
        await self.db.execute(
            """
            INSERT OR IGNORE INTO notification_members (notification_id, user_id)
            VALUES (?, ?)
            """,
            (notification_id, user_id),
        )
        await self.db.commit()

    async def remove_member(self, notification_id: int, user_id: int) -> None:
        """Remove um membro da lista de menções."""
        await self.db.execute(
            "DELETE FROM notification_members WHERE notification_id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        await self.db.commit()

    async def get_members(self, notification_id: int) -> list[dict]:
        """Retorna todos os membros de uma notificação."""
        rows = await self.db.fetchall(
            "SELECT * FROM notification_members WHERE notification_id = ?",
            (notification_id,),
        )
        return [dict(r) for r in rows]

    async def get_active_members(self, notification_id: int) -> list[dict]:
        """Retorna membros que NÃO optaram por sair."""
        rows = await self.db.fetchall(
            "SELECT * FROM notification_members WHERE notification_id = ? AND opted_out = 0",
            (notification_id,),
        )
        return [dict(r) for r in rows]

    async def opt_out(self, notification_id: int, user_id: int) -> bool:
        """Membro opta por não ser mencionado. Retorna True se existia."""
        row = await self.db.fetchone(
            "SELECT 1 FROM notification_members WHERE notification_id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        if not row:
            return False
        await self.db.execute(
            "UPDATE notification_members SET opted_out = 1 WHERE notification_id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        await self.db.commit()
        return True

    async def opt_in(self, notification_id: int, user_id: int) -> bool:
        """Membro volta a aceitar menção. Retorna True se existia."""
        row = await self.db.fetchone(
            "SELECT 1 FROM notification_members WHERE notification_id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        if not row:
            return False
        await self.db.execute(
            "UPDATE notification_members SET opted_out = 0 WHERE notification_id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        await self.db.commit()
        return True
