"""
Modelos de dados (Dataclasses) para representar as tabelas do banco de dados.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class UserData:
    guild_id: int
    user_id: int
    messages_sent: int = 0
    voice_seconds: int = 0
    xp: int = 0
    level: int = 1
    longest_voice: int = 0
    longest_message: int = 0
    warnings: int = 0
    last_active: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    selected_theme: str = 'default'
    coins: int = 0
    last_daily: Optional[str] = None
    daily_streak: int = 0
    unlocked_backgrounds: str = 'default'


    # Campos calculados em tempo de execução
    xp_next_level: Optional[int] = None
    xp_current_level: Optional[int] = None

    def __getitem__(self, item: str) -> Any:
        """Permite acessar os atributos como um dicionário para compatibilidade com código antigo."""
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def __setitem__(self, key: str, value: Any) -> None:
        """Permite modificar os atributos como um dicionário para compatibilidade."""
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            raise KeyError(key)

    def get(self, item: str, default: Any = None) -> Any:
        """Equivalente a dict.get()"""
        return getattr(self, item, default)

    @classmethod
    def from_row(cls, row: dict | None) -> "UserData | None":
        if not row:
            return None
        # Filtra apenas os campos que a dataclass conhece
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in dict(row).items() if k in valid_keys}
        return cls(**filtered)
