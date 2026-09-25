"""
Enums e constantes utilizadas em todo o bot.
"""

import enum

from config.settings import BotEmojis


class Feature(enum.Enum):
    """Features que podem ser ativadas/desativadas por servidor."""

    TRACKING = "tracking"
    LEVELING = "leveling"
    LOGGING = "logging"
    MODERATION = "moderation"
    MINECRAFT = "minecraft"
    DOWNLOADS = "downloads"


class TrackingType(enum.Enum):
    MESSAGE = "message"
    VOICE = "voice"


class LogCategory(enum.Enum):
    """Categorias de log que podem ser ativadas/desativadas por servidor."""

    MESSAGES = "messages"  # Mensagens editadas/excluídas
    VOICE = "voice"  # Eventos de voz
    MEMBERS = "members"  # Entrada/saída de membros
    ROLES = "roles"  # Cargos criados/excluídos
    CHANNELS = "channels"  # Canais criados/excluídos
    MODERATION = "moderation"  # Bans/unbans
    BOT_EVENTS = "bot_events"  # Eventos internos (level up, config, etc.)
    WEEKLY_SUMMARY = "weekly_summary" # Resumo semanal de atividade


# Metadados visuais das categorias
LOG_CATEGORY_META: dict[LogCategory, tuple[str, str]] = {
    LogCategory.MESSAGES: (BotEmojis.COMMON_MESSAGE, "Mensagens"),
    LogCategory.VOICE: (BotEmojis.AUDIO_ON, "Voz"),
    LogCategory.MEMBERS: (BotEmojis.COMMON_USERS, "Membros"),
    LogCategory.ROLES: (BotEmojis.COMMON_TAG, "Cargos"),
    LogCategory.CHANNELS: (BotEmojis.COMMON_CHANNEL, "Canais"),
    LogCategory.MODERATION: (BotEmojis.COMMON_TOOLS, "Moderação"),
    LogCategory.BOT_EVENTS: (BotEmojis.ACTION_SETTINGS, "Eventos do Bot"),
    LogCategory.WEEKLY_SUMMARY: (BotEmojis.COMMON_LIST, "Resumo Semanal"),
}


class AutoRoleMode(enum.Enum):
    """Modos de entrega do AutoRole."""

    INSTANT = "instant"  # Cargo dado ao entrar
    TIMER = "timer"  # Cargo dado após X segundos
    BUTTON = "button"  # Membro clica em botão
    REACTION = "reaction"  # Membro reage à mensagem
