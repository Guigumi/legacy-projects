"""
Repositório base com helpers compartilhados.
"""

from __future__ import annotations

from core.database import Database


class BaseRepository:
    """Classe base para todos os repositórios."""

    def __init__(self, db: Database) -> None:
        self.db = db
