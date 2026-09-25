from __future__ import annotations

import json
import time

from core.repository import BaseRepository


class OsuRepository(BaseRepository):
    """Repositório para cache de respostas da osu! API v2."""

    async def get_cache(self, key: str) -> dict | list | None:
        """Busca dados no cache. Retorna None se não existir ou expirar."""
        row = await self.db.fetchone(
            "SELECT data, expires_at FROM osu_cache WHERE key = ?",
            (key,)
        )

        if row:
            data_str, expires_at = row["data"], row["expires_at"]
            if time.time() < expires_at:
                return json.loads(data_str)
            else:
                # Remove o item expirado
                await self.db.execute("DELETE FROM osu_cache WHERE key = ?", (key,))
                await self.db.commit()

        return None

    async def set_cache(self, key: str, data: dict | list, ttl_seconds: int = 3600) -> None:
        """Salva dados no cache com TTL."""
        expires_at = time.time() + ttl_seconds
        data_str = json.dumps(data)

        await self.db.execute(
            """
            INSERT INTO osu_cache (key, data, expires_at)
            VALUES (?, ?, ?)
            ON CONFLICT (key) DO UPDATE SET
                data = excluded.data,
                expires_at = excluded.expires_at
            """,
            (key, data_str, expires_at)
        )
        await self.db.commit()

    async def clear_expired(self) -> None:
        """Remove todos os itens expirados do cache."""
        now = time.time()
        await self.db.execute("DELETE FROM osu_cache WHERE expires_at < ?", (now,))
        await self.db.commit()
