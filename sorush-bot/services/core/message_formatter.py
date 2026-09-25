"""
Message Formatter Module - Global error handling with standardized embeds
"""
import logging
import discord
from discord.ext import commands

from services.embed_helpers import (
    embed_error, embed_internal_error, embed_cooldown, embed_no_permission
)

logger = logging.getLogger(__name__)


async def on_error_handler(interaction: discord.Interaction, error: Exception):
    """Global slash command error handler"""
    embed = embed_internal_error()
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem de erro: {e}")


def create_error_handler(bot: commands.Bot) -> None:
    """Register global error handlers on the bot"""

    @bot.event
    async def on_command_error(ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=embed_no_permission(), delete_after=5)
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                embed=embed_error(f"argumento obrigatorio faltando: `{error.param.name}`"),
                delete_after=5
            )
            return

        if isinstance(error, commands.BadArgument):
            await ctx.send(
                embed=embed_error(f"argumento invalido: {error}"),
                delete_after=5
            )
            return

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                embed=embed_cooldown(error.retry_after),
                delete_after=5
            )
            return

        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=embed_no_permission(), delete_after=5)
            return

        # Internal error - never expose details
        logger.error(f"Erro no comando {ctx.command}: {error}", exc_info=error)
        try:
            await ctx.send(embed=embed_internal_error(), delete_after=10)
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem de erro: {e}")

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: Exception):
        embed = embed_internal_error()

        if isinstance(error, discord.app_commands.CommandOnCooldown):
            embed = embed_cooldown(error.retry_after)
        elif isinstance(error, discord.app_commands.MissingPermissions):
            embed = embed_no_permission()

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Erro ao enviar resposta de erro: {e}")

        if not isinstance(error, (discord.app_commands.CommandOnCooldown, discord.app_commands.MissingPermissions)):
            logger.error(f"Erro no slash command: {error}", exc_info=error)

    logger.info("✓ Error handlers registrados")
