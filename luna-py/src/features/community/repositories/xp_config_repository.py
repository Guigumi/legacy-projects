"""
Repositório de configuração de XP por servidor.
Gerencia xp_config, xp_channel_config, xp_boost_roles e xp_level_roles.
"""

from __future__ import annotations

from core.repository import BaseRepository


class XPConfigRepository(BaseRepository):
    """Acesso a configuração de XP no banco."""

    _VALID_CONFIG_FIELDS = {
        "xp_per_level",
        "xp_per_message",
        "xp_per_voice_min",
        "xp_per_reaction",
        "level_up_mode",
        "level_up_channel_id",
        "level_up_title",
        "level_up_message",
        "role_policy",
        "updated_at",
    }

    # ── XP Config Base ────────────────────────────────────────

    async def ensure_config(self, guild_id: int) -> None:
        """Garante que a config de XP do servidor exista."""
        await self.db.execute(
            "INSERT OR IGNORE INTO xp_config (guild_id) VALUES (?)",
            (guild_id,),
        )
        await self.db.commit()

    async def get_config(self, guild_id: int) -> dict:
        """Retorna configuração de XP do servidor."""
        await self.ensure_config(guild_id)
        row = await self.db.fetchone(
            "SELECT * FROM xp_config WHERE guild_id = ?",
            (guild_id,),
        )
        return dict(row) if row else {}

    async def update_config(self, guild_id: int, **kwargs) -> None:
        """Atualiza campos da configuração de XP."""
        if not kwargs:
            return
        # Validar campos contra whitelist
        invalid = set(kwargs) - self._VALID_CONFIG_FIELDS
        if invalid:
            return
        await self.ensure_config(guild_id)
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [guild_id]
        await self.db.execute(
            f"UPDATE xp_config SET {set_clause}, updated_at = datetime('now') WHERE guild_id = ?",
            tuple(values),
        )
        await self.db.commit()

    # ── Channel Config (boost/blocked) ────────────────────────

    async def get_channel_configs(self, guild_id: int) -> list[dict]:
        """Lista canais configurados (boost ou bloqueados)."""
        rows = await self.db.fetchall(
            "SELECT * FROM xp_channel_config WHERE guild_id = ?",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def get_channel_config(self, guild_id: int, channel_id: int) -> dict | None:
        """Retorna config de um canal específico."""
        row = await self.db.fetchone(
            "SELECT * FROM xp_channel_config WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        return dict(row) if row else None

    async def set_channel_config(
        self, guild_id: int, channel_id: int, mode: str, multiplier: float = 1.0
    ) -> None:
        """Define configuração de XP para um canal."""
        await self.db.execute(
            """
            INSERT INTO xp_channel_config (guild_id, channel_id, mode, multiplier)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (guild_id, channel_id)
            DO UPDATE SET mode = excluded.mode, multiplier = excluded.multiplier
            """,
            (guild_id, channel_id, mode, multiplier),
        )
        await self.db.commit()

    async def remove_channel_config(self, guild_id: int, channel_id: int) -> None:
        """Remove configuração de XP de um canal."""
        await self.db.execute(
            "DELETE FROM xp_channel_config WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        await self.db.commit()

    # ── Boost Roles ───────────────────────────────────────────

    async def get_boost_roles(self, guild_id: int) -> list[dict]:
        """Lista cargos com boost de XP."""
        rows = await self.db.fetchall(
            "SELECT * FROM xp_boost_roles WHERE guild_id = ?",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def set_boost_role(
        self, guild_id: int, role_id: int, multiplier: float
    ) -> None:
        """Define boost de XP para um cargo."""
        await self.db.execute(
            """
            INSERT INTO xp_boost_roles (guild_id, role_id, multiplier)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, role_id)
            DO UPDATE SET multiplier = excluded.multiplier
            """,
            (guild_id, role_id, multiplier),
        )
        await self.db.commit()

    async def remove_boost_role(self, guild_id: int, role_id: int) -> None:
        """Remove boost de XP de um cargo."""
        await self.db.execute(
            "DELETE FROM xp_boost_roles WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id),
        )
        await self.db.commit()

    # ── Level Roles ───────────────────────────────────────────

    async def get_level_roles(self, guild_id: int) -> list[dict]:
        """Lista cargos concedidos por nível."""
        rows = await self.db.fetchall(
            "SELECT * FROM xp_level_roles WHERE guild_id = ? ORDER BY level ASC",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def set_level_role(self, guild_id: int, level: int, role_id: int) -> None:
        """Define cargo concedido ao atingir um nível."""
        await self.db.execute(
            """
            INSERT INTO xp_level_roles (guild_id, level, role_id)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, level, role_id) DO NOTHING
            """,
            (guild_id, level, role_id),
        )
        await self.db.commit()

    async def remove_level_role(self, guild_id: int, level: int, role_id: int) -> None:
        """Remove cargo de um nível."""
        await self.db.execute(
            "DELETE FROM xp_level_roles WHERE guild_id = ? AND level = ? AND role_id = ?",
            (guild_id, level, role_id),
        )
        await self.db.commit()

    async def get_roles_for_level(self, guild_id: int, level: int) -> list[int]:
        """Retorna IDs de cargos para um nível específico."""
        rows = await self.db.fetchall(
            "SELECT role_id FROM xp_level_roles WHERE guild_id = ? AND level = ?",
            (guild_id, level),
        )
        return [row["role_id"] for row in rows]

    async def get_roles_for_level_range(
        self, guild_id: int, min_level: int, max_level: int
    ) -> list[dict]:
        """Returns all roles configured within a level range (inclusive)."""
        rows = await self.db.fetchall(
            """
            SELECT level, role_id FROM xp_level_roles
            WHERE guild_id = ? AND level BETWEEN ? AND ?
            ORDER BY level ASC
            """,
            (guild_id, min_level, max_level),
        )
        return [dict(r) for r in rows]

    async def get_all_roles_up_to_level(self, guild_id: int, level: int) -> list[dict]:
        """Retorna todos os cargos até um nível (para dar cargos cumulativos)."""
        rows = await self.db.fetchall(
            "SELECT * FROM xp_level_roles WHERE guild_id = ? AND level <= ? ORDER BY level ASC",
            (guild_id, level),
        )
        return [dict(r) for r in rows]
