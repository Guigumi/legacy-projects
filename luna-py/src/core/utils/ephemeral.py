"""
Helpers para mensagens ephemerals de contexto.
Define autodelete curto (3–5s) para respostas ephemerals puramente informativas
que não possuem view.
"""
from __future__ import annotations

from typing import Any, Sequence

import discord
from discord.ext import commands

# Evita aplicar o patch múltiplas vezes
_PATCHED = False


def _estimate_length(content: Any | None, embed: discord.Embed | None, embeds: Sequence[discord.Embed] | None) -> int:
    length = len(str(content)) if content else 0

    def _len_embed(e: discord.Embed | None) -> int:
        if not e:
            return 0
        total = len(e.title or "") + len(e.description or "")
        for field in e.fields:
            total += len(field.name or "") + len(field.value or "")
        if e.footer and e.footer.text:
            total += len(e.footer.text)
        return total

    length += _len_embed(embed)
    if embeds:
        length += sum(_len_embed(e) for e in embeds)
    return length


def _default_delete_after(content: Any | None, embed: discord.Embed | None, embeds: Sequence[discord.Embed] | None) -> float:
    # Mensagens curtas somem mais rápido; mensagens com mais texto ficam 5s.
    return 3.0 if _estimate_length(content, embed, embeds) <= 180 else 5.0


def _should_autodelete(kwargs: dict[str, Any]) -> bool:
    # Mensagens efêmeras não podem ser deletadas pelo bot via API (o Discord não permite).
    return False


def patch_ephemeral_autodelete() -> None:
    """Adiciona delete_after automático a respostas ephemerals sem view.

    • InteractionResponse.send_message
    • commands.Context.send (híbridos)
    """
    global _PATCHED
    if _PATCHED:
        return

    async def _wrap_send_message(self, *args: Any, **kwargs: Any):
        if _should_autodelete(kwargs):
            kwargs["delete_after"] = _default_delete_after(
                kwargs.get("content"), kwargs.get("embed"), kwargs.get("embeds")
            )
        return await _orig_send_message(self, *args, **kwargs)

    async def _wrap_ctx_send(self, *args: Any, **kwargs: Any):
        if _should_autodelete(kwargs):
            kwargs["delete_after"] = _default_delete_after(
                kwargs.get("content"), kwargs.get("embed"), kwargs.get("embeds")
            )
        return await _orig_ctx_send(self, *args, **kwargs)

    _orig_send_message = discord.InteractionResponse.send_message
    _orig_ctx_send = commands.Context.send

    discord.InteractionResponse.send_message = _wrap_send_message  # type: ignore[assignment]
    commands.Context.send = _wrap_ctx_send  # type: ignore[assignment]

    _PATCHED = True
