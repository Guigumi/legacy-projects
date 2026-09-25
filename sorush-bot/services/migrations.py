"""
Database Migrations System
Manages schema versions and updates
"""
import logging
from datetime import datetime
from services.connection import db_connection

logger = logging.getLogger(__name__)


class MigrationVersionError(Exception):
    """Raised when migration version check fails"""
    pass


class Migrations:
    """Database migration manager"""
    
    @staticmethod
    def init_migration_table():
        """Create migrations tracking table if it doesn't exist"""
        with db_connection.get_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.debug("Migrations table ready")
    
    @staticmethod
    def get_latest_version() -> str:
        """Get the latest applied migration version"""
        try:
            with db_connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT version FROM migrations 
                    ORDER BY version DESC LIMIT 1
                """)
                result = cursor.fetchone()
                return result[0] if result else "000"
        except Exception as e:
            logger.warning(f"Could not get latest migration version: {e}")
            return "000"
    
    @staticmethod
    def apply_migration(version: str, name: str, sql_statements: list) -> bool:
        """
        Apply a migration
        
        Args:
            version: Migration version (e.g. "001", "002")
            name: Human-readable migration name
            sql_statements: List of SQL statements to execute
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with db_connection.get_cursor() as cursor:
                # Check if already applied
                cursor.execute("SELECT 1 FROM migrations WHERE version = ?", (version,))
                if cursor.fetchone():
                    logger.info(f"Migration {version} already applied, skipping")
                    return True
                
                # Execute all statements
                for statement in sql_statements:
                    if statement.strip():
                        cursor.execute(statement)
                
                # Record migration
                cursor.execute("""
                    INSERT INTO migrations (version, name) 
                    VALUES (?, ?)
                """, (version, name))
                
                logger.info(f"✓ Applied migration {version}: {name}")
                return True
        
        except Exception as e:
            logger.error(f"✗ Migration {version} failed: {e}")
            return False
    
    @staticmethod
    def add_column_if_not_exists(table: str, column: str, column_type: str) -> bool:
        """
        Add a column to a table if it doesn't exist
        
        Args:
            table: Table name
            column: Column name
            column_type: Column definition (e.g. "INTEGER DEFAULT 0", "TEXT")
        
        Returns:
            True if added or already exists, False on error
        """
        try:
            with db_connection.get_cursor() as cursor:
                # Check if column exists
                cursor.execute(f"PRAGMA table_info({table})")
                columns = {row[1] for row in cursor.fetchall()}
                
                if column in columns:
                    logger.debug(f"Column {table}.{column} already exists")
                    return True
                
                # Add column
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
                logger.info(f"✓ Added column {table}.{column}")
                return True
        
        except Exception as e:
            logger.error(f"✗ Failed to add column {table}.{column}: {e}")
            return False
    
    @staticmethod
    def initialize_database():
        """Initialize database with schema and run pending migrations"""
        logger.info("Initializing database...")
        
        # Create migrations table
        Migrations.init_migration_table()
        
        # Load and execute schema
        try:
            from pathlib import Path
            schema_path = Path(__file__).parent / "schema.sql"
            
            with open(schema_path, 'r') as f:
                schema = f.read()
            
            db_connection.execute_script(schema)
            logger.info("✓ Schema initialized")
        
        except Exception as e:
            logger.error(f"✗ Failed to initialize schema: {e}")
            return False
        
        # Apply pending migrations
        Migrations._apply_pending_migrations()
        
        # Verify integrity
        is_ok = db_connection.verify_integrity()
        if is_ok:
            logger.info("✓ Database ready")
        else:
            logger.error("✗ Database integrity check failed")
            return False
        
        return True
    
    @staticmethod
    def _apply_pending_migrations():
        """Apply any pending migrations"""
        latest = Migrations.get_latest_version()
        
        # Guild config expansions – new columns for server preferences
        guild_config_cols = [
            ("prefix", "TEXT DEFAULT '!'"),
            ("xp_message_amount", "INTEGER DEFAULT -1"),
            ("xp_voice_amount", "INTEGER DEFAULT -1"),
            ("xp_accumulate_roles", "INTEGER DEFAULT 1"),
            ("xp_levelup_message", "INTEGER DEFAULT 1"),
            ("xp_levelup_channel_id", "INTEGER"),
            ("autorole_id", "INTEGER"),
            ("autorole_enabled", "INTEGER DEFAULT 0"),
            ("daily_base", "INTEGER DEFAULT 500"),
            ("daily_streak_bonus", "INTEGER DEFAULT 50"),
            ("daily_max_streak_bonus", "INTEGER DEFAULT 1000"),
            ("gambling_enabled", "INTEGER DEFAULT 1"),
            ("gambling_min_bet", "INTEGER DEFAULT 50"),
            ("gambling_max_bet", "INTEGER DEFAULT 50000"),
            ("gambling_daily_loss_limit", "INTEGER DEFAULT 10000"),
            ("gambling_house_edge", "REAL DEFAULT 0.02"),
            ("shop_enabled", "INTEGER DEFAULT 1"),
            ("log_events", "TEXT DEFAULT '{}'"),
            ("feature_economy_enabled", "INTEGER DEFAULT 1"),
            ("feature_fun_enabled", "INTEGER DEFAULT 1"),
            ("feature_moderation_enabled", "INTEGER DEFAULT 1"),
            ("feature_notifications_enabled", "INTEGER DEFAULT 1"),
        ]
        
        pending_migrations = [
            ("001", "Expand guild_config with server preferences", []),
            ("002", "Add shop_items table", [
                """CREATE TABLE IF NOT EXISTS shop_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    duration_type TEXT DEFAULT 'temporary',
                    duration_days INTEGER DEFAULT 7,
                    condition TEXT,
                    name TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(guild_id, role_id)
                )""",
                "CREATE INDEX IF NOT EXISTS idx_shop_items_guild ON shop_items(guild_id)",
            ]),
            ("003", "Add shop_purchases table", [
                """CREATE TABLE IF NOT EXISTS shop_purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    duration_type TEXT DEFAULT 'temporary',
                    condition TEXT,
                    purchased_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT
                )""",
                "CREATE INDEX IF NOT EXISTS idx_shop_purchases_guild ON shop_purchases(guild_id, user_id)",
                "CREATE INDEX IF NOT EXISTS idx_shop_purchases_expires ON shop_purchases(expires_at) WHERE expires_at IS NOT NULL",
            ]),
            ("004", "Add user_notifications table", [
                """CREATE TABLE IF NOT EXISTS user_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    keyword TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(guild_id, user_id, keyword)
                )""",
                "CREATE INDEX IF NOT EXISTS idx_notifications_guild ON user_notifications(guild_id, user_id)",
            ]),
        ]
        
        for version, name, statements in pending_migrations:
            if version > latest:
                # Migration 001 uses add_column_if_not_exists for guild_config
                if version == "001":
                    for col_name, col_type in guild_config_cols:
                        Migrations.add_column_if_not_exists("guild_config", col_name, col_type)
                    # Record it manually
                    Migrations.apply_migration(version, name, [])
                else:
                    Migrations.apply_migration(version, name, statements)


# Singleton instance
migrations = Migrations()
