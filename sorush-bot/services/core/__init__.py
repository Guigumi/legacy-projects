"""
Módulos core do bot

Este pacote contém utilitarios centrais e re-exports de formatacao.

NOTA: Funcoes XP e formatacao mais complexas ficam em services/xp/utils.py
e services/embed_helpers.py.
"""
from .utils import (
    # Text
    count_n_words,
    # Formatting
    format_time,
    format_number,
)

__all__ = [
    # Text
    "count_n_words",
    # Formatting
    "format_time",
    "format_number",
]