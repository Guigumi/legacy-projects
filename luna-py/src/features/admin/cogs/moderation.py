from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from config.settings import BotEmojis


class ModerationCog(commands.Cog, name="Moderação"):
    """Comandos administrativos e moderação."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot


# ── Context Menus (devem ser definidos no módulo, não na classe) ────────────

@app_commands.context_menu(name="Advertir")
async def warn_context_menu(interaction: discord.Interaction, member: discord.Member) -> None:
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            embed=EmbedBuilder.error_user("Você não tem permissão para advertir membros.").build(),
            ephemeral=True,
        )
        return

    if member.bot:
        await interaction.response.send_message(
            embed=EmbedBuilder.error_user("Você não pode advertir bots.").build(),
            ephemeral=True,
        )
        return

    if member.id == interaction.user.id:
        await interaction.response.send_message(
            embed=EmbedBuilder.error_user("Você não pode se advertir.").build(),
            ephemeral=True,
        )
        return

    cog: ModerationCog | None = interaction.client.cogs.get("Moderação")  # type: ignore
    if not cog:
        await interaction.response.send_message("Serviço indisponível.", ephemeral=True)
        return

    total = await cog.bot.user_service.add_warning(interaction.guild_id, member.id)

    embed = (
        EmbedBuilder.success(f"Aviso aplicado a {member.display_name}")
        .description(f"{BotEmojis.STATUS_WARNING} O usuário agora possui **{total}** avisos.")
        .footer(f"Executor: {interaction.user}")
        .build()
    )

    await interaction.response.send_message(embed=embed)

    # Tentar avisar o usuário na DM
    try:
        await member.send(
            f"Olá {member.display_name}, você recebeu uma advertência no servidor **{interaction.guild.name}**.\n"
            f"Total de avisos: **{total}**"
        )
    except Exception:
        pass


async def setup(bot: LunaBot) -> None:
    await bot.add_cog(ModerationCog(bot))
    bot.tree.add_command(warn_context_menu)
