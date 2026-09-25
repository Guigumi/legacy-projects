"""
Transaction Repository
Handles all economy/mora transaction operations
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from services.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class TransactionRepository(BaseRepository):
    """Repository for economy transactions"""
    
    def _get_table_name(self) -> str:
        return "transactions"
    
    def create_transaction(self, guild_id: int, user_id: int, 
                          trans_type: str, amount: int, balance_after: int,
                          description: Optional[str] = None,
                          related_user_id: Optional[int] = None) -> Dict[str, Any]:
        """Create a transaction record"""
        data = {
            "guild_id": guild_id,
            "user_id": user_id,
            "type": trans_type,  # 'earn', 'spend', 'gamble', 'trade', etc.
            "amount": amount,
            "balance_after": balance_after,
            "description": description,
            "related_user_id": related_user_id,
            "created_at": datetime.now().isoformat(),
        }
        
        try:
            self.create(**data)
            logger.debug(f"Created transaction: {trans_type} {amount} mora for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to create transaction: {e}")
            raise
        
        # Return the created transaction
        return self.find_one(
            guild_id=guild_id,
            user_id=user_id,
            created_at=data['created_at']
        )

    def add_transaction(self, guild_id: int, user_id: int, trans_type: str, amount: int,
                        balance_after: int, description: Optional[str] = None,
                        related_user_id: Optional[int] = None) -> bool:
        """Compatibility helper for creating transactions"""
        try:
            self.create_transaction(
                guild_id=guild_id,
                user_id=user_id,
                trans_type=trans_type,
                amount=amount,
                balance_after=balance_after,
                description=description,
                related_user_id=related_user_id
            )
            return True
        except Exception:
            return False
    
    def get_user_transactions(self, guild_id: int, user_id: int,
                             limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Get recent transactions for a user"""
        query = """
            SELECT * FROM transactions
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, user_id, limit, offset))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get transactions: {e}")
            raise

    def get_transactions(self, guild_id: int, user_id: int,
                         limit: int = 10, transaction_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Compatibility helper for transaction history"""
        if transaction_type:
            if transaction_type == 'gambling':
                query = """
                    SELECT * FROM transactions
                    WHERE guild_id = ? AND user_id = ? AND (type = 'gambling_win' OR type = 'gambling_lose')
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                params = (guild_id, user_id, limit)
            else:
                query = """
                    SELECT * FROM transactions
                    WHERE guild_id = ? AND user_id = ? AND type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                params = (guild_id, user_id, transaction_type, limit)
        else:
            query = """
                SELECT * FROM transactions
                WHERE guild_id = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """
            params = (guild_id, user_id, limit)

        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get transaction history: {e}")
            return []

    def get_transaction_stats(self, guild_id: int, user_id: int, days: int = 7) -> Dict[str, int]:
        """Return transaction stats for the last N days"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total_earned,
                        COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as total_spent,
                        COUNT(*) as total_transactions
                    FROM transactions 
                    WHERE guild_id = ? AND user_id = ? 
                    AND datetime(created_at) >= datetime('now', '-' || ? || ' days')
                """, (guild_id, user_id, days))
                row = cursor.fetchone()
                return dict(row) if row else {'total_earned': 0, 'total_spent': 0, 'total_transactions': 0}
        except Exception as e:
            logger.error(f"Failed to get transaction stats: {e}")
            return {'total_earned': 0, 'total_spent': 0, 'total_transactions': 0}
    
    def get_user_balance_history(self, guild_id: int, user_id: int,
                                days: int = 7) -> List[Dict[str, Any]]:
        """Get user's balance history for the last N days"""
        before = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = """
            SELECT created_at, balance_after, type, amount
            FROM transactions
            WHERE guild_id = ? AND user_id = ? AND created_at > ?
            ORDER BY created_at DESC
        """
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, user_id, before))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get balance history: {e}")
            raise
    
    def get_earnings_by_type(self, guild_id: int, user_id: int) -> Dict[str, int]:
        """Get total earnings by transaction type"""
        query = """
            SELECT type, SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as earned
            FROM transactions
            WHERE guild_id = ? AND user_id = ?
            GROUP BY type
        """
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, user_id))
                return {row['type']: row['earned'] or 0 for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Failed to get earnings by type: {e}")
            raise
    
    def get_guild_transactions(self, guild_id: int, trans_type: Optional[str] = None,
                              limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all transactions for a guild, optionally filtered by type"""
        if trans_type:
            query = """
                SELECT * FROM transactions
                WHERE guild_id = ? AND type = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, trans_type, limit, offset))
                return [dict(row) for row in cursor.fetchall()]
        else:
            query = """
                SELECT * FROM transactions
                WHERE guild_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, limit, offset))
                return [dict(row) for row in cursor.fetchall()]
    
    def get_richest_users(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get richest users by final balance in transactions"""
        query = """
            SELECT DISTINCT ON (user_id) user_id, balance_after
            FROM transactions
            WHERE guild_id = ?
            ORDER BY user_id, created_at DESC
            LIMIT ?
        """
        
        # SQLite doesn't support DISTINCT ON, use a subquery instead
        query = """
            SELECT user_id, balance_after
            FROM (
                SELECT user_id, balance_after, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) as rn
                FROM transactions
                WHERE guild_id = ?
            ) WHERE rn = 1
            ORDER BY balance_after DESC
            LIMIT ?
        """
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.warning(f"ROW_NUMBER not supported, using fallback: {e}")
            # Fallback for SQLite without window functions
            return self._get_richest_users_fallback(guild_id, limit)
    
    def _get_richest_users_fallback(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Fallback method for getting richest users without window functions"""
        query = """
            SELECT user_id, MAX(balance_after) as balance
            FROM transactions
            WHERE guild_id = ?
            GROUP BY user_id
            ORDER BY balance DESC
            LIMIT ?
        """
        
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get richest users: {e}")
            raise
    
    def cleanup_old_transactions(self, guild_id: Optional[int] = None, 
                                days: int = 90) -> int:
        """Remove transactions older than N days"""
        before = (datetime.now() - timedelta(days=days)).isoformat()
        
        if guild_id:
            query = "DELETE FROM transactions WHERE guild_id = ? AND created_at < ?"
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (guild_id, before))
        else:
            query = "DELETE FROM transactions WHERE created_at < ?"
            with self.connection.get_cursor() as cursor:
                cursor.execute(query, (before,))
        
        deleted = cursor.rowcount
        logger.info(f"Cleaned up {deleted} old transactions")
        return deleted


# Singleton instance
transaction_repo = TransactionRepository()
