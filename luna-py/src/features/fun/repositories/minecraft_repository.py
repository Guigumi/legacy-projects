"""
Repositório dedicado para configurações do subsistema Minecraft.

Tabela: minecraft_config
    guild_id           INTEGER PRIMARY KEY
    webhook_url        TEXT            -- URL persistido do webhook do canal
    webhook_channel_id INTEGER         -- canal onde o webhook foi criado (#9)
    ram_mb             INTEGER         -- RAM em MB para o servidor
    updated_at         TEXT
"""

from __future__ import annotations

from typing import Optional

from core.database import Database


class MinecraftRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ── RAM ──────────────────────────────────────────────────────────────────

    async def get_ram(self) -> int:
        """Retorna a RAM configurada em MB (padrão 2048)."""
        row = await self.db.fetchone(
            "SELECT value FROM bot_settings WHERE key = ?",
            ("minecraft_ram",),
        )
        if row and row[0]:
            try:
                return int(row[0])
            except (ValueError, TypeError):
                pass
        return 2048

    async def set_ram(self, ram_mb: int) -> None:
        """Persiste a RAM em MB na tabela de configurações globais do bot."""
        await self.db.execute(
            """
            INSERT INTO bot_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                updated_at = datetime('now')
            """,
            ("minecraft_ram", str(ram_mb)),
        )
        await self.db.commit()

    # ── Webhook URL ──────────────────────────────────────────────────────────

    async def get_webhook_config(self, guild_id: int) -> tuple[Optional[str], Optional[int]]:
        """Retorna (webhook_url, webhook_channel_id) persistidos para o guild."""
        row = await self.db.fetchone(
            "SELECT webhook_url, webhook_channel_id FROM minecraft_config WHERE guild_id = ?",
            (guild_id,),
        )
        if not row:
            return None, None
        url = row["webhook_url"] if row["webhook_url"] else None
        channel_id = int(row["webhook_channel_id"]) if row["webhook_channel_id"] else None
        return url, channel_id

    async def get_webhook_url(self, guild_id: int) -> Optional[str]:
        """Retorna o URL do webhook persistido para o guild."""
        url, _ = await self.get_webhook_config(guild_id)
        return url

    async def set_webhook_url(
        self,
        guild_id: int,
        url: Optional[str],
        channel_id: Optional[int] = None,
    ) -> None:
        """Persiste (ou limpa) o URL do webhook e o canal associado para o guild."""
        await self.db.execute(
            """
            INSERT INTO minecraft_config (guild_id, webhook_url, webhook_channel_id, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                webhook_url        = excluded.webhook_url,
                webhook_channel_id = excluded.webhook_channel_id,
                updated_at         = datetime('now')
            """,
            (guild_id, url, channel_id),
        )
        await self.db.commit()

    # ── Canal Minecraft ──────────────────────────────────────────────────────

    async def get_guilds_with_minecraft_channel(self) -> list[int]:
        """Retorna guild_ids com canal Minecraft configurado."""
        rows = await self.db.fetchall(
            "SELECT guild_id FROM guild_config WHERE minecraft_channel IS NOT NULL"
        )
        return [int(row["guild_id"]) for row in rows]

    async def get_minecraft_channel(self, guild_id: int) -> Optional[int]:
        """Retorna o channel_id vinculado ao Minecraft para o guild."""
        row = await self.db.fetchone(
            "SELECT minecraft_channel FROM guild_config WHERE guild_id = ?",
            (guild_id,),
        )
        if row and row["minecraft_channel"]:
            return int(row["minecraft_channel"])
        return None

    async def set_minecraft_channel(self, guild_id: int, channel_id: int) -> None:
        """Vincula (ou desvincula) um canal de texto ao chat do Minecraft."""
        await self.db.execute(
            """
            INSERT INTO guild_config (guild_id, minecraft_channel, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(guild_id) DO UPDATE SET
                minecraft_channel = excluded.minecraft_channel,
                updated_at        = datetime('now')
            """,
            (guild_id, channel_id),
        )
        await self.db.commit()

    # ── Vínculo de Jogadores ──────────────────────────────────────────────────

    async def link_player(self, guild_id: int, discord_id: int, nickname: str) -> None:
        """Cria ou atualiza o vínculo de um jogador."""
        async with self.db.transaction():
            await self.db.execute(
                """
                INSERT INTO minecraft_players (guild_id, discord_id, mc_nickname)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, discord_id) DO UPDATE SET
                    mc_nickname = excluded.mc_nickname
                """,
                (guild_id, discord_id, nickname),
            )

    async def unlink_player(self, guild_id: int, discord_id: int) -> Optional[str]:
        """Remove o vínculo e retorna o nickname que estava vinculado, se houver."""
        async with self.db.transaction():
            nick = await self.get_player_by_discord(guild_id, discord_id)
            if nick:
                await self.db.execute(
                    "DELETE FROM minecraft_players WHERE guild_id = ? AND discord_id = ?",
                    (guild_id, discord_id),
                )
            return nick

    async def get_player_by_discord(self, guild_id: int, discord_id: int) -> Optional[str]:
        """Busca o nickname do Minecraft vinculado a um ID do Discord."""
        row = await self.db.fetchone(
            "SELECT mc_nickname FROM minecraft_players WHERE guild_id = ? AND discord_id = ?",
            (guild_id, discord_id),
        )
        return row["mc_nickname"] if row else None

    async def get_player_by_nickname(self, guild_id: int, nickname: str) -> Optional[int]:
        """Busca o ID do Discord vinculado a um nickname (case-insensitive)."""
        row = await self.db.fetchone(
            "SELECT discord_id FROM minecraft_players WHERE guild_id = ? AND LOWER(mc_nickname) = LOWER(?)",
            (guild_id, nickname),
        )
        return int(row["discord_id"]) if row else None

    async def get_all_linked_nicknames(self) -> list[str]:
        """Retorna uma lista de todos os nicknames vinculados em todos os servidores."""
        rows = await self.db.fetchall("SELECT DISTINCT mc_nickname FROM minecraft_players")
        return [row["mc_nickname"] for row in rows]
