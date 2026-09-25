"""Handlers modulares de erros para prefix commands."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Callable, Coroutine

from discord.ext import commands

from core.utils.embed_builder import EmbedBuilder
from config.settings import OWNER_ID
from core.command_usage_loader import format_missing_argument_error

if TYPE_CHECKING:
    from core.bot import LunaBot

logger = logging.getLogger(__name__)

ErrorHandler = Callable[["LunaBot", commands.Context, commands.CommandError], Coroutine[None, None, bool]]


class ErrorHandlerRegistry:
    """Registro de handlers de erro."""
    
    def __init__(self) -> None:
        self._handlers: list[ErrorHandler] = []
    
    def register(self, handler: ErrorHandler) -> ErrorHandler:
        """Decorator para registrar um handler."""
        self._handlers.append(handler)
        return handler
    
    async def handle(self, bot: "LunaBot", ctx: commands.Context, error: commands.CommandError) -> bool:
        """Tenta processar o erro com handlers registrados.
        
        Returns:
            True se o erro foi tratado, False caso contrário.
        """
        for handler in self._handlers:
            try:
                if await handler(bot, ctx, error):
                    return True
            except Exception as exc:
                logger.exception("Erro em handler: %s", exc)
        return False


registry = ErrorHandlerRegistry()


async def _send_error_embed(
    ctx: commands.Context,
    description: str,
    delete_after: float = 10.0,
    **embed_kwargs
) -> None:
    """Envia um embed de erro padronizado."""
    builder = EmbedBuilder.error_user(description)
    
    for field in embed_kwargs.get("fields", []):
        builder.field(field[0], field[1], field[2] if len(field) > 2 else False)
    
    if embed_kwargs.get("footer"):
        builder.footer(embed_kwargs["footer"])
    
    await ctx.send(embed=builder.build(), delete_after=delete_after)


@registry.register
async def handle_command_not_found(
    bot: "LunaBot",
    ctx: commands.Context,
    error: commands.CommandError
) -> bool:
    """Ignora comandos não encontrados."""
    if isinstance(error, commands.CommandNotFound):
        return True  # Handled: silenciosamente ignorado
    return False


@registry.register
async def handle_missing_required_argument(
    bot: "LunaBot",
    ctx: commands.Context,
    error: commands.CommandError
) -> bool:
    """Trata argumentos obrigatórios faltantes com mensagens de uso."""
    if not isinstance(error, commands.MissingRequiredArgument):
        return False
    
    cmd_name = ctx.command.qualified_name if ctx.command else "?"
    error_info = format_missing_argument_error(cmd_name, error.param.name)
    
    builder = EmbedBuilder.error_user(error_info.get("title", "Parâmetro ausente"))
    
    if error_info.get("description"):
        builder.description(error_info["description"])
    
    for name, value, inline in error_info.get("fields", []):
        builder.field(name, value, inline)
    
    if error_info.get("footer"):
        builder.footer(error_info["footer"])
    
    await ctx.send(embed=builder.build(), delete_after=15.0)
    return True


@registry.register
async def handle_cooldown(
    bot: "LunaBot",
    ctx: commands.Context,
    error: commands.CommandError
) -> bool:
    """Trata cooldown de comandos."""
    if not isinstance(error, commands.CommandOnCooldown):
        return False
    
    await _send_error_embed(
        ctx,
        f"Relaxe! Tente novamente em {error.retry_after:.0f}s.",
        delete_after=10
    )
    return True


@registry.register
async def handle_missing_permissions(
    bot: "LunaBot",
    ctx: commands.Context,
    error: commands.CommandError
) -> bool:
    """Trata falta de permissões do usuário."""
    if not isinstance(error, commands.MissingPermissions):
        return False
    
    await _send_error_embed(
        ctx,
        " Este é um comando de **administrador**.\n"
        "Você não tem permissão para executá-lo.",
        delete_after=10.0
    )
    return True


@registry.register
async def handle_not_owner(
    bot: "LunaBot",
    ctx: commands.Context,
    error: commands.CommandError
) -> bool:
    """Trata comandos restritos ao dono do bot."""
    if not isinstance(error, commands.NotOwner):
        return False
    
    is_update_cmd = bool(
        ctx.command and ctx.command.qualified_name.startswith("update")
    )
    is_owner = ctx.author.id == OWNER_ID
    dev_mode = getattr(bot, "_dev_mode", False)
    
    if is_update_cmd and is_owner and not dev_mode:
        message = (
            " `!update` exige **modo Dev ativo**.\n"
            "Digite `undead` (owner) e clique em **Ativar modo Dev**."
        )
    else:
        message = (
            " Este é um comando de **administrador**.\n"
            "Você não tem permissão para executá-lo."
        )
    
    await _send_error_embed(ctx, message, delete_after=10.0)
    return True


@registry.register
async def handle_bot_missing_permissions(
    bot: "LunaBot",
    ctx: commands.Context,
    error: commands.CommandError
) -> bool:
    """Trata quando o bot não tem permissões necessárias."""
    if not isinstance(error, commands.BotMissingPermissions):
        return False
    
    perms = ", ".join(error.missing_permissions)
    await _send_error_embed(
        ctx,
        f"Preciso das seguintes permissões: **{perms}**",
        delete_after=10
    )
    return True


@registry.register
async def handle_bad_argument(
    bot: "LunaBot",
    ctx: commands.Context,
    error: commands.CommandError
) -> bool:
    """Trata argumentos inválidos."""
    if not isinstance(error, (commands.BadArgument, commands.BadUnionArgument)):
        return False
    
    cmd_name = ctx.command.qualified_name if ctx.command else "?"
    await _send_error_embed(
        ctx,
        f"Argumento inválido. Verifique se digitou corretamente.\n"
        f"Tente: `/{cmd_name}` para ver os campos.",
        delete_after=10.0
    )
    return True


async def handle_unexpected_error(
    bot: "LunaBot",
    ctx: commands.Context,
    error: commands.CommandError
) -> None:
    """Handler padrão para erros não tratados."""
    logger.exception(
        "Erro não tratado no comando '%s': %s",
        ctx.command.qualified_name if ctx.command else "?",
        error,
    )
    try:
        await ctx.send(
            embed=EmbedBuilder.error_user("Ocorreu um erro inesperado. Tente novamente.").build(),
            delete_after=10.0,
        )
    except Exception:
        pass  # Canal pode ter sido deletado ou bot sem permissão
