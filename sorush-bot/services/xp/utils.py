"""
XP Utilities - Funcoes e constantes compartilhadas do sistema de XP
"""
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# ======================== CONSTANTS ========================

# Ranking emojis
RANK_EMOJIS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

# Cooldown para XP de mensagem (em segundos)
# 3s permite XP durante conversas normais, mas evita spam
MESSAGE_XP_COOLDOWN = 3

# ======================== XP HELPERS ========================

def create_progress_bar(current: int, total: int, length: int = 10) -> str:
    """Create visual progress bar"""
    if total <= 0:
        return "▱" * length

    progress = min(current / total, 1.0)
    filled = int(progress * length)
    empty = length - filled

    bar = "▰" * filled + "▱" * empty
    return bar


def calculate_level(xp: int) -> Tuple[int, int, int]:
    """
    Calculate level based on XP
    Returns: (level, current_xp_in_level, xp_needed_for_next)

    Formula: XP = 100 * level^1.5
    """
    if xp < 0:
        logger.warning(f"Negative XP detected: {xp}, clamping to 0")
        xp = 0

    level = 0
    total_xp_for_level = 0
    max_iterations = 10000

    for _ in range(max_iterations):
        xp_for_next = int(100 * ((level + 1) ** 1.5))
        if xp < total_xp_for_level + xp_for_next:
            break
        total_xp_for_level += xp_for_next
        level += 1

    xp_in_current_level = max(0, xp - total_xp_for_level)  # Garantir nao-negativo
    xp_for_next_level = int(100 * ((level + 1) ** 1.5))

    logger.debug(
        f"Level calculated: xp={xp}, level={level}, current={xp_in_current_level}, next_required={xp_for_next_level}"
    )
    return level, xp_in_current_level, xp_for_next_level


def format_xp(xp: int) -> str:
    """Format XP with separators"""
    if xp >= 1_000_000:
        return f"{xp/1_000_000:.1f}M"
    elif xp >= 1_000:
        return f"{xp/1_000:.1f}K"
    return f"{xp:,}"


async def assign_role_safely(member, role, reason: str = "Level up") -> bool:
    """
    Safely assign a role to a member with logging
    Returns True if successful, False otherwise
    """
    if not member or not role:
        logger.warning("Cannot assign role: invalid member or role")
        return False

    if role in member.roles:
        logger.debug(f"Member {member.id} already has role {role.id}")
        return True

    try:
        await member.add_roles(role, reason=reason)
        logger.info(
            f"Role assigned: {role.name} to {member.id} ({member.name}) in guild {member.guild.id}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to assign role {role.id} to {member.id}: {e}")
        return False
