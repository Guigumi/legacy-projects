"""
XP Role Repository
Handles all XP role configuration operations

Note: The database stores level_required, but the application logic uses XP.
This repository handles the conversion between XP and levels automatically.
"""
import logging
from typing import Dict, List, Optional
from services.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


def calculate_level_from_xp(xp: int) -> int:
    """Calculate level based on XP (same formula as in _xp_utils.py)"""
    if xp < 0:
        return 0
    
    level = 0
    total_xp_for_level = 0
    
    for _ in range(10000):  # Safety limit
        xp_for_next = int(100 * ((level + 1) ** 1.5))
        if xp < total_xp_for_level + xp_for_next:
            break
        total_xp_for_level += xp_for_next
        level += 1
    
    return level


def calculate_xp_from_level(level: int) -> int:
    """Calculate minimum XP needed for a level"""
    if level <= 0:
        return 0
    
    total_xp = 0
    for lv in range(1, level + 1):
        total_xp += int(100 * (lv ** 1.5))
    
    return total_xp


class XPRoleRepository(BaseRepository):
    """Repository for XP role operations"""
    
    def _get_table_name(self) -> str:
        return "xp_roles"
    
    def get_role(self, guild_id: int, role_id: int) -> Optional[Dict]:
        """Get XP role configuration"""
        return self.find_one(guild_id=guild_id, role_id=role_id)
    
    def get_all_roles(self, guild_id: int) -> List[Dict]:
        """Get all XP roles for a guild"""
        return self.find_all(guild_id=guild_id)
    
    def get_roles_dict(self, guild_id: int) -> Dict[str, int]:
        """
        Get XP roles as dict {role_id: xp_required}
        For backward compatibility with JSON format (which stored XP, not levels)
        """
        roles = self.get_all_roles(guild_id)
        # Convert level_required back to XP for compatibility
        return {str(role['role_id']): calculate_xp_from_level(role['level_required']) for role in roles}
    
    def add_role(self, guild_id: int, role_id: int, xp_required: int) -> bool:
        """
        Add or update XP role
        
        Args:
            xp_required: The XP amount required (will be converted to level for storage)
        """
        try:
            # Convert XP to level for storage
            level_required = calculate_level_from_xp(xp_required)
            
            existing = self.get_role(guild_id, role_id)
            
            if existing:
                # Update existing
                return self.update(
                    filters={'guild_id': guild_id, 'role_id': role_id},
                    level_required=level_required
                )
            else:
                # Create new
                self.create(
                    guild_id=guild_id,
                    role_id=role_id,
                    level_required=level_required
                )
                logger.info(f"Added XP role {role_id} ({xp_required} XP = level {level_required}) for guild {guild_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to add XP role {role_id} for guild {guild_id}: {e}")
            return False
    
    def remove_role(self, guild_id: int, role_id: int) -> bool:
        """Remove XP role"""
        try:
            self.delete(guild_id=guild_id, role_id=role_id)
            logger.info(f"Removed XP role {role_id} from guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove XP role {role_id} from guild {guild_id}: {e}")
            return False
    
    def get_roles_for_xp(self, guild_id: int, xp: int) -> List[int]:
        """Get all role IDs that should be assigned at given XP or below"""
        level = calculate_level_from_xp(xp)
        return self.get_roles_for_level(guild_id, level)
    
    def get_roles_for_level(self, guild_id: int, level: int) -> List[int]:
        """Get all role IDs that should be assigned at given level or below"""
        query = f"""
            SELECT role_id FROM {self._get_table_name()}
            WHERE guild_id = ? AND level_required <= ?
            ORDER BY level_required ASC
        """
        
        with self.connection.get_cursor() as cursor:
            cursor.execute(query, (guild_id, level))
            return [row[0] for row in cursor.fetchall()]
    
    def clear_all_roles(self, guild_id: int) -> bool:
        """Remove all XP roles for a guild"""
        try:
            self.delete(guild_id=guild_id)
            logger.info(f"Cleared all XP roles for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear XP roles for guild {guild_id}: {e}")
            return False


# Singleton instance
xp_role_repo = XPRoleRepository()
