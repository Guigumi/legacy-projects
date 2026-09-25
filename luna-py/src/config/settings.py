
"""
Configuração central do Luna Bot.
Todas as constantes e padrões visuais ficam aqui.
Nada hardcoded nos cogs/services — tudo referencia este arquivo.
"""

import datetime
import os
from typing import Optional
from zoneinfo import ZoneInfo

import discord

from config.emojis import Emojis

# ── Fuso Horário Padrão (Brasília) ──────────────────────────────
BRT = ZoneInfo("America/Sao_Paulo")


def now_brt() -> datetime.datetime:
    """Retorna o datetime atual no fuso de Brasília (aware)."""
    return datetime.datetime.now(BRT)


# ── Versão ───────────────────────────────────────────────────────
VERSION = "26.7.4"














# ── Owner ────────────────────────────────────────────────────────
_DEFAULT_OWNER_ID = 832450162050859009
_owner_id_raw = os.getenv("OWNER_ID", "").strip()
if _owner_id_raw:
    try:
        OWNER_ID = int(_owner_id_raw)
    except ValueError as exc:
        raise RuntimeError(
            "OWNER_ID inválido. Configure um inteiro no .env, ex.: "
            "OWNER_ID=832450162050859009"
        ) from exc
else:
    OWNER_ID = _DEFAULT_OWNER_ID


# ── Ambiente e Emojis ────────────────────────────────────────────
BOT_ENV = os.getenv("BOT_ENV", "prod").strip().lower() or "prod"
_IS_PROD = BOT_ENV == "prod"

class BotEmojis:
    """
    Classe dinâmica que provê os emojis certos para o ambiente.
    Em 'prod', usa estritamente os customizados (índice 0).
    Em outros, usa o fallback (índice 1).
    """
    pass

# Popula BotEmojis automaticamente a partir de config.emojis.Emojis
for _name, _value in vars(Emojis).items():
    if not _name.startswith("_") and isinstance(_value, tuple):
        # Seleciona: 0 (Custom) se PROD, senão 1 (Fallback)
        _idx = 0 if _IS_PROD else 1
        setattr(BotEmojis, _name, _value[_idx])


# ── Cores Padronizadas ───────────────────────────────────────────
class Colors:
    ERROR_INTERNAL = discord.Color(0xFF4444)  # Erro interno do bot
    ERROR_USER = discord.Color(0xFF9999)  # Erro do usuário
    ALERT = discord.Color(0xFFFACE)  # Aviso/alerta
    DEFAULT = discord.Color(0x820909)  # Cor padrão (#820909)
    SUCCESS = discord.Color(0x90FF90)  # Operação bem-sucedida
    GAMES = discord.Color(0xAAAAFF)  # Relacionado a jogos


# ── Separadores Visuais ──────────────────────────────────────────
class Separators:
    LINE = "────────"
    STAR = "──────── ✦ ────────"
    TITLED = "─────〔 {title} 〕─────"
    DIAMOND = "✦"
    DIAMOND_S = "・" #DOT same name for compatibility
    ARROW_R = "▸"
    ARROW_L = "◂"
    ARROW_U = "▴"
    ARROW_D = "▾"

    @classmethod
    def title(cls, text: str) -> str:
        return cls.TITLED.format(title=text)


# ── Mensagens de Erro Humanizadas ────────────────────────────────
class ErrorMessages:
    NO_PERMISSION = "Você não tem permissão para isso."
    INVALID_PARAM = "Isso não é válido. Tente: `{example}`"
    COOLDOWN = "Relaxe! Tente novamente em {seconds}s."
    INTERNAL = "Algo deu errado. Se persistir, reporte ao suporte."
    NOT_FOUND = "Não encontrei o que você procura."
    DISABLED = "Essa funcionalidade está desativada neste servidor."


# ── Padrões do Bot ───────────────────────────────────────────────
class Defaults:
    """Configurações padrão do bot (valores usados quando não configurados por servidor)."""

    PREFIX: str = "!"
    ACTIVITY_STATUS: str = "Observando o servidor"
    EMBED_FOOTER: str = "Luna Bot • Use /help para mais informações"
    COOLDOWN_SECONDS: int = 5
    TRACKING_ENABLED: bool = True
    LOG_CHANNEL_ID: Optional[int] = None

    # Links públicos (opcionais — configure no .env para exibir botões no /about)
    INVITE_URL: str = os.getenv("BOT_INVITE_URL", "").strip()
    SUPPORT_URL: str = os.getenv("BOT_SUPPORT_URL", "").strip()



# ── Tracking de Voz ──────────────────────────────────────────────
class TrackingConfig:
    """Parâmetros relacionados ao tracking de voz."""

    VOICE_MIN_SECONDS: int = 5
    VOICE_FLUSH_INTERVAL_SECONDS: int = 300
    VOICE_CHECKPOINT_SECONDS: int = 600
