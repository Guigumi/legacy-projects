"""
Serviço de integração com a API v2 do osu!
Autenticação via OAuth2 client credentials.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from features.fun.repositories.osu_repository import OsuRepository

logger = logging.getLogger(__name__)

OSU_TOKEN_URL = "https://osu.ppy.sh/oauth/token"
OSU_API_BASE = "https://osu.ppy.sh/api/v2"

# Modos de jogo do osu!
OSU_MODES = {
    "osu": "osu",
    "taiko": "taiko",
    "fruits": "fruits",
    "mania": "mania",
    # Aliases comuns
    "std": "osu",
    "standard": "osu",
    "catch": "fruits",
    "ctb": "fruits",
}

# Nomes legíveis
MODE_DISPLAY = {
    "osu": "osu!standard",
    "taiko": "osu!taiko",
    "fruits": "osu!catch",
    "mania": "osu!mania",
}

# Emojis por modo
MODE_EMOJI = {
    "osu": "🎵",
    "taiko": "🥁",
    "fruits": "🍎",
    "mania": "⌨️",
}


class OsuService:
    """Cliente async para a osu! API v2."""

    def __init__(self, client_id: int, client_secret: str, repo: OsuRepository) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.repo = repo
        self._token: str | None = None
        self._token_expires: float = 0
        self._session: aiohttp.ClientSession | None = None

        # Cache em memória: key -> (data, timestamp)
        self._memory_cache: dict[str, tuple[Any, float]] = {}
        self._cache_ttl = 600.0  # 10 minutos de cache em RAM

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _ensure_token(self) -> str:
        """Obtém ou renova o token OAuth2."""
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        session = await self._get_session()
        async with session.post(
            OSU_TOKEN_URL,
            json={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
                "scope": "public",
            },
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error("osu! OAuth falhou: %s %s", resp.status, text)
                raise RuntimeError("Falha na autenticação com a osu! API")

            data = await resp.json()
            self._token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 86400)
            logger.debug("osu! token renovado, expira em %ss", data.get("expires_in"))
            return self._token

    async def _request(
        self, endpoint: str, params: dict | None = None
    ) -> dict | list | None:
        """Faz request autenticada à API."""
        token = await self._ensure_token()
        session = await self._get_session()
        url = f"{OSU_API_BASE}{endpoint}"
        headers = {"Authorization": f"Bearer {token}"}

        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 404:
                return None
            if resp.status != 200:
                text = await resp.text()
                logger.warning("osu! API %s → %s: %s", endpoint, resp.status, text)
                return None
            return await resp.json()

    async def get_user(self, username: str, mode: str | None = None) -> dict | None:
        """Busca dados de um jogador. Mode opcional (osu, taiko, fruits, mania)."""
        cache_key = f"osu_user_{username.lower()}_{mode or 'none'}"
        
        # 1. Tentar cache em memória (RAM)
        now = time.time()
        if cache_key in self._memory_cache:
            data, ts = self._memory_cache[cache_key]
            if now - ts < self._cache_ttl:
                return data

        # 2. Tentar cache persistente (SQLite)
        cached = await self.repo.get_cache(cache_key)
        if cached is not None:
            self._memory_cache[cache_key] = (cached, now)
            return cached

        endpoint = f"/users/{username}/{mode}" if mode else f"/users/{username}"
        data = await self._request(endpoint, params={"key": "username"})

        if data and isinstance(data, dict):
            # Cache por 1 hora no banco e 10 min em RAM
            await self.repo.set_cache(cache_key, data, ttl_seconds=3600)
            self._memory_cache[cache_key] = (data, now)
            return data
        return None

    async def get_user_best(
        self, user_id: int, mode: str | None = None, limit: int = 5
    ) -> list[dict]:
        """Busca as melhores scores (top PP) de um jogador."""
        cache_key = f"osu_best_{user_id}_{mode or 'none'}_{limit}"
        
        now = time.time()
        if cache_key in self._memory_cache:
            data, ts = self._memory_cache[cache_key]
            if now - ts < self._cache_ttl:
                return data

        cached = await self.repo.get_cache(cache_key)
        if cached is not None and isinstance(cached, list):
            self._memory_cache[cache_key] = (cached, now)
            return cached

        endpoint = f"/users/{user_id}/scores/best"
        params: dict[str, Any] = {"limit": limit}
        if mode:
            params["mode"] = mode
        data = await self._request(endpoint, params=params)

        if data and isinstance(data, list):
            # Cache por 1 hora no banco e 10 min em RAM
            await self.repo.set_cache(cache_key, data, ttl_seconds=3600)
            self._memory_cache[cache_key] = (data, now)
            return data
        return []

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    @staticmethod
    def resolve_mode(mode_input: str | None) -> str | None:
        """Resolve alias de modo para o valor da API."""
        if not mode_input:
            return None
        return OSU_MODES.get(mode_input.lower())
