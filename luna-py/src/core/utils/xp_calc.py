"""
Fórmulas matemáticas para cálculo de XP e níveis.
Centralizado para evitar dependências circulares entre serviços.
"""

from __future__ import annotations

import math


def xp_for_level(level: int, xp_per_level: int | None = None) -> int:
    """XP total necessário para alcançar um nível.

    Usa curva exponencial: xp_per_level * level^1.5
    Se xp_per_level não for fornecido ou for <= 0, usa o padrão de 100.
    """
    base = xp_per_level if xp_per_level is not None and xp_per_level > 0 else 100
    return int(base * (level**1.5))


def calculate_level(xp: int, xp_per_level: int | None = None) -> int:
    """Calcula o nível baseado no XP total — O(1) via inversão matemática.

    Curva exponencial: xp = base * level^1.5  →  level = (xp / base)^(2/3)

    Sempre retorna no mínimo 1.
    """
    if xp <= 0:
        return 1

    base = xp_per_level if xp_per_level is not None and xp_per_level > 0 else 100
    level = int(math.floor((xp / base) ** (2.0 / 3.0)))

    # Verificação de borda: garantir que o nível calculado é correto
    # (protege contra imprecisão de ponto flutuante na curva quadrática)
    while xp >= xp_for_level(level + 1, xp_per_level):
        level += 1

    return max(1, level)
