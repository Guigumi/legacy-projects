"""
Formatadores compartilhados — funções de exibição reutilizáveis.
"""

from __future__ import annotations


def fmt_voice(seconds: int) -> str:
    """Formata segundos de voz em string legível.

    Exemplos:
        45     → "45s"
        120    → "2m"
        3661   → "1h 1m"
        86400  → "24h 0m"
    """
    if seconds < 60:
        return f"{seconds}s"
    hours, rem = divmod(seconds, 3600)
    mins = rem // 60
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"
