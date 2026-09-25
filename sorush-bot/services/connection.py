"""
Database Connection Manager
Handles SQLite connections with WAL mode and optimizations
"""
import sqlite3
import threading
import logging
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from typing import Optional
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Singleton database connection manager with thread-local connections"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.db_path = Path(DATABASE_PATH)
        self._local = threading.local()
        self._ensure_directory()
        self._initialized = True
    
    def _ensure_directory(self):
        """Ensure data directory exists"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Database path: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local database connection"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=60.0
            )
            conn.row_factory = sqlite3.Row
            
            # Performance optimizations
            self._configure_pragmas(conn)
            
            self._local.connection = conn
            logger.debug(f"Created new connection for thread {threading.current_thread().name}")
        
        return self._local.connection
    
    @staticmethod
    def _configure_pragmas(conn: sqlite3.Connection):
        """Configure SQLite PRAGMA settings for performance"""
        pragmas = {
            "journal_mode": "WAL",  # Write-Ahead Logging for better concurrency
            "synchronous": "NORMAL",  # Balance between safety and speed
            "foreign_keys": "ON",  # Enable foreign key constraints
            "busy_timeout": "5000",  # 5 second timeout for locked database
            "cache_size": "10000",  # Cache size in pages
            "temp_store": "MEMORY",  # Use memory for temporary tables
            "locking_mode": "NORMAL",  # Normal locking mode
            "query_only": "OFF",  # Allow writes
        }
        
        for pragma, value in pragmas.items():
            try:
                conn.execute(f"PRAGMA {pragma}={value}")
            except Exception as e:
                logger.warning(f"Failed to set PRAGMA {pragma}={value}: {e}")
    
    @contextmanager
    def get_cursor(self):
        """
        Context manager for database operations
        Automatically commits on success, rolls back on exception
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
            logger.debug(f"Committed transaction")
        except Exception as e:
            conn.rollback()
            logger.error(f"Rolled back transaction due to: {e}")
            raise
        finally:
            cursor.close()
    
    def execute_script(self, script: str) -> None:
        """Execute a SQL script (used for schema initialization)"""
        conn = self._get_connection()
        try:
            conn.executescript(script)
            conn.commit()
            logger.info("Script executed successfully")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to execute script: {e}")
            raise
    
    def verify_integrity(self) -> bool:
        """Run PRAGMA quick_check for database integrity"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("PRAGMA quick_check")
                result = cursor.fetchone()
                is_ok = result and result[0] == "ok"
                
                if is_ok:
                    logger.info("Database integrity check: OK ✓")
                else:
                    logger.error(f"Database integrity check failed: {result}")
                
                return is_ok
        except Exception as e:
            logger.error(f"Database integrity check error: {e}")
            return False
    
    def close(self):
        """Manually close the thread-local connection"""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
                self._local.connection = None
                logger.debug(f"Closed connection for thread {threading.current_thread().name}")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")


# Global connection instance
db_connection = DatabaseConnection()
