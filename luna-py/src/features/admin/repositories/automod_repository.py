from __future__ import annotations

from core.repository import BaseRepository


class AutoModRepository(BaseRepository):
    """Acesso a dados de configuração do AutoMod."""

    async def get_config(self, guild_id: int) -> dict | None:
        row = await self.db.fetchone(
            "SELECT * FROM automod_config WHERE guild_id = ?",
            (guild_id,),
        )
        return dict(row) if row else None

    async def save_config(self, guild_id: int, data: dict) -> None:
        await self.db.execute(
            """
            INSERT INTO automod_config (
                guild_id, invites_blocked, blocked_words,
                block_links, max_mentions, log_channel_id,
                ignored_channels, ignored_roles, punishment,
                target_group, preset, max_warnings, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                invites_blocked   = excluded.invites_blocked,
                blocked_words     = excluded.blocked_words,
                block_links       = excluded.block_links,
                max_mentions      = excluded.max_mentions,
                log_channel_id    = excluded.log_channel_id,
                ignored_channels  = excluded.ignored_channels,
                ignored_roles     = excluded.ignored_roles,
                punishment        = excluded.punishment,
                target_group      = excluded.target_group,
                preset            = excluded.preset,
                max_warnings      = excluded.max_warnings,
                updated_at        = excluded.updated_at
            """,
            (
                guild_id,
                data["invites_blocked"],
                data["blocked_words"],
                data["block_links"],
                data["max_mentions"],
                data.get("log_channel_id"),
                data["ignored_channels"],
                data["ignored_roles"],
                data.get("punishment", "warn_delete"),
                data.get("target_group", "all"),
                data.get("preset", "alto"),
                data.get("max_warnings", 3),
            ),
        )
        await self.db.commit()
