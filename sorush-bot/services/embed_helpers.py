"""
Embed Helpers - Standardized embed creation following Instructions.md

All embeds use consistent colors, separators, and formatting.
Import these helpers instead of creating raw embeds.
"""
import discord
from typing import Optional, List
from config import Colors


# ======================== SEPARATORS ========================
SEP_LINE = "────────"
SEP_TITLE = "──────── ✦ ────────"
SEP_SPACER = "✦"
BULLET = "▸"


# ======================== EMBED BUILDERS ========================

def embed_success(description: str, title: Optional[str] = None, footer: Optional[str] = None) -> discord.Embed:
    """Standard success embed"""
    embed = discord.Embed(
        title=title or "✅ Feito",
        description=description,
        color=Colors.SUCCESS
    )
    if footer:
        embed.set_footer(text=footer)
    return embed


def embed_error(description: str, title: Optional[str] = None, footer: Optional[str] = None) -> discord.Embed:
    """User error embed (wrong input, missing perms, etc)"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=Colors.USER_ERROR
    )
    if footer:
        embed.set_footer(text=footer)
    return embed


def embed_internal_error(footer: Optional[str] = None) -> discord.Embed:
    """Internal error embed - never expose details"""
    embed = discord.Embed(
        description="algo deu errado. tente novamente ou reporte ao suporte.",
        color=Colors.ERROR
    )
    if footer:
        embed.set_footer(text=footer)
    return embed


def embed_warning(description: str, title: Optional[str] = None) -> discord.Embed:
    """Warning/alert embed"""
    return discord.Embed(
        title=title,
        description=description,
        color=Colors.WARNING
    )


def embed_info(description: str, title: Optional[str] = None, footer: Optional[str] = None) -> discord.Embed:
    """Neutral information embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=Colors.PRIMARY
    )
    if footer:
        embed.set_footer(text=footer)
    return embed


def embed_loading(text: str = "verificando…") -> discord.Embed:
    """Loading/deferred feedback embed"""
    return discord.Embed(
        description=f"⏳ {text}",
        color=Colors.PRIMARY
    )


def embed_cooldown(retry_after: float) -> discord.Embed:
    """Cooldown embed"""
    return discord.Embed(
        description=f"relaxe! tente novamente em **{retry_after:.0f}s**",
        color=Colors.USER_ERROR
    )


def embed_no_permission() -> discord.Embed:
    """Permission denied embed"""
    return discord.Embed(
        description="você não tem permissão para isso.",
        color=Colors.USER_ERROR
    )


def embed_disabled(feature: str = "essa funcionalidade") -> discord.Embed:
    """Feature disabled embed"""
    return discord.Embed(
        description=f"{feature} está desativada neste servidor.",
        color=Colors.WARNING
    )


# ======================== STAT FORMATTING ========================

def stat_value(value: str) -> str:
    """Wrap a stat value in backticks"""
    return f"```{value}```"


def spacer_field() -> dict:
    """Returns a spacer field dict for embed.add_field(**spacer_field())"""
    return {"name": "  ✦", "value": "  ✦", "inline": True}


def section_header(title: str) -> str:
    """Returns a section header like: ─────〔 Title 〕─────"""
    return f"─────〔 {title} 〕─────"


def format_number(number: int) -> str:
    """Format number with dot separators"""
    return f"{number:,}".replace(',', '.')


def format_time(minutes: int) -> str:
    """Format minutes to readable format"""
    if minutes <= 0:
        return "0m"
    
    days = minutes // (24 * 60)
    remaining = minutes % (24 * 60)
    hours = remaining // 60
    mins = remaining % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0:
        parts.append(f"{mins}m")
    
    return " ".join(parts) if parts else "0m"
