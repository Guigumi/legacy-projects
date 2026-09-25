"""
Sorush Bot Centralized Configuration
"""
import os
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _env_str(name: str, default: str = "") -> str:
    """Safely read a string env var with a default."""
    return os.getenv(name, default)


def _env_int(name: str, default: int = 0) -> int:
    """Safely read an int env var with a default."""
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default

# ======================== DIRECTORIES ========================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATABASE_DIR = DATA_DIR / "database"
TEMP_DIR = BASE_DIR / "temp_downloads"
LOGS_DIR = DATA_DIR / "logs"

# Create directories if they don't exist
for directory in [DATA_DIR, DATABASE_DIR, TEMP_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ======================== DATABASE ========================
DATABASE_PATH = DATABASE_DIR / "bot_data.db"

# ======================== BOT ========================
DISCORD_TOKEN: str = _env_str("DISCORD_TOKEN", "")
APPLICATION_ID: int = _env_int("APPLICATION_ID", 0)
OWNER_ID: int = 832450162050859009  # Bot owner ID for reports (change for your bot, i dont want to receive them)

BOT_PREFIX: Tuple[str, ...] = ("s!", "S!")
BOT_DESCRIPTION: str = "Use s! ou / para comandos."
BOT_ACTIVITY: str = "🤎 /help"
BOT_VERSION: str = "2.6.0"
BOT_UPDATE_DATE: str = "2026-01-04"

# ======================== XP SYSTEM ========================
XP_COOLDOWN_SECONDS: int = 5  # Time between XP gains per message
XP_PER_MESSAGE: Tuple[int, int] = (15, 25)  # XP range per message (min, max)
XP_PER_VOICE_MINUTE: int = 5  # XP per minute in voice call
XP_MESSAGE_FORMULA: int = 20  # Multiplier for calculating XP per messages
XP_VOICE_FORMULA: int = 5  # Multiplier for calculating XP per voice minutes

# Level formula: Required XP = BASE * (level ^ MULTIPLIER)
XP_LEVEL_BASE: int = 100
XP_LEVEL_MULTIPLIER: float = 1.5

# ======================== RATE LIMITS ========================
RATE_LIMIT_COMMANDS: int = 5  # seconds between moderation commands
RATE_LIMIT_MESSAGES: int = 1  # second between messages for counting

# ======================== CACHE ========================
CACHE_TTL_SECONDS: int = 300  # Cache time-to-live in seconds
CACHE_MAX_SIZE: int = 1000  # Maximum cache entries

# ======================== LOGGING ========================
LOG_LEVEL: str = _env_str("LOG_LEVEL", "INFO")

# ======================== EMBEDS ========================
SHOW_TIMESTAMP: bool = True  # Show timestamp in embeds

class Colors:
    """Default colors for embeds"""
    ERROR = 0xff4444
    USER_ERROR = 0xff9999
    WARNING = 0xffface
    PRIMARY = 0x90ffff
    SUCCESS = 0x90ff90
    GAMES = 0xaaaaff
    INFO = 0x90ffff       # Same as PRIMARY for info messages
    XP = 0xaaaaff         # Same as GAMES for XP-related messages

# ======================== EMOJIS ========================
EMOJI_SUCCESS = "✅"
EMOJI_ERROR = "❌"
EMOJI_WARNING = "⚠️"
EMOJI_LOADING = "⏳"

# Shortcuts for backward compatibility
EMBED_COLOR_PRIMARY = Colors.PRIMARY
EMBED_COLOR_SUCCESS = Colors.SUCCESS
EMBED_COLOR_ERROR = Colors.ERROR
EMBED_COLOR_WARNING = Colors.WARNING

# Constants used in battle.py (backward compatibility)
COLOR_ERROR = Colors.ERROR
COLOR_WARNING = Colors.WARNING

# ======================== VALIDATION ========================
def validate_config() -> bool:
    """Validates if required configurations are present"""
    errors = []
    
    if not DISCORD_TOKEN:
        errors.append("DISCORD_TOKEN not configured in .env")
    
    if not APPLICATION_ID:
        errors.append("APPLICATION_ID not configured in .env")
    
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(errors))
    
    return True