"""
Repositório de dados de usuário (por servidor).
CRUD + queries de ranking/estatísticas.

Otimizações aplicadas:
- ensure_user não faz commit isolado (chamadores controlam transação).
- update_xp_and_level: operação atômica de XP + nível em um único commit.
- Menos round-trips ao banco em operações compostas.
"""

from __future__ import annotations

from core.repository import BaseRepository
from core.models import UserData


class UserRepository(BaseRepository):
    """Acesso a dados de usuário no banco."""

    async def ensure_user(self, guild_id: int, user_id: int) -> None:
        """Garante que o registro do usuário exista.

        Nota: usa INSERT OR IGNORE — é um no-op se já existir,
        portanto seguro para chamar múltiplas vezes sem overhead.
        """
        await self.db.execute(
            """
            INSERT OR IGNORE INTO user_data (guild_id, user_id)
            VALUES (?, ?)
            """,
            (guild_id, user_id),
        )
        await self.db.commit()

    async def get_user(self, guild_id: int, user_id: int) -> UserData | None:
        """Retorna dados de um usuário no servidor."""
        row = await self.db.fetchone(
            "SELECT * FROM user_data WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return UserData.from_row(row)

    async def increment_messages(
        self, guild_id: int, user_id: int, msg_len: int
    ) -> None:
        """Incrementa contador de mensagens e atualiza longest_message usando UPSERT."""
        await self.db.execute(
            """
            INSERT INTO user_data (guild_id, user_id, messages_sent, longest_message, last_active, updated_at)
            VALUES (?, ?, 1, ?, datetime('now'), datetime('now'))
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
                messages_sent   = messages_sent + 1,
                longest_message = MAX(longest_message, excluded.longest_message),
                last_active     = excluded.last_active,
                updated_at      = excluded.updated_at
            """,
            (guild_id, user_id, msg_len),
        )
        await self.db.commit()

    async def add_voice_seconds(
        self, guild_id: int, user_id: int, seconds: int
    ) -> None:
        """Adiciona tempo de voz e atualiza longest_voice usando UPSERT."""
        await self.db.execute(
            """
            INSERT INTO user_data (guild_id, user_id, voice_seconds, longest_voice, last_active, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
                voice_seconds = voice_seconds + excluded.voice_seconds,
                longest_voice = MAX(longest_voice, excluded.longest_voice),
                last_active   = excluded.last_active,
                updated_at    = excluded.updated_at
            """,
            (guild_id, user_id, seconds, seconds),
        )
        await self.db.commit()

    async def update_xp_and_level(
        self, guild_id: int, user_id: int, xp_delta: int, new_level: int
    ) -> None:
        """Atualiza XP e nível atomicamente em uma única transação.

        Evita o problema de grant_xp fazer dois commits separados (add_xp + set_level),
        o que poderia deixar o estado inconsistente se o bot caísse entre os dois.
        """
        async with self.db.transaction():
            await self.db.execute(
                """
                UPDATE user_data
                SET xp         = xp + ?,
                    level      = ?,
                    updated_at = datetime('now')
                WHERE guild_id = ? AND user_id = ?
                """,
                (xp_delta, new_level, guild_id, user_id),
            )

    async def upsert_voice_session(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int | None,
        now_ts: float,
    ) -> None:
        """Cria/atualiza sessão de voz ativa com checkpoint inicial."""
        await self.db.execute(
            """
            INSERT INTO voice_sessions (
                guild_id, user_id, channel_id, started_at_ts, last_checkpoint_ts, updated_at
            )
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
                channel_id = excluded.channel_id,
                started_at_ts = excluded.started_at_ts,
                last_checkpoint_ts = excluded.last_checkpoint_ts,
                updated_at = datetime('now')
            """,
            (guild_id, user_id, channel_id, now_ts, now_ts),
        )
        await self.db.commit()

    async def remove_voice_session(self, guild_id: int, user_id: int) -> None:
        """Remove sessão de voz ativa do usuário."""
        await self.db.execute(
            "DELETE FROM voice_sessions WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.db.commit()

    async def get_voice_session(self, guild_id: int, user_id: int) -> dict | None:
        """Retorna estado da sessão de voz ativa de um usuário."""
        row = await self.db.fetchone(
            "SELECT * FROM voice_sessions WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return dict(row) if row else None

    async def get_all_voice_sessions(self, guild_id: int) -> list[dict]:
        """Retorna todas as sessões de voz ativas de um servidor."""
        rows = await self.db.fetchall(
            "SELECT * FROM voice_sessions WHERE guild_id = ?",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def accrue_voice_session_seconds(
        self,
        guild_id: int,
        user_id: int,
        now_ts: float,
        min_seconds: int = 1,
        channel_id: int | None = None,
    ) -> int:
        """Credita segundos de voz de forma atômica a partir do último checkpoint.

        Retorna quantos segundos foram creditados. Se não houver sessão ativa
        ou o delta for menor que `min_seconds`, retorna 0.

        Nota: `longest_voice` é atualizado com a duração total da sessão
        (now - started_at), não apenas o delta do checkpoint.
        """
        session = await self.get_voice_session(guild_id, user_id)
        if not session:
            return 0

        last_checkpoint = float(session["last_checkpoint_ts"])
        started_at = float(session["started_at_ts"])
        seconds = int(now_ts - last_checkpoint)
        if seconds < min_seconds:
            return 0

        # Duração total da sessão para longest_voice (não apenas o chunk)
        total_session_seconds = int(now_ts - started_at)

        effective_channel_id = (
            channel_id if channel_id is not None else session.get("channel_id")
        )
        await self.ensure_user(guild_id, user_id)

        async with self.db.transaction():
            await self.db.execute(
                """
                UPDATE user_data
                SET voice_seconds = voice_seconds + ?,
                    longest_voice = MAX(longest_voice, ?),
                    last_active   = datetime('now'),
                    updated_at    = datetime('now')
                WHERE guild_id = ? AND user_id = ?
                """,
                (seconds, total_session_seconds, guild_id, user_id),
            )
            await self.db.execute(
                """
                UPDATE voice_sessions
                SET last_checkpoint_ts = ?,
                    channel_id = COALESCE(?, channel_id),
                    updated_at = datetime('now')
                WHERE guild_id = ? AND user_id = ?
                """,
                (now_ts, effective_channel_id, guild_id, user_id),
            )

        return seconds

    async def add_xp(self, guild_id: int, user_id: int, amount: int) -> UserData | None:
        """Adiciona XP e retorna dados atualizados usando UPSERT."""
        await self.db.execute(
            """
            INSERT INTO user_data (guild_id, user_id, xp, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
                xp         = xp + excluded.xp,
                updated_at = excluded.updated_at
            """,
            (guild_id, user_id, amount),
        )
        await self.db.commit()
        return await self.get_user(guild_id, user_id)

    async def set_level(self, guild_id: int, user_id: int, level: int) -> None:
        """Define o nível do usuário.

        NOTA: Para operações que também precisam atualizar o XP,
        prefira update_xp_and_level() que faz tudo atomicamente.
        """
        await self.db.execute(
            """
            UPDATE user_data
            SET level      = ?,
                updated_at = datetime('now')
            WHERE guild_id = ? AND user_id = ?
            """,
            (level, guild_id, user_id),
        )
        await self.db.commit()

    async def add_warning(self, guild_id: int, user_id: int, reason: str = "") -> int:
        """Adiciona um aviso com expiração e retorna o total de avisos ativos (últimos 7 dias)."""
        await self.ensure_user(guild_id, user_id)
        
        # Insere o warn com data atual
        await self.db.execute(
            """
            INSERT INTO user_warnings (guild_id, user_id, reason, created_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (guild_id, user_id, reason),
        )
        await self.db.commit()
        
        # Conta apenas warns dos últimos 7 dias
        row = await self.db.fetchone(
            """
            SELECT COUNT(*) FROM user_warnings 
            WHERE guild_id = ? AND user_id = ? 
              AND created_at >= datetime('now', '-7 days')
            """,
            (guild_id, user_id),
        )
        return row[0] if row else 0

    async def get_leaderboard(
        self, guild_id: int, order_by: str = "xp", limit: int = 10, offset: int = 0
    ) -> list[UserData]:
        """Retorna ranking de usuários do servidor com paginação."""
        mapping = {
            "xp": "xp",
            "messages_sent": "messages_sent",
            "voice_seconds": "voice_seconds",
            "level": "level",
        }
        # A atribuição explícita a partir de um literal no mapping garante que
        # order_by seja uma string segura e controlada, prevenindo SQL Injection
        # por objetos maliciosos que passam no teste 'in' mas têm __str__ perigoso.
        safe_order_by = mapping.get(order_by, "xp")

        rows = await self.db.fetchall(
            f"SELECT * FROM user_data WHERE guild_id = ? AND {safe_order_by} > 0 ORDER BY {safe_order_by} DESC LIMIT ? OFFSET ?",
            (guild_id, limit, offset),
        )
        return [UserData.from_row(r) for r in rows if r]

    async def get_leaderboard_count(self, guild_id: int, order_by: str = "xp") -> int:
        """Retorna a contagem total de usuários com atividade no ranking."""
        mapping = {
            "xp": "xp",
            "messages_sent": "messages_sent",
            "voice_seconds": "voice_seconds",
            "level": "level",
        }
        safe_order_by = mapping.get(order_by, "xp")
        row = await self.db.fetchone(
            f"SELECT COUNT(*) FROM user_data WHERE guild_id = ? AND {safe_order_by} > 0",
            (guild_id,),
        )
        return row[0] if row else 0

    async def set_user_theme(self, guild_id: int, user_id: int, theme: str) -> None:
        """Salva a escolha de tema do rank card do usuário."""
        await self.ensure_user(guild_id, user_id)
        await self.db.execute(
            """
            UPDATE user_data
            SET selected_theme = ?,
                updated_at = datetime('now')
            WHERE guild_id = ? AND user_id = ?
            """,
            (theme, guild_id, user_id),
        )
        await self.db.commit()

    async def get_user_rank(self, guild_id: int, user_id: int) -> int:
        """Retorna o rank do usuário com base no XP (1-indexed)."""
        row = await self.db.fetchone(
            """
            SELECT COUNT(*) as rank_val FROM user_data 
            WHERE guild_id = ? AND xp > (
                SELECT xp FROM user_data WHERE guild_id = ? AND user_id = ?
            )
            """,
            (guild_id, guild_id, user_id),
        )
        return (row["rank_val"] + 1) if (row and row["rank_val"] is not None) else 1

    async def add_coins(self, guild_id: int, user_id: int, amount: int) -> None:
        """Adiciona moedas/pontos ao usuário."""
        await self.ensure_user(guild_id, user_id)
        await self.db.execute(
            """
            UPDATE user_data
            SET coins = coins + ?,
                updated_at = datetime('now')
            WHERE guild_id = ? AND user_id = ?
            """,
            (amount, guild_id, user_id),
        )
        await self.db.commit()

    async def update_daily_claim(
        self, guild_id: int, user_id: int, last_daily_str: str, streak: int, coins_to_add: int
    ) -> None:
        """Atualiza data do daily, streak e adiciona as moedas obtidas em uma única transação."""
        await self.ensure_user(guild_id, user_id)
        async with self.db.transaction():
            await self.db.execute(
                """
                UPDATE user_data
                SET last_daily = ?,
                    daily_streak = ?,
                    coins = coins + ?,
                    updated_at = datetime('now')
                WHERE guild_id = ? AND user_id = ?
                """,
                (last_daily_str, streak, coins_to_add, guild_id, user_id),
            )

    async def unlock_background(
        self, guild_id: int, user_id: int, new_unlocked_str: str, price: int
    ) -> None:
        """Desbloqueia um plano de fundo na loja deduzindo o custo do saldo do usuário."""
        await self.ensure_user(guild_id, user_id)
        async with self.db.transaction():
            await self.db.execute(
                """
                UPDATE user_data
                SET unlocked_backgrounds = ?,
                    coins = MAX(0, coins - ?),
                    updated_at = datetime('now')
                WHERE guild_id = ? AND user_id = ?
                """,
                (new_unlocked_str, price, guild_id, user_id),
            )


