"""
Shop Repository
Handles shop items and purchases in SQLite
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
from services.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ShopItemRepository(BaseRepository):
    """Repository for shop item operations"""
    
    def _get_table_name(self) -> str:
        return "shop_items"
    
    def get_items(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get all shop items for a guild"""
        return self.find_all(guild_id=guild_id)
    
    def get_item_by_role(self, guild_id: int, role_id: int) -> Optional[Dict[str, Any]]:
        """Get a shop item by role ID"""
        return self.find_one(guild_id=guild_id, role_id=role_id)
    
    def add_item(self, guild_id: int, role_id: int, price: int,
                 duration_type: str = "temporary", duration_days: int = 7,
                 condition: str = None, name: str = None) -> bool:
        """Add or update a shop item"""
        existing = self.get_item_by_role(guild_id, role_id)
        if existing:
            return self.update(
                filters={'guild_id': guild_id, 'role_id': role_id},
                price=price, duration_type=duration_type,
                duration_days=duration_days, condition=condition, name=name
            )
        
        try:
            self.create(
                guild_id=guild_id, role_id=role_id, price=price,
                duration_type=duration_type, duration_days=duration_days,
                condition=condition, name=name,
                created_at=datetime.now(timezone.utc).isoformat()
            )
            return True
        except Exception as e:
            logger.error(f"Failed to add shop item: {e}")
            return False
    
    def remove_item(self, guild_id: int, role_id: int) -> bool:
        """Remove a shop item"""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute(
                    "DELETE FROM shop_items WHERE guild_id = ? AND role_id = ?",
                    (guild_id, role_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to remove shop item: {e}")
            return False
    
    def update_item(self, guild_id: int, role_id: int, **kwargs) -> bool:
        """Update a shop item"""
        return self.update(filters={'guild_id': guild_id, 'role_id': role_id}, **kwargs)


class ShopPurchaseRepository(BaseRepository):
    """Repository for shop purchase operations"""
    
    def _get_table_name(self) -> str:
        return "shop_purchases"
    
    def add_purchase(self, guild_id: int, user_id: int, role_id: int,
                     duration_type: str = "temporary", duration_days: int = None,
                     condition: str = None) -> bool:
        """Record a purchase"""
        expires_at = None
        if duration_type == "temporary" and duration_days:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=duration_days)).isoformat()
        
        try:
            self.create(
                guild_id=guild_id, user_id=user_id, role_id=role_id,
                duration_type=duration_type, condition=condition,
                purchased_at=datetime.now(timezone.utc).isoformat(),
                expires_at=expires_at
            )
            return True
        except Exception as e:
            logger.error(f"Failed to add purchase: {e}")
            return False
    
    def get_user_purchases(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        """Get active purchases for a user"""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM shop_purchases
                    WHERE guild_id = ? AND user_id = ?
                    AND (expires_at IS NULL OR expires_at > ? OR duration_type != 'temporary')
                """, (guild_id, user_id, now))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get purchases: {e}")
            return []
    
    def get_expired_purchases(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get and remove expired purchases"""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM shop_purchases 
                    WHERE guild_id = ? AND duration_type = 'temporary'
                    AND expires_at IS NOT NULL AND expires_at <= ?
                """, (guild_id, now))
                expired = [dict(row) for row in cursor.fetchall()]
                
                if expired:
                    cursor.execute("""
                        DELETE FROM shop_purchases
                        WHERE guild_id = ? AND duration_type = 'temporary'
                        AND expires_at IS NOT NULL AND expires_at <= ?
                    """, (guild_id, now))
                
                return expired
        except Exception as e:
            logger.error(f"Failed to get expired purchases: {e}")
            return []


# Singleton instances
shop_item_repo = ShopItemRepository()
shop_purchase_repo = ShopPurchaseRepository()
