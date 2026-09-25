"""
Lógica de negócio para configuração de servidores.
"""

from __future__ import annotations

import logging
import time

from core.events import BotEvent, EventBus
from core.enums import Feature
from features.community.repositories import GuildRepository

logger = logging.getLogger(__name__)

# TTL do cache em segundos — curto o suficiente para refletir mudanças
# rapidamente, longo o suficiente para evitar queries a cada mensagem.
_CACHE_TTL = 300.0


class GuildService:
    """Serviço de configuração por servidor."""

    def __init__(self, guild_repo: GuildRepository, event_bus: EventBus) -> None:
        self.repo = guild_repo
        self.bus = event_bus

        # Cache leve: guild_id → (dict, timestamp)
        self._config_cache: dict[int, tuple[dict, float]] = {}
        # Cache de features desabilitadas: guild_id → (set[str], timestamp)
        self._disabled_cache: dict[int, tuple[set[str], float]] = {}

    def _invalidate(self, guild_id: int) -> None:
        """Invalida caches de uma guild após escrita."""
        self._config_cache.pop(guild_id, None)
        self._disabled_cache.pop(guild_id, None)

    async def get_config(self, guild_id: int) -> dict:
        now = time.monotonic()
        cached = self._config_cache.get(guild_id)
        if cached and (now - cached[1]) < _CACHE_TTL:
            return cached[0]

        config = await self.repo.get_config(guild_id)
        if config is not None:
            self._config_cache[guild_id] = (config, now)
        return config

    async def update_config(self, guild_id: int, changed_by: int, **kwargs) -> None:
        await self.repo.update_config(guild_id, **kwargs)
        self._invalidate(guild_id)
        await self.bus.emit(
            guild_id,
            BotEvent.CONFIG_CHANGED,
            {"changed_by": changed_by, "fields": list(kwargs.keys())},
        )

    # ── Feature Toggle ────────────────────────────────────────

    async def _get_disabled_set(self, guild_id: int) -> set[str]:
        """Retorna o set de features desabilitadas (com cache)."""
        now = time.monotonic()
        cached = self._disabled_cache.get(guild_id)
        if cached and (now - cached[1]) < _CACHE_TTL:
            return cached[0]

        disabled = set(await self.repo.get_disabled_features(guild_id))
        self._disabled_cache[guild_id] = (disabled, now)
        return disabled

    async def is_feature_enabled(self, guild_id: int, feature: Feature) -> bool:
        disabled = await self._get_disabled_set(guild_id)
        return feature.value not in disabled

    async def toggle_feature(
        self, guild_id: int, feature: Feature, enable: bool, toggled_by: int
    ) -> bool:
        """Ativa/desativa feature. Retorna novo estado (True=ativada)."""
        if enable:
            await self.repo.enable_feature(guild_id, feature.value)
        else:
            await self.repo.disable_feature(guild_id, feature.value, toggled_by)

        self._invalidate(guild_id)

        await self.bus.emit(
            guild_id,
            BotEvent.FEATURE_TOGGLED,
            {"feature": feature.value, "enabled": enable, "toggled_by": toggled_by},
        )
        logger.info(
            "Feature %s %s in guild %s by %s",
            feature.value,
            "enabled" if enable else "disabled",
            guild_id,
            toggled_by,
        )
        return enable

    async def get_disabled_features(self, guild_id: int) -> list[str]:
        disabled = await self._get_disabled_set(guild_id)
        return list(disabled)

    # ── Log Categories ────────────────────────────────────────

    async def is_log_category_enabled(self, guild_id: int, category: str) -> bool:
        return not await self.repo.is_log_category_disabled(guild_id, category)

    async def toggle_log_category(
        self, guild_id: int, category: str, enable: bool, toggled_by: int
    ) -> bool:
        if enable:
            await self.repo.enable_log_category(guild_id, category)
        else:
            await self.repo.disable_log_category(guild_id, category, toggled_by)
        return enable

    async def get_disabled_log_categories(self, guild_id: int) -> list[str]:
        return await self.repo.get_disabled_log_categories(guild_id)

    # ── Welcome ───────────────────────────────────────────────

    async def set_welcome(
        self, guild_id: int, channel_id: int, message: str, set_by: int
    ) -> None:
        await self.repo.set_welcome(guild_id, channel_id, message)
        await self.bus.emit(
            guild_id,
            BotEvent.CONFIG_CHANGED,
            {"changed_by": set_by, "fields": ["welcome_channel", "welcome_message"]},
        )

    async def disable_welcome(self, guild_id: int) -> None:
        await self.repo.disable_welcome(guild_id)
