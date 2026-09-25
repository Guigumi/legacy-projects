"""
Lógica de negócio do sistema de AutoRole.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from core.events import BotEvent, EventBus
from core.enums import AutoRoleMode
from features.community.repositories import AutoRoleRepository

logger = logging.getLogger(__name__)


class AutoRoleService:
    """Gerencia a lógica de entrega de cargos automáticos."""

    def __init__(self, repo: AutoRoleRepository, event_bus: EventBus) -> None:
        self.repo = repo
        self.bus = event_bus
        self._pending_tasks: dict[tuple[int, int], asyncio.Task] = {}

    # ── Config ────────────────────────────────────────────────

    async def get_autoroles(self, guild_id: int) -> list[dict]:
        return await self.repo.get_autoroles(guild_id)

    async def get_all(self, guild_id: int) -> list[dict]:
        return await self.repo.get_by_guild(guild_id)

    async def get_by_message(self, message_id: int) -> dict | None:
        return await self.repo.get_by_message(message_id)

    async def create_autorole(
        self,
        guild_id: int,
        role_id: int,
        mode: AutoRoleMode,
        configured_by: int,
        **kwargs,
    ) -> int:
        """Cria autorole e emite evento. Retorna ID."""
        autorole_id = await self.repo.create(
            guild_id,
            role_id,
            mode.value,
            configured_by,
            **kwargs,
        )
        await self.bus.emit(
            guild_id,
            BotEvent.AUTOROLE_CONFIG,
            {
                "action": "created",
                "autorole_id": autorole_id,
                "mode": mode.value,
                "role_id": role_id,
                "configured_by": configured_by,
            },
        )
        return autorole_id

    async def update_message_id(self, autorole_id: int, message_id: int) -> None:
        await self.repo.update_message(autorole_id, message_id)

    async def toggle_autorole(self, autorole_id: int, enabled: bool) -> None:
        await self.repo.toggle(autorole_id, enabled)

    async def delete_autorole(self, autorole_id: int) -> None:
        await self.repo.delete(autorole_id)

    async def delete_all(self, guild_id: int) -> int:
        return await self.repo.delete_all(guild_id)

    async def record_role_given(self, guild_id: int, user_id: int, role_id: int) -> None:
        """Registra que um cargo foi dado e emite evento."""
        await self.bus.emit(
            guild_id,
            BotEvent.AUTOROLE_GIVEN,
            {"user_id": user_id, "role_id": role_id},
        )
        logger.info(
            "AutoRole registrado: %s -> role %s em guild %s",
            user_id,
            role_id,
            guild_id,
        )

    # ── Timer ─────────────────────────────────────────────────

    def schedule_delayed_role(
        self, guild_id: int, user_id: int, role_id: int, delay: int
    ) -> None:
        """Agenda entrega de cargo após X segundos."""
        key = (guild_id, user_id)

        # Cancela task anterior se existir
        existing = self._pending_tasks.pop(key, None)
        if existing and not existing.done():
            existing.cancel()

        async def _delayed():
            await asyncio.sleep(delay)
            await self.bus.emit(
                guild_id,
                BotEvent.AUTOROLE_DELAYED_GIVE,
                {"user_id": user_id, "role_id": role_id, "delay": delay},
            )
            self._pending_tasks.pop(key, None)

        task = asyncio.create_task(_delayed())
        self._pending_tasks[key] = task

    def cancel_pending(self, guild_id: int, user_id: int) -> None:
        """Cancela entrega pendente (ex: membro saiu antes do timer)."""
        key = (guild_id, user_id)
        task = self._pending_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()
            logger.debug(
                "Timer de autorole cancelado: user %s guild %s", user_id, guild_id
            )
