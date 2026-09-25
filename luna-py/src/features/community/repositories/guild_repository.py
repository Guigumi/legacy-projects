"""
Repositório de configuração por servidor.
Gerencia guild_config e disabled_features.
"""

from __future__ import annotations

import logging

from core.repository import BaseRepository

logger = logging.getLogger(__name__)


class GuildRepository(BaseRepository):
    """Acesso a configuração de servidor no banco."""

    _VALID_CONFIG_FIELDS = {
        "prefix",
        "welcome_enabled",
        "welcome_channel",
        "welcome_message",
        "log_channel",
        "locale",
        "minecraft_channel",
        "updated_at",
    }

    async def ensure_guild(self, guild_id: int) -> None:
        """Garante que a config do servidor exista."""
        cursor = await self.db.execute(
            "INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)",
            (guild_id,),
        )
        if cursor.rowcount > 0:
            # Servidor novo: sistema de XP desativado por padrão
            await self.db.execute(
                "INSERT INTO disabled_features (guild_id, feature_name, disabled_by) VALUES (?, ?, ?)",
                (guild_id, "leveling", 0),
            )
        await self.db.commit()

    async def get_config(self, guild_id: int) -> dict | None:
        """Retorna configuração do servidor."""
        await self.ensure_guild(guild_id)
        row = await self.db.fetchone(
            "SELECT * FROM guild_config WHERE guild_id = ?",
            (guild_id,),
        )
        return dict(row) if row else None

    async def update_config(self, guild_id: int, **kwargs) -> None:
        """Atualiza campos específicos da configuração."""
        if not kwargs:
            return
        # Validar campos contra whitelist
        invalid = set(kwargs) - self._VALID_CONFIG_FIELDS
        if invalid:
            logger.warning("update_config: campos inválidos ignorados: %s", invalid)
            kwargs = {k: v for k, v in kwargs.items() if k in self._VALID_CONFIG_FIELDS}
            if not kwargs:
                return
        await self.ensure_guild(guild_id)

        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [guild_id]

        await self.db.execute(
            f"UPDATE guild_config SET {set_clause}, updated_at = datetime('now') WHERE guild_id = ?",
            tuple(values),
        )
        await self.db.commit()

    # ── Features ──────────────────────────────────────────────

    async def is_feature_disabled(self, guild_id: int, feature_name: str) -> bool:
        """Verifica se uma feature está desativada no servidor."""
        row = await self.db.fetchone(
            "SELECT 1 FROM disabled_features WHERE guild_id = ? AND feature_name = ?",
            (guild_id, feature_name),
        )
        return row is not None

    async def disable_feature(
        self, guild_id: int, feature_name: str, disabled_by: int
    ) -> None:
        """Desativa uma feature no servidor (memória de decisão)."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO disabled_features (guild_id, feature_name, disabled_by)
            VALUES (?, ?, ?)
            """,
            (guild_id, feature_name, disabled_by),
        )
        await self.db.commit()

    async def enable_feature(self, guild_id: int, feature_name: str) -> None:
        """Reativa uma feature no servidor."""
        await self.db.execute(
            "DELETE FROM disabled_features WHERE guild_id = ? AND feature_name = ?",
            (guild_id, feature_name),
        )
        await self.db.commit()

    async def get_disabled_features(self, guild_id: int) -> list[str]:
        """Lista todas as features desativadas no servidor."""
        rows = await self.db.fetchall(
            "SELECT feature_name FROM disabled_features WHERE guild_id = ?",
            (guild_id,),
        )
        return [row["feature_name"] for row in rows]

    # ── Welcome ───────────────────────────────────────────────

    async def set_welcome(self, guild_id: int, channel_id: int, message: str) -> None:
        """Configura mensagem de boas-vindas."""
        await self.update_config(
            guild_id,
            welcome_enabled=1,
            welcome_channel=channel_id,
            welcome_message=message,
        )

    async def disable_welcome(self, guild_id: int) -> None:
        await self.update_config(guild_id, welcome_enabled=0)

    # ── Log Categories ────────────────────────────────────────

    async def is_log_category_disabled(self, guild_id: int, category: str) -> bool:
        row = await self.db.fetchone(
            "SELECT 1 FROM disabled_log_categories WHERE guild_id = ? AND category = ?",
            (guild_id, category),
        )
        return row is not None

    async def disable_log_category(
        self, guild_id: int, category: str, disabled_by: int
    ) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO disabled_log_categories (guild_id, category, disabled_by) VALUES (?, ?, ?)",
            (guild_id, category, disabled_by),
        )
        await self.db.commit()

    async def enable_log_category(self, guild_id: int, category: str) -> None:
        await self.db.execute(
            "DELETE FROM disabled_log_categories WHERE guild_id = ? AND category = ?",
            (guild_id, category),
        )
        await self.db.commit()

    async def get_disabled_log_categories(self, guild_id: int) -> list[str]:
        rows = await self.db.fetchall(
            "SELECT category FROM disabled_log_categories WHERE guild_id = ?",
            (guild_id,),
        )
        return [row["category"] for row in rows]
