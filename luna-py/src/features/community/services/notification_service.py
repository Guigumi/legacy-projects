"""
Lógica de negócio do sistema de Notificações.
Gerencia agendamento, lembretes prévios e disparo de menções.
As datas são armazenadas em ISO-8601 no banco e comparadas no fuso de Brasília.
O loop recarrega do banco a cada ciclo, garantindo persistência após restart.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from config.settings import BRT
from core.events import BotEvent, EventBus
from features.community.repositories import NotificationRepository

logger = logging.getLogger(__name__)

# Intervalo do loop de verificação (segundos)
CHECK_INTERVAL = 15


def _parse_iso_brt(iso: str) -> datetime:
    """Parse ISO string do banco, retorna datetime aware no fuso de Brasília."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BRT)
    return dt.astimezone(BRT)


class NotificationService:
    """Gerencia agendamento e disparo de notificações."""

    def __init__(self, repo: NotificationRepository, event_bus: EventBus) -> None:
        self.repo = repo
        self.bus = event_bus
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Inicia o loop de verificação de notificações."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._check_loop())
            logger.debug("NotificationService: loop iniciado")

    def stop(self) -> None:
        """Para o loop de verificação."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.debug("NotificationService: loop parado")

    # ── CRUD via repo ─────────────────────────────────────────

    async def create_notification(
        self,
        guild_id: int,
        channel_id: int,
        creator_id: int,
        title: str,
        scheduled_at: str,
        *,
        description: str | None = None,
        remind_before: int = 0,
    ) -> int:
        """Cria notificação e retorna o ID."""
        notif_id = await self.repo.create(
            guild_id,
            channel_id,
            creator_id,
            title,
            scheduled_at,
            description=description,
            remind_before=remind_before,
        )
        await self.bus.emit(
            guild_id,
            BotEvent.NOTIFICATION_CREATED,
            {
                "notification_id": notif_id,
                "creator_id": creator_id,
                "title": title,
                "scheduled_at": scheduled_at,
            },
        )
        return notif_id

    async def get_notification(self, notification_id: int) -> dict | None:
        return await self.repo.get(notification_id)

    async def get_by_guild(self, guild_id: int) -> list[dict]:
        return await self.repo.get_by_guild(guild_id)

    async def get_by_creator(self, guild_id: int, creator_id: int) -> list[dict]:
        return await self.repo.get_by_creator(guild_id, creator_id)

    async def delete_notification(self, notification_id: int) -> None:
        await self.repo.delete(notification_id)

    async def update_remind_before(self, notification_id: int, minutes: int) -> None:
        await self.repo.update_remind_before(notification_id, minutes)

    async def update_notification(
        self,
        notification_id: int,
        title: str,
        scheduled_at: str,
        *,
        description: str | None = None,
        remind_before: int = 0,
    ) -> None:
        """Atualiza as informações de uma notificação."""
        await self.repo.update(
            notification_id,
            title,
            scheduled_at,
            description=description,
            remind_before=remind_before,
        )

    # ── Membros ───────────────────────────────────────────────

    async def add_member(self, notification_id: int, user_id: int) -> None:
        await self.repo.add_member(notification_id, user_id)

    async def remove_member(self, notification_id: int, user_id: int) -> None:
        await self.repo.remove_member(notification_id, user_id)

    async def get_members(self, notification_id: int) -> list[dict]:
        return await self.repo.get_members(notification_id)

    async def get_active_members(self, notification_id: int) -> list[dict]:
        return await self.repo.get_active_members(notification_id)

    async def opt_out(self, notification_id: int, user_id: int) -> bool:
        return await self.repo.opt_out(notification_id, user_id)

    async def opt_in(self, notification_id: int, user_id: int) -> bool:
        return await self.repo.opt_in(notification_id, user_id)

    # ── Loop de verificação ───────────────────────────────────

    async def _check_loop(self) -> None:
        """Loop que verifica periodicamente notificações pendentes."""
        while True:
            try:
                await self._process_pending()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Erro no loop de notificações")
            await asyncio.sleep(CHECK_INTERVAL)

    async def _process_pending(self) -> None:
        """Processa notificações cuja hora já chegou ou cujo lembrete deve ser enviado."""
        pending = await self.repo.get_pending()
        now = datetime.now(BRT)

        for notif in pending:
            scheduled = _parse_iso_brt(notif["scheduled_at"])

            # ── Lembrete prévio ───────────────────────────────
            remind_min = notif.get("remind_before", 0)
            if remind_min > 0 and not notif["reminded"]:
                remind_at = scheduled - timedelta(minutes=remind_min)
                if now >= remind_at:
                    await self._send_reminder(notif, remind_min)

            # ── Notificação final ─────────────────────────────
            if now >= scheduled:
                await self._send_notification(notif)

    async def _send_reminder(self, notif: dict, minutes: int) -> None:
        """Emite evento de lembrete prévio."""
        await self.bus.emit(
            notif["guild_id"],
            BotEvent.NOTIFICATION_DISPATCH,
            {"type": "reminder", "notification": notif, "minutes": minutes},
        )
        await self.repo.mark_reminded(notif["id"])

    async def _send_notification(self, notif: dict) -> None:
        """Emite evento de notificação final."""
        await self.bus.emit(
            notif["guild_id"],
            BotEvent.NOTIFICATION_DISPATCH,
            {"type": "final", "notification": notif},
        )
        await self.repo.mark_notified(notif["id"])

    async def build_mentions(self, notif: dict) -> str:
        """Monta a string de menções (criador + membros que não optaram sair)."""
        user_ids: set[int] = {notif["creator_id"]}
        active = await self.repo.get_active_members(notif["id"])
        for m in active:
            user_ids.add(m["user_id"])
        return " ".join(f"<@{uid}>" for uid in user_ids)
