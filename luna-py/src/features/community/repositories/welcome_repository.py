"""
Repositório de configuração de boas-vindas (Welcome).
Gerencia a tabela welcome_config.
"""

from __future__ import annotations

import logging

from core.repository import BaseRepository

logger = logging.getLogger(__name__)


class WelcomeRepository(BaseRepository):
    """Acesso à configuração de welcome no banco."""

    _VALID_CONFIG_FIELDS = {
        "channel_id",
        "content",
        "embed_title",
        "embed_description",
        "embed_color",
        "embed_thumbnail",
        "embed_image",
        "embed_footer_text",
        "embed_footer_icon",
        "embed_author_name",
        "embed_author_icon",
        "welcome_emoji",
        "enabled",
        "updated_at",
    }

    async def ensure_guild(self, guild_id: int, event_type: str) -> None:
        """Garante que a config do servidor exista na tabela welcome_config."""
        await self.db.execute(
            "INSERT OR IGNORE INTO welcome_config (guild_id, event_type) VALUES (?, ?)",
            (guild_id, event_type),
        )
        await self.db.commit()

    async def get_config(self, guild_id: int, event_type: str) -> dict | None:
        """Retorna configuração de welcome do servidor."""
        await self.ensure_guild(guild_id, event_type)
        row = await self.db.fetchone(
            "SELECT * FROM welcome_config WHERE guild_id = ? AND event_type = ?",
            (guild_id, event_type),
        )
        return dict(row) if row else None

    async def update_config(self, guild_id: int, event_type: str, **kwargs) -> None:
        """Atualiza campos específicos da configuração de welcome."""
        if not kwargs:
            return

        invalid = set(kwargs) - self._VALID_CONFIG_FIELDS
        if invalid:
            logger.warning("WelcomeRepository.update_config: campos inválidos: %s", invalid)
            kwargs = {k: v for k, v in kwargs.items() if k in self._VALID_CONFIG_FIELDS}
            if not kwargs:
                return

        await self.ensure_guild(guild_id, event_type)

        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [guild_id, event_type]

        await self.db.execute(
            f"UPDATE welcome_config SET {set_clause}, updated_at = datetime('now') WHERE guild_id = ? AND event_type = ?",
            tuple(values),
        )
        await self.db.commit()
