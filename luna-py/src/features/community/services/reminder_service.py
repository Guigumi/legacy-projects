from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from features.community.repositories.reminder_repository import ReminderRepository

logger = logging.getLogger(__name__)
BRT = ZoneInfo("America/Sao_Paulo")


class ReminderService:
    """Serviço de lógica para agendamento de lembretes."""

    def __init__(self, repo: ReminderRepository) -> None:
        self.repo = repo
        self._task: asyncio.Task | None = None
        self.on_reminder_dispatch = None  # Callback assíncrono injetado pelo Cog

    def start(self) -> None:
        """Inicia o loop de verificação de lembretes."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._check_loop())
            logger.debug("ReminderService: loop iniciado")

    def stop(self) -> None:
        """Para o loop de verificação."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.debug("ReminderService: loop parado")

    async def create_reminder(
        self, user_id: int, channel_id: int, guild_id: int | None, message: str, remind_at: datetime
    ) -> int:
        """Salva um lembrete no banco."""
        remind_at_str = remind_at.astimezone(BRT).isoformat()
        return await self.repo.create(user_id, channel_id, guild_id, message, remind_at_str)

    async def _check_loop(self) -> None:
        """Verifica lembretes pendentes periodicamente."""
        while True:
            try:
                await self._process_pending()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Erro no loop de lembretes")
            await asyncio.sleep(15)

    async def _process_pending(self) -> None:
        """Processa lembretes cuja data e hora já passaram."""
        pending = await self.repo.get_pending()
        now = datetime.now(BRT)

        for rem in pending:
            try:
                remind_at = datetime.fromisoformat(rem["remind_at"])
                if remind_at.tzinfo is None:
                    remind_at = remind_at.replace(tzinfo=BRT)

                if now >= remind_at:
                    if self.on_reminder_dispatch:
                        # Chama o callback registrado no Cog para enviar a mensagem
                        await self.on_reminder_dispatch(rem)
                    await self.repo.mark_notified(rem["id"])
            except Exception:
                logger.exception("Erro ao processar lembrete #%s", rem.get("id"))
