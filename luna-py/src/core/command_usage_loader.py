"""Loader de mensagens de uso de comandos."""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_USAGES: dict[str, dict[str, str]] = {}


def _load_command_usages() -> dict[str, dict[str, str]]:
    """Carrega as mensagens de uso de comandos do arquivo JSON."""
    global _DEFAULT_USAGES
    if _DEFAULT_USAGES:
        return _DEFAULT_USAGES

    json_path = Path(__file__).parent / "command_usages.json"
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            _DEFAULT_USAGES = json.load(f)
        logger.debug("Command usages carregado: %d comandos", len(_DEFAULT_USAGES))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Arquivo command_usages.json não encontrado ou inválido: %s", exc)
        _DEFAULT_USAGES = {}

    return _DEFAULT_USAGES


def get_command_usage(command_name: str) -> dict[str, str] | None:
    """Retorna as informações de uso de um comando específico.
    
    Args:
        command_name: Nome completo do comando (ex: "autorole instant")
        
    Returns:
        Dict com "usage" e "example", ou None se não encontrado.
    """
    usages = _load_command_usages()
    return usages.get(command_name)


def format_missing_argument_error(command_name: str, param_name: str) -> dict[str, Any]:
    """Formata uma mensagem de erro para argumento faltante.
    
    Args:
        command_name: Nome do comando
        param_name: Nome do parâmetro faltante
        
    Returns:
        Dict com title e fields para embed.
    """
    usage = get_command_usage(command_name)
    
    if usage:
        return {
            "title": f"Parâmetro ausente: `{param_name}`",
            "fields": [
                ("Como usar", usage["usage"], False),
                ("Exemplo", usage["example"], False),
            ],
            "footer": "Slash commands (/comando) preenchem automaticamente",
        }
    
    return {
        "title": f"Faltou o parâmetro `{param_name}`",
        "description": f"Tente usar `/{command_name}` para ver os campos.",
        "fields": [],
        "footer": None,
    }
