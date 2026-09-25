"""
Event Bus System
Internal event system for inter-cog communication.
Allows commands and listeners to emit events that other features react to.

Usage:
    from services.event_bus import event_bus, BotEvent
    
    # Emit event
    await event_bus.emit(BotEvent.USER_LEVELED_UP, guild_id=123, data={'user_id': 456, 'level': 5})
    
    # Listen to event
    @event_bus.on(BotEvent.USER_LEVELED_UP)
    async def on_level_up(guild_id, data):
        ...
"""
import asyncio
import logging
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class BotEvent(Enum):
    """All internal bot events"""
    # User Events
    USER_LEVELED_UP = auto()
    USER_XP_GAINED = auto()
    USER_ROLE_GAINED = auto()
    USER_ROLE_LOST = auto()
    
    # Economy Events
    TRANSACTION_COMPLETED = auto()
    DAILY_CLAIMED = auto()
    GAMBLING_RESULT = auto()
    SHOP_PURCHASE = auto()
    
    # Moderation Events
    WARNING_ISSUED = auto()
    MESSAGES_CLEARED = auto()
    MEMBER_BANNED = auto()
    MEMBER_KICKED = auto()
    
    # Config Events
    CONFIG_CHANGED = auto()
    FEATURE_TOGGLED = auto()
    PREFIX_CHANGED = auto()
    
    # Activity Events
    COMMAND_EXECUTED = auto()
    VOICE_SESSION_START = auto()
    VOICE_SESSION_END = auto()
    MESSAGE_SENT = auto()


class EventBus:
    """
    Central event bus for the bot.
    Singleton pattern - use the global `event_bus` instance.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._listeners: Dict[BotEvent, List[Callable]] = defaultdict(list)
        self._initialized = True
        logger.info("✓ Event bus initialized")
    
    def on(self, event_type: BotEvent):
        """Decorator to register an event listener"""
        def decorator(func: Callable):
            self._listeners[event_type].append(func)
            logger.debug(f"Registered listener for {event_type.name}: {func.__qualname__}")
            return func
        return decorator
    
    def subscribe(self, event_type: BotEvent, callback: Callable):
        """Register a listener programmatically"""
        self._listeners[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type.name}: {callback.__qualname__}")
    
    def unsubscribe(self, event_type: BotEvent, callback: Callable):
        """Remove a listener"""
        if callback in self._listeners[event_type]:
            self._listeners[event_type].remove(callback)
    
    async def emit(self, event_type: BotEvent, guild_id: int = 0, data: Optional[Dict[str, Any]] = None):
        """
        Emit an event to all registered listeners.
        
        Args:
            event_type: The event being emitted
            guild_id: The guild this event is for
            data: Event-specific data dict
        """
        if data is None:
            data = {}
        
        listeners = self._listeners.get(event_type, [])
        if not listeners:
            return
        
        logger.debug(f"Emitting {event_type.name} for guild {guild_id} → {len(listeners)} listener(s)")
        
        for listener in listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(guild_id=guild_id, data=data)
                else:
                    listener(guild_id=guild_id, data=data)
            except Exception as e:
                logger.error(
                    f"Error in event listener {listener.__qualname__} "
                    f"for {event_type.name}: {e}",
                    exc_info=True
                )
    
    def listener_count(self, event_type: BotEvent) -> int:
        """Return number of listeners for an event"""
        return len(self._listeners.get(event_type, []))

    def emit_nowait(self, event_type: BotEvent, guild_id: int = 0, data: Optional[Dict[str, Any]] = None):
        """
        Fire-and-forget emit for sync contexts.
        Schedules the async emit on the running event loop.
        Safe to call from synchronous code running inside an async context.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(event_type, guild_id, data))
        except RuntimeError:
            logger.debug(f"No running loop, skipping emit for {event_type.name}")
    
    @property
    def total_listeners(self) -> int:
        """Total registered listeners across all events"""
        return sum(len(v) for v in self._listeners.values())


# Global singleton
event_bus = EventBus()
