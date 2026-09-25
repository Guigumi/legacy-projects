"""
Gerenciador de banco de dados SQLite com WAL mode.
Centraliza conexão, migrações e operações assíncronas.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DB_DIR / "luna.db"


class Database:
    """Singleton-like async SQLite manager."""

    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None
        self._in_transaction: int = 0  # suporta reentrada (nested)

    async def connect(self) -> None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Iniciando conexão com o banco de dados...")
        self._db = await aiosqlite.connect(DB_PATH)
        self._db.row_factory = aiosqlite.Row

        # Configurações de performance e resiliência
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._db.execute("PRAGMA synchronous = NORMAL")
        await self._db.execute("PRAGMA locking_mode = NORMAL")
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("PRAGMA busy_timeout = 5000")

        await self._run_migrations()
        logger.info("Banco de dados conectada com sucesso.")

    async def close(self) -> None:
        if self._db:
            logger.info("Encerrando conexão com o banco de dados...")
            await self._db.close()
            self._db = None
            logger.info("Banco de dados desconectada.")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    @property
    def is_connected(self) -> bool:
        """Retorna True quando a conexão com o banco já foi estabelecida."""
        return self._db is not None

    # ── Helpers ───────────────────────────────────────────────

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        import time
        start_time = time.perf_counter()
        try:
            return await self.conn.execute(sql, params)
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "Query SQL executada",
                extra={
                    "sql": sql,
                    "params": params,
                    "duration_ms": round(duration_ms, 2)
                }
            )

    async def executemany(self, sql: str, params_list: list[tuple]) -> aiosqlite.Cursor:
        import time
        start_time = time.perf_counter()
        try:
            return await self.conn.executemany(sql, params_list)
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "Query SQL executemany executada",
                extra={
                    "sql": sql,
                    "params_count": len(params_list),
                    "duration_ms": round(duration_ms, 2)
                }
            )

    async def fetchone(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
        cursor = await self.execute(sql, params)
        return await cursor.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        cursor = await self.execute(sql, params)
        return list(await cursor.fetchall())

    async def commit(self) -> None:
        if self._in_transaction:
            return  # defer até o fim da transaction
        await self.conn.commit()

    @asynccontextmanager
    async def transaction(self):
        """Context manager que agrupa múltiplos commits em uma única transação.

        Seguro para reentrada (nested transactions fazem no-op até o nível mais externo).

        Uso::

            async with db.transaction():
                await repo.add_balance(...)
                await repo.add_item(...)
                # commit único aqui
        """
        self._in_transaction += 1
        try:
            yield
        except BaseException:
            self._in_transaction -= 1
            if self._in_transaction == 0:
                try:
                    await self.conn.rollback()
                except Exception:
                    logger.exception("Erro no rollback da transação")
            raise
        else:
            self._in_transaction -= 1
            if self._in_transaction == 0:
                await self.conn.commit()

    # ── Migrations ────────────────────────────────────────────

    async def _run_migrations(self) -> None:
        """Cria as tabelas principais se não existirem."""

        await self.conn.executescript("""
            -- Configuração por servidor
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id      INTEGER PRIMARY KEY,
                prefix        TEXT    DEFAULT '!',
                welcome_enabled  INTEGER DEFAULT 0,
                welcome_channel  INTEGER,
                welcome_message  TEXT,
                log_channel      INTEGER,
                tracking_enabled INTEGER DEFAULT 1,
                locale           TEXT    DEFAULT 'pt-BR',
                minecraft_channel INTEGER,
                created_at       TEXT    DEFAULT (datetime('now')),
                updated_at       TEXT    DEFAULT (datetime('now'))
            );

            -- Dados de usuário por servidor
            CREATE TABLE IF NOT EXISTS user_data (
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                messages_sent   INTEGER DEFAULT 0,
                voice_seconds   INTEGER DEFAULT 0,
                xp              INTEGER DEFAULT 0,
                level           INTEGER DEFAULT 1,
                longest_voice   INTEGER DEFAULT 0,
                longest_message INTEGER DEFAULT 0,
                warnings        INTEGER DEFAULT 0,
                last_active     TEXT,
                selected_theme  TEXT    DEFAULT 'default',
                coins           INTEGER DEFAULT 0,
                last_daily      TEXT,
                daily_streak    INTEGER DEFAULT 0,
                unlocked_backgrounds TEXT DEFAULT 'default',
                created_at      TEXT    DEFAULT (datetime('now')),
                updated_at      TEXT    DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, user_id)
            );

            -- Warns com expiração (1 semana)
            CREATE TABLE IF NOT EXISTS user_warnings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                reason          TEXT,
                created_at      TEXT    DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_user_warnings_lookup
                ON user_warnings(guild_id, user_id, created_at);

            -- Sessões de voz ativas (checkpoint persistente)
            CREATE TABLE IF NOT EXISTS voice_sessions (
                guild_id            INTEGER NOT NULL,
                user_id             INTEGER NOT NULL,
                channel_id          INTEGER,
                started_at_ts       REAL    NOT NULL,
                last_checkpoint_ts  REAL    NOT NULL,
                updated_at          TEXT    DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_voice_sessions_guild
                ON voice_sessions(guild_id);

            -- Flags desativadas por servidor (memória de decisões)
            CREATE TABLE IF NOT EXISTS disabled_features (
                guild_id     INTEGER NOT NULL,
                feature_name TEXT    NOT NULL,
                disabled_by  INTEGER,
                disabled_at  TEXT    DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, feature_name)
            );

            -- Log de eventos internos
            CREATE TABLE IF NOT EXISTS event_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                event_type TEXT    NOT NULL,
                data       TEXT,
                created_at TEXT    DEFAULT (datetime('now'))
            );

            -- AutoRole: configuração por servidor
            CREATE TABLE IF NOT EXISTS autorole (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id       INTEGER NOT NULL,
                role_id        INTEGER NOT NULL,
                mode           TEXT    NOT NULL DEFAULT 'instant',
                delay_seconds  INTEGER DEFAULT 0,
                channel_id     INTEGER,
                message_id     INTEGER,
                embed_title    TEXT,
                embed_text     TEXT,
                emoji          TEXT    DEFAULT '✅',
                enabled        INTEGER DEFAULT 1,
                configured_by  INTEGER,
                created_at     TEXT    DEFAULT (datetime('now')),
                updated_at     TEXT    DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_autorole_guild
                ON autorole(guild_id, enabled);

            -- Categorias de log desativadas por servidor
            CREATE TABLE IF NOT EXISTS disabled_log_categories (
                guild_id      INTEGER NOT NULL,
                category      TEXT    NOT NULL,
                disabled_by   INTEGER,
                disabled_at   TEXT    DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, category)
            );

            -- Notificações agendadas
            CREATE TABLE IF NOT EXISTS notifications (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                channel_id      INTEGER NOT NULL,
                creator_id      INTEGER NOT NULL,
                title           TEXT    NOT NULL,
                description     TEXT,
                scheduled_at    TEXT    NOT NULL,
                remind_before   INTEGER DEFAULT 0,
                reminded        INTEGER DEFAULT 0,
                notified        INTEGER DEFAULT 0,
                created_at      TEXT    DEFAULT (datetime('now')),
                updated_at      TEXT    DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_notifications_guild
                ON notifications(guild_id, notified);

            -- Giveaways (Sorteios)
            CREATE TABLE IF NOT EXISTS giveaways (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                channel_id      INTEGER NOT NULL,
                message_id      INTEGER,
                creator_id      INTEGER NOT NULL,
                prize           TEXT    NOT NULL,
                winner_count    INTEGER DEFAULT 1,
                ends_at         TEXT    NOT NULL,
                ended           INTEGER DEFAULT 0,
                cancelled       INTEGER DEFAULT 0,
                winners         TEXT, -- Lista de IDs (JSON ou formatado)
                created_at      TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS giveaway_participants (
                giveaway_id     INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                PRIMARY KEY (giveaway_id, user_id),
                FOREIGN KEY (giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_giveaways_active
                ON giveaways(guild_id, ended, cancelled);

            -- Membros adicionais a serem mencionados na notificação
            CREATE TABLE IF NOT EXISTS notification_members (
                notification_id INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                opted_out       INTEGER DEFAULT 0,
                PRIMARY KEY (notification_id, user_id),
                FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE CASCADE
            );

            -- Configuração de XP por servidor
            CREATE TABLE IF NOT EXISTS xp_config (
                guild_id          INTEGER PRIMARY KEY,
                xp_per_level      INTEGER DEFAULT 100,
                xp_per_message    INTEGER DEFAULT 5,
                xp_per_voice_min  INTEGER DEFAULT 3,
                xp_per_reaction   INTEGER DEFAULT 2,
                level_formula     TEXT    DEFAULT 'linear',
                level_up_mode     TEXT    DEFAULT 'current',
                level_up_channel_id INTEGER,
                level_up_title    TEXT,
                level_up_message  TEXT,
                created_at        TEXT    DEFAULT (datetime('now')),
                updated_at        TEXT    DEFAULT (datetime('now'))
            );

            -- Canais com boost ou bloqueio de XP
            CREATE TABLE IF NOT EXISTS xp_channel_config (
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                mode        TEXT    NOT NULL DEFAULT 'blocked',
                multiplier  REAL    DEFAULT 1.0,
                PRIMARY KEY (guild_id, channel_id)
            );

            -- Cargos com boost de XP
            CREATE TABLE IF NOT EXISTS xp_boost_roles (
                guild_id    INTEGER NOT NULL,
                role_id     INTEGER NOT NULL,
                multiplier  REAL    DEFAULT 1.5,
                PRIMARY KEY (guild_id, role_id)
            );

            -- Cargos ganhos ao atingir um nível
            CREATE TABLE IF NOT EXISTS xp_level_roles (
                guild_id  INTEGER NOT NULL,
                level     INTEGER NOT NULL,
                role_id   INTEGER NOT NULL,
                PRIMARY KEY (guild_id, level, role_id)
            );

            CREATE INDEX IF NOT EXISTS idx_xp_level_roles_guild
                ON xp_level_roles(guild_id);

            -- Índices para performance
            CREATE INDEX IF NOT EXISTS idx_user_data_guild
                ON user_data(guild_id);
            CREATE INDEX IF NOT EXISTS idx_event_log_guild_type
                ON event_log(guild_id, event_type);



            -- ═══════════════════════════════════════════════════
            -- CONFIGURAÇÕES GLOBAIS DO BOT (persistem entre restarts)
            -- ═══════════════════════════════════════════════════

            -- Configurações chave-valor do bot (auto-update, etc.)
            -- Não é por servidor — é global do bot inteiro.
            CREATE TABLE IF NOT EXISTS bot_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- ═══════════════════════════════════════════════════
            -- ÍNDICES DE LEADERBOARD (performance em ORDER BY DESC)
            -- ═══════════════════════════════════════════════════

            CREATE INDEX IF NOT EXISTS idx_user_data_xp
                ON user_data(guild_id, xp DESC);
            
            -- ═══════════════════════════════════════════════════
            -- OSU CACHE
            -- ═══════════════════════════════════════════════════
            
            CREATE TABLE IF NOT EXISTS osu_cache (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                expires_at REAL NOT NULL
            );

        """)

        await self._ensure_guild_config_columns()
        await self._ensure_xp_config_columns()
        await self._ensure_user_data_columns()
        await self._ensure_minecraft_config_table()
        await self._ensure_minecraft_config_columns()
        await self._ensure_welcome_config_table()
        await self._ensure_starboard_tables()
        await self._ensure_reminder_table()
        await self._ensure_automod_table()
        await self._ensure_ticket_tables()

        self._v6_data_migrations = []
        await self.conn.commit()
        logger.debug("Migrações executadas com sucesso.")

    async def _ensure_minecraft_config_table(self) -> None:
        """Cria a tabela minecraft_config se não existir (webhook URL por guild)."""
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS minecraft_config (
                guild_id    INTEGER PRIMARY KEY,
                webhook_url TEXT,
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            -- Vínculo de identidade Minecraft-Discord
            CREATE TABLE IF NOT EXISTS minecraft_players (
                guild_id    INTEGER NOT NULL,
                discord_id  INTEGER NOT NULL,
                mc_nickname TEXT    NOT NULL,
                created_at  TEXT    DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, discord_id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_minecraft_players_nick
                ON minecraft_players(guild_id, LOWER(mc_nickname));
        """)
        logger.debug("minecraft_config & minecraft_players: tabelas garantidas.")

    async def _ensure_minecraft_config_columns(self) -> None:
        """Garante colunas novas em minecraft_config sem recriar a tabela."""
        required_columns: dict[str, str] = {
            "webhook_channel_id": "INTEGER",
        }

        cursor = await self.conn.execute("PRAGMA table_info(minecraft_config)")
        rows = await cursor.fetchall()
        existing = {row[1] for row in rows}

        for col, definition in required_columns.items():
            if col in existing:
                continue
            await self.conn.execute(
                f"ALTER TABLE minecraft_config ADD COLUMN {col} {definition}"
            )
            logger.info("minecraft_config: coluna adicionada: %s", col)

    async def _ensure_welcome_config_table(self) -> None:
        """Cria a tabela welcome_config se não existir."""
        await self.conn.executescript("""
            -- DROP temporário para recriar com a nova chave primária
            DROP TABLE IF EXISTS welcome_config;
            
            CREATE TABLE IF NOT EXISTS welcome_config (
                guild_id          INTEGER,
                event_type        TEXT, -- 'join' ou 'leave'
                channel_id        INTEGER,
                content           TEXT,
                embed_title       TEXT,
                embed_description TEXT,
                embed_color       TEXT,
                embed_thumbnail   TEXT,
                embed_image       TEXT,
                embed_footer_text TEXT,
                embed_footer_icon TEXT,
                embed_author_name TEXT,
                embed_author_icon TEXT,
                welcome_emoji     TEXT DEFAULT '👋',
                enabled           INTEGER DEFAULT 0,
                updated_at        TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, event_type)
            );
        """)
        logger.debug("welcome_config: tabela garantida.")

    async def _ensure_guild_config_columns(self) -> None:
        """Garante colunas novas em guild_config sem recriar a tabela."""
        required_columns: dict[str, str] = {
            "minecraft_channel": "INTEGER",
            "warn_timeout_hours": "INTEGER DEFAULT 1",
        }

        cursor = await self.conn.execute("PRAGMA table_info(guild_config)")
        rows = await cursor.fetchall()
        existing = {row[1] for row in rows}

        for col, definition in required_columns.items():
            if col in existing:
                continue
            await self.conn.execute(
                f"ALTER TABLE guild_config ADD COLUMN {col} {definition}"
            )
            logger.info("guild_config: coluna adicionada: %s", col)

    async def _ensure_xp_config_columns(self) -> None:
        """Garante colunas novas em xp_config sem recriar a tabela."""
        required_columns: dict[str, str] = {
            "level_up_mode": "TEXT DEFAULT 'current'",
            "level_up_channel_id": "INTEGER",
            "level_up_title": "TEXT",
            "level_up_message": "TEXT",
            "role_policy": "TEXT DEFAULT 'stack'",
        }

        cursor = await self.conn.execute("PRAGMA table_info(xp_config)")
        rows = await cursor.fetchall()
        existing = {row[1] for row in rows}

        for col, definition in required_columns.items():
            if col in existing:
                continue
            await self.conn.execute(
                f"ALTER TABLE xp_config ADD COLUMN {col} {definition}"
            )
            logger.info("xp_config: coluna adicionada: %s", col)

    async def _ensure_user_data_columns(self) -> None:
        """Garante colunas novas em user_data sem recriar a tabela."""
        required_columns: dict[str, str] = {
            "selected_theme": "TEXT DEFAULT 'default'",
            "coins": "INTEGER DEFAULT 0",
            "last_daily": "TEXT",
            "daily_streak": "INTEGER DEFAULT 0",
            "unlocked_backgrounds": "TEXT DEFAULT 'default'",
        }

        cursor = await self.conn.execute("PRAGMA table_info(user_data)")
        rows = await cursor.fetchall()
        existing = {row[1] for row in rows}

        for col, definition in required_columns.items():
            if col in existing:
                continue
            await self.conn.execute(
                f"ALTER TABLE user_data ADD COLUMN {col} {definition}"
            )
            logger.info("user_data: coluna adicionada: %s", col)


    async def _ensure_starboard_tables(self) -> None:
        """Cria as tabelas starboard_config e starboard_messages se não existirem."""
        await self.conn.executescript("""
            -- Tabela de configuração do starboard por guilda
            CREATE TABLE IF NOT EXISTS starboard_config (
                guild_id    INTEGER PRIMARY KEY,
                channel_id  INTEGER NOT NULL,
                emoji       TEXT    DEFAULT '⭐',
                min_stars   INTEGER DEFAULT 3,
                enabled     INTEGER DEFAULT 1,
                updated_at  TEXT    DEFAULT (datetime('now'))
            );
            
            -- Tabela de mensagens que já foram enviadas para o starboard
            CREATE TABLE IF NOT EXISTS starboard_messages (
                message_id           INTEGER PRIMARY KEY,
                starboard_message_id INTEGER NOT NULL,
                guild_id             INTEGER NOT NULL,
                channel_id           INTEGER NOT NULL,
                star_count           INTEGER NOT NULL,
                updated_at           TEXT    DEFAULT (datetime('now'))
            );
        """)
        logger.debug("starboard_config & starboard_messages: tabelas garantidas.")

    async def _ensure_reminder_table(self) -> None:
        """Cria a tabela reminders se não existir."""
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                guild_id    INTEGER,
                message     TEXT NOT NULL,
                remind_at   TEXT NOT NULL,
                notified    INTEGER DEFAULT 0,
                created_at  TEXT    DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_reminders_pending ON reminders(notified, remind_at);
        """)
        logger.debug("reminders: tabela garantida.")

    async def _ensure_economy_tables(self) -> None:
        """Cria as tabelas de economia se não existirem."""
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS economy_users (
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                coins       INTEGER DEFAULT 0,
                bank        INTEGER DEFAULT 0,
                last_daily  TEXT,
                last_work   TEXT,
                updated_at  TEXT    DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS economy_inventory (
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                item_id     TEXT NOT NULL,
                quantity    INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, user_id, item_id)
            );
        """)
        logger.debug("economy_users & economy_inventory: tabelas garantidas.")

    async def _ensure_automod_table(self) -> None:
        """Cria a tabela automod_config se não existir e garante colunas novas."""
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS automod_config (
                guild_id          INTEGER PRIMARY KEY,
                invites_blocked   INTEGER DEFAULT 0,
                blocked_words     TEXT    DEFAULT '',
                updated_at        TEXT    DEFAULT (datetime('now'))
            );
        """)

        # Migração incremental — adiciona colunas novas sem recriar a tabela
        required_columns: dict[str, str] = {
            "block_links":      "INTEGER DEFAULT 0",
            "max_mentions":     "INTEGER DEFAULT 5",
            "log_channel_id":   "INTEGER",
            "ignored_channels": "TEXT DEFAULT ''",
            "ignored_roles":    "TEXT DEFAULT ''",
            "punishment":       "TEXT DEFAULT 'warn_delete'",
            "target_group":     "TEXT DEFAULT 'all'",
            "preset":           "TEXT DEFAULT 'alto'",
            "max_warnings":     "INTEGER DEFAULT 3",
        }

        cursor = await self.conn.execute("PRAGMA table_info(automod_config)")
        rows = await cursor.fetchall()
        existing = {row[1] for row in rows}

        for col, definition in required_columns.items():
            if col in existing:
                continue
            await self.conn.execute(
                f"ALTER TABLE automod_config ADD COLUMN {col} {definition}"
            )
            logger.info("automod_config: coluna adicionada: %s", col)

        logger.debug("automod_config: tabela garantida.")

    async def _ensure_ticket_tables(self) -> None:
        """Cria as tabelas de ticket se não existirem."""
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS ticket_config (
                guild_id            INTEGER PRIMARY KEY,
                category_id         INTEGER NOT NULL,
                support_role_id     INTEGER NOT NULL,
                log_channel_id      INTEGER,
                last_ticket_number  INTEGER DEFAULT 0,
                enabled             INTEGER DEFAULT 1,
                updated_at          TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id       INTEGER NOT NULL,
                channel_id     INTEGER NOT NULL,
                creator_id     INTEGER NOT NULL,
                claimant_id    INTEGER,
                status         TEXT    NOT NULL DEFAULT 'open',
                created_at     TEXT    DEFAULT (datetime('now')),
                closed_at      TEXT,
                closed_by      INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_tickets_guild_status
                ON tickets(guild_id, status);
            CREATE INDEX IF NOT EXISTS idx_tickets_channel
                ON tickets(channel_id);
        """)
        logger.debug("ticket_config & tickets: tabelas garantidas.")


