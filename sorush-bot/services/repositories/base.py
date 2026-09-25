"""
Base Repository Class
Abstract base for all repository implementations
Provides common database operations and patterns
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from abc import ABC, abstractmethod
from services.connection import db_connection

logger = logging.getLogger(__name__)


class BaseRepository(ABC):
    """Abstract base repository for all data access operations"""
    
    def __init__(self):
        self.connection = db_connection
    
    @abstractmethod
    def _get_table_name(self) -> str:
        """Return the table name this repository manages"""
        pass
    
    def exists(self, **filters) -> bool:
        """Check if a record exists with given filters"""
        query = f"SELECT 1 FROM {self._get_table_name()} WHERE " + \
                " AND ".join(f"{k} = ?" for k in filters.keys()) + " LIMIT 1"
        
        with self.connection.get_cursor() as cursor:
            cursor.execute(query, tuple(filters.values()))
            return cursor.fetchone() is not None
    
    def find_one(self, **filters) -> Optional[Dict[str, Any]]:
        """Find a single record by filters"""
        query = f"SELECT * FROM {self._get_table_name()} WHERE " + \
                " AND ".join(f"{k} = ?" for k in filters.keys()) + " LIMIT 1"
        
        with self.connection.get_cursor() as cursor:
            cursor.execute(query, tuple(filters.values()))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def find_all(self, **filters) -> List[Dict[str, Any]]:
        """Find all records matching filters"""
        if not filters:
            query = f"SELECT * FROM {self._get_table_name()}"
            with self.connection.get_cursor() as cursor:
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        
        query = f"SELECT * FROM {self._get_table_name()} WHERE " + \
                " AND ".join(f"{k} = ?" for k in filters.keys())
        
        with self.connection.get_cursor() as cursor:
            cursor.execute(query, tuple(filters.values()))
            return [dict(row) for row in cursor.fetchall()]
    
    def count(self, **filters) -> int:
        """Count records matching filters"""
        if not filters:
            query = f"SELECT COUNT(*) FROM {self._get_table_name()}"
            with self.connection.get_cursor() as cursor:
                cursor.execute(query)
                return cursor.fetchone()[0]
        
        query = f"SELECT COUNT(*) FROM {self._get_table_name()} WHERE " + \
                " AND ".join(f"{k} = ?" for k in filters.keys())
        
        with self.connection.get_cursor() as cursor:
            cursor.execute(query, tuple(filters.values()))
            return cursor.fetchone()[0]
    
    def create(self, **data) -> Optional[Dict[str, Any]]:
        """Create a new record (must be overridden for specific logic)"""
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        query = f"INSERT INTO {self._get_table_name()} ({columns}) VALUES ({placeholders})"
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, tuple(data.values()))
                logger.debug(f"Created record in {self._get_table_name()}")
        except Exception as e:
            logger.error(f"Failed to create record: {e}")
            raise
        
        return self.find_one(**{k: v for k, v in data.items() if k in ['id', 'guild_id', 'user_id']})
    
    def update(self, filters: Dict[str, Any], **data) -> bool:
        """Update records matching filters"""
        if not data:
            return False
        
        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        query = f"UPDATE {self._get_table_name()} SET {set_clause} WHERE " + \
                " AND ".join(f"{k} = ?" for k in filters.keys())
        
        values = list(data.values()) + list(filters.values())
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, values)
                affected = cursor.rowcount
                logger.debug(f"Updated {affected} record(s) in {self._get_table_name()}")
                return affected > 0
        except Exception as e:
            logger.error(f"Failed to update record: {e}")
            raise
    
    def delete(self, **filters) -> int:
        """Delete records matching filters"""
        query = f"DELETE FROM {self._get_table_name()} WHERE " + \
                " AND ".join(f"{k} = ?" for k in filters.keys())
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, tuple(filters.values()))
                affected = cursor.rowcount
                logger.debug(f"Deleted {affected} record(s) from {self._get_table_name()}")
                return affected
        except Exception as e:
            logger.error(f"Failed to delete record: {e}")
            raise
    
    def raw_query(self, sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        """Execute a raw SQL query and return results"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Raw query failed: {e}")
            raise
