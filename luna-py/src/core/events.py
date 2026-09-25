"""
Sistema de eventos internos do bot.
Permite que comandos emitam eventos que outros módulos escutam.
"""

import asyncio
import enum
import json
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class BotEvent(enum.Enum):
    COMMAND_EXECUTED = "command_executed"
    FEATURE_TOGGLED = "feature_toggled"
    USER_LEVELED_UP = "user_leveled_up"
    WARNING_ISSUED = "warning_issued"
    CONFIG_CHANGED = "config_changed"
    MESSAGE_TRACKED = "message_tracked"
    VOICE_TRACKED = "voice_tracked"
    MEMBER_JOINED = "member_joined"
    MEMBER_LEFT = "member_left"
    AUTOROLE_GIVEN = "autorole_given"
    AUTOROLE_CONFIG = "autorole_config"
    NOTIFICATION_CREATED = "notification_created"
    
    # Community Refactor
    NOTIFICATION_DISPATCH = "notification_dispatch"
    AUTOROLE_DELAYED_GIVE = "autorole_delayed_give"
    
    # Minecraft
    MINECRAFT_CHAT = "minecraft_chat"
    MINECRAFT_DEATH = "minecraft_death"
    MINECRAFT_JOIN = "minecraft_join"
    MINECRAFT_LEAVE = "minecraft_leave"
    MINECRAFT_PLAYER_COMMAND = "minecraft_player_command"
    
    # Giveaways
    GIVEAWAY_CREATED = "giveaway_created"
    GIVEAWAY_ENDED = "giveaway_ended"


Listener = Callable[[int, BotEvent, dict[str, Any]], Coroutine]


class EventBus:
    """Pub/sub interno para eventos do bot."""

    def __init__(self) -> None:
        self._listeners: dict[BotEvent, list[Listener]] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def subscribe(self, event_type: BotEvent, callback: Listener) -> None:
        self._listeners.setdefault(event_type, []).append(callback)
        logger.debug("Listener registrado para %s", event_type.value)

    def unsubscribe(self, event_type: BotEvent, callback: Listener) -> None:
        if event_type in self._listeners:
            try:
                self._listeners[event_type].remove(callback)
            except ValueError:
                pass  # Callback já removido ou nunca registrado

    async def emit(
        self,
        guild_id: int,
        event_type: BotEvent,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emite um evento para todos os listeners registrados (em paralelo)."""
        data = data or {}
        listeners = self._listeners.get(event_type, [])
        if not listeners:
            return
        logger.debug("Evento emitido: %s guild=%s (%d listeners)", event_type.value, guild_id, len(listeners))

        async def _safe_call(cb: Listener) -> None:
            try:
                await cb(guild_id, event_type, data)
            except Exception:
                logger.exception("Erro no listener de %s", event_type.value)

        # Dispara os eventos em background (fire-and-forget)
        for cb in listeners:
            task = asyncio.create_task(_safe_call(cb))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def log_event(
        self, db, guild_id: int, event_type: BotEvent, data: dict
    ) -> None:
        """Persiste evento no banco de dados.

        Nota: não faz commit individual — agrupa com a transação do caller
        ou faz commit no final do ciclo do event loop.
        """
        await db.execute(
            "INSERT INTO event_log (guild_id, event_type, data) VALUES (?, ?, ?)",
            (guild_id, event_type.value, json.dumps(data)),
        )
        await db.commit()
