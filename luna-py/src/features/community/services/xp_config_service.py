"""
Serviço de configuração de XP.
Lógica de negócio para ajustes de XP, boost, canais e cargos por nível.

Otimizações aplicadas:
- Cache TTL em memória para config base, channel configs e boost roles.
  Evita queries ao banco a cada mensagem/evento de voz (hot path).
- Fórmula de nível unificada com user_service.xp_for_level().
- Invalidação de cache automática ao alterar configurações.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.events import BotEvent, EventBus
from core.utils.xp_calc import xp_for_level
from features.community.repositories import XPConfigRepository

logger = logging.getLogger(__name__)

# Defaults usados quando não há config no banco
DEFAULT_XP_CONFIG = {
    "xp_per_level": 100,
    "xp_per_message": 5,
    "xp_per_voice_min": 3,
    "xp_per_reaction": 2,
}

# TTL do cache em segundos (5 minutos — balanceia frescor vs performance)
_CACHE_TTL = 300.0


class _TTLCache:
    """Cache simples em memória com TTL por chave.

    Armazena pares (valor, timestamp) e invalida automaticamente
    entradas expiradas. Sem dependências externas.
    """

    __slots__ = ("_store", "_ttl")

    def __init__(self, ttl: float = _CACHE_TTL) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl

    def get(self, key: str) -> Any | None:
        """Retorna valor se existir e não estiver expirado, senão None."""
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        """Armazena valor com timestamp atual."""
        self._store[key] = (value, time.monotonic())

    def invalidate(self, key: str) -> None:
        """Remove entrada específica do cache."""
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        """Remove todas as entradas cujo key começa com prefix."""
        keys_to_remove = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._store[k]

    def clear(self) -> None:
        """Limpa todo o cache."""
        self._store.clear()


class XPConfigService:
    """Serviço de configuração de XP por servidor."""

    def __init__(self, xp_config_repo: XPConfigRepository, event_bus: EventBus) -> None:
        self.repo = xp_config_repo
        self.bus = event_bus
        self._cache = _TTLCache(ttl=_CACHE_TTL)

    # ── Cache Keys ────────────────────────────────────────────

    @staticmethod
    def _config_key(guild_id: int) -> str:
        return f"cfg:{guild_id}"

    @staticmethod
    def _channels_key(guild_id: int) -> str:
        return f"ch:{guild_id}"

    @staticmethod
    def _channel_key(guild_id: int, channel_id: int) -> str:
        return f"ch:{guild_id}:{channel_id}"

    @staticmethod
    def _boost_roles_key(guild_id: int) -> str:
        return f"br:{guild_id}"

    @staticmethod
    def _level_roles_key(guild_id: int) -> str:
        return f"lr:{guild_id}"

    def _invalidate_guild(self, guild_id: int) -> None:
        """Invalida todo o cache de uma guild."""
        prefix = f"cfg:{guild_id}"
        self._cache.invalidate(prefix)
        self._cache.invalidate_prefix(f"ch:{guild_id}")
        self._cache.invalidate_prefix(f"br:{guild_id}")
        self._cache.invalidate_prefix(f"lr:{guild_id}")

    # ── Config Base ───────────────────────────────────────────

    async def get_config(self, guild_id: int) -> dict:
        """Retorna config de XP do servidor (com defaults).

        Resultado é cacheado por _CACHE_TTL segundos para evitar
        query ao banco em cada mensagem/evento de voz.
        """
        key = self._config_key(guild_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        config = await self.repo.get_config(guild_id)
        result = {**DEFAULT_XP_CONFIG}
        if config:
            result.update({k: v for k, v in config.items() if v is not None})

        self._cache.set(key, result)
        return result

    async def update_config(self, guild_id: int, changed_by: int, **kwargs) -> None:
        """Atualiza config de XP e invalida cache."""
        await self.repo.update_config(guild_id, **kwargs)
        self._cache.invalidate(self._config_key(guild_id))
        await self.bus.emit(
            guild_id,
            BotEvent.CONFIG_CHANGED,
            {
                "changed_by": changed_by,
                "fields": list(kwargs.keys()),
                "scope": "xp_config",
            },
        )

    # ── XP Calculation ────────────────────────────────────────

    async def calculate_xp(
        self,
        guild_id: int,
        base_xp: int,
        action: str,
        channel_id: int | None = None,
        member_role_ids: list[int] | None = None,
    ) -> int:
        """Calcula XP final considerando boost de canal e cargo.

        Usa cache para channel config e boost roles, evitando queries
        no hot path (cada mensagem enviada / minuto em call).
        """
        # Verificar se canal está bloqueado ou tem boost
        if channel_id:
            ch_config = await self._get_channel_config_cached(guild_id, channel_id)
            if ch_config:
                if ch_config["mode"] == "blocked":
                    return 0  # Canal bloqueado, sem XP
                elif ch_config["mode"] == "boost":
                    base_xp = int(base_xp * ch_config["multiplier"])

        # Aplicar boost de cargo (usa o maior multiplicador)
        if member_role_ids:
            boost_roles = await self._get_boost_roles_cached(guild_id)
            if boost_roles:
                # Converter role_ids para set para lookup O(1)
                role_set = set(member_role_ids)
                max_multiplier = 1.0
                for br in boost_roles:
                    if br["role_id"] in role_set:
                        max_multiplier = max(max_multiplier, br["multiplier"])
                if max_multiplier > 1.0:
                    base_xp = int(base_xp * max_multiplier)

        return base_xp

    async def _get_channel_config_cached(
        self, guild_id: int, channel_id: int
    ) -> dict | None:
        """Retorna config de canal com cache."""
        key = self._channel_key(guild_id, channel_id)
        cached = self._cache.get(key)
        if cached is not None:
            # Usamos _SENTINEL para diferenciar "cacheado como None" de "não cacheado"
            return cached if cached is not _SENTINEL else None

        result = await self.repo.get_channel_config(guild_id, channel_id)
        self._cache.set(key, result if result is not None else _SENTINEL)
        return result

    async def _get_boost_roles_cached(self, guild_id: int) -> list[dict]:
        """Retorna boost roles com cache."""
        key = self._boost_roles_key(guild_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        result = await self.repo.get_boost_roles(guild_id)
        self._cache.set(key, result)
        return result

    async def get_xp_for_action(self, guild_id: int, action: str) -> int:
        """Retorna XP base por ação (message, voice, reaction).

        Usa get_config() que já é cacheado.
        """
        config = await self.get_config(guild_id)
        mapping = {
            "message": config.get("xp_per_message", 5),
            "voice": config.get("xp_per_voice_min", 3),
            "reaction": config.get("xp_per_reaction", 2),
        }
        return mapping.get(action, 0)

    def xp_for_level(self, level: int, xp_per_level: int = 100) -> int:
        """XP total necessário para alcançar um nível."""
        return xp_for_level(level, xp_per_level)

    # ── Channel Config ────────────────────────────────────────

    async def get_channel_configs(self, guild_id: int) -> list[dict]:
        key = self._channels_key(guild_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        result = await self.repo.get_channel_configs(guild_id)
        self._cache.set(key, result)
        return result

    async def set_channel_blocked(self, guild_id: int, channel_id: int) -> None:
        await self.repo.set_channel_config(guild_id, channel_id, "blocked", 0.0)
        self._cache.invalidate_prefix(f"ch:{guild_id}")

    async def set_channel_boost(
        self, guild_id: int, channel_id: int, multiplier: float
    ) -> None:
        await self.repo.set_channel_config(guild_id, channel_id, "boost", multiplier)
        self._cache.invalidate_prefix(f"ch:{guild_id}")

    async def remove_channel_config(self, guild_id: int, channel_id: int) -> None:
        await self.repo.remove_channel_config(guild_id, channel_id)
        self._cache.invalidate_prefix(f"ch:{guild_id}")

    # ── Boost Roles ───────────────────────────────────────────

    async def get_boost_roles(self, guild_id: int) -> list[dict]:
        return await self._get_boost_roles_cached(guild_id)

    async def set_boost_role(
        self, guild_id: int, role_id: int, multiplier: float
    ) -> None:
        await self.repo.set_boost_role(guild_id, role_id, multiplier)
        self._cache.invalidate(self._boost_roles_key(guild_id))

    async def remove_boost_role(self, guild_id: int, role_id: int) -> None:
        await self.repo.remove_boost_role(guild_id, role_id)
        self._cache.invalidate(self._boost_roles_key(guild_id))

    # ── Level Roles ───────────────────────────────────────────

    async def get_level_roles(self, guild_id: int) -> list[dict]:
        key = self._level_roles_key(guild_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        result = await self.repo.get_level_roles(guild_id)
        self._cache.set(key, result)
        return result

    async def set_level_role(self, guild_id: int, level: int, role_id: int) -> None:
        await self.repo.set_level_role(guild_id, level, role_id)
        self._cache.invalidate(self._level_roles_key(guild_id))

    async def remove_level_role(self, guild_id: int, level: int, role_id: int) -> None:
        await self.repo.remove_level_role(guild_id, level, role_id)
        self._cache.invalidate(self._level_roles_key(guild_id))

    async def get_roles_for_level(self, guild_id: int, level: int) -> list[int]:
        return await self.repo.get_roles_for_level(guild_id, level)

    async def get_roles_for_level_range(
        self, guild_id: int, min_level: int, max_level: int
    ) -> list[dict]:
        """Returns roles for a level range, using cache if available."""
        cached_all = self._cache.get(self._level_roles_key(guild_id))
        if cached_all is not None:
            # Filter from cache (all level roles)
            return [
                lr for lr in cached_all if min_level <= lr["level"] <= max_level
            ]

        # Not fully cached or specific jump - fetch from repo
        return await self.repo.get_roles_for_level_range(guild_id, min_level, max_level)

    async def get_all_roles_up_to_level(self, guild_id: int, level: int) -> list[dict]:
        return await self.repo.get_all_roles_up_to_level(guild_id, level)


# Sentinel para diferenciar "valor None cacheado" de "não está no cache"
_SENTINEL = object()
