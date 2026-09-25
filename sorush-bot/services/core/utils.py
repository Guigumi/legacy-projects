"""
Core Utilities Module - Funcoes auxiliares para formatacao
"""
from typing import Optional
import discord

# Re-export from embed_helpers for backward compatibility
from services.embed_helpers import format_time, format_number


# ======================== TEXT UTILITIES ========================

def count_n_words(text: str) -> int:
    """Conta o numero de palavras em um texto"""
    if not text:
        return 0
    words = text.split()
    return len(words)


# ======================== DEPRECATED ========================
# format_time and format_number are now in services/embed_helpers.py
# Re-exported here for backward compatibility.
