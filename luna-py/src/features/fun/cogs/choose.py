"""
Cog choose — o bot escolhe aleatoriamente entre opções dadas.
Uso: !choose opção1 ! opção2 ! opção3
"""

from __future__ import annotations

import random

from discord import app_commands
from discord.ext import commands

from config.settings import Colors, BotEmojis
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder

_FILTER_EMOJI = BotEmojis.FILTER


class ChooseCog(commands.Cog):
    """Comando para escolher aleatoriamente entre opções."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="choose",
        aliases=["escolher", "pick"],
        description="Escolhe aleatoriamente entre as opções dadas (separe com !)",
    )
    @app_commands.describe(
        options="Opções separadas por ! (ex: pizza ! hambúrguer ! sushi)"
    )
    async def choose(self, ctx: commands.Context, *, options: str) -> None:
        # Separar por "!" e limpar espaços
        choices = [c.strip() for c in options.split("!") if c.strip()]

        if len(choices) < 2:
            embed = EmbedBuilder.error_user(
                "Dê pelo menos **2 opções** separadas por `!`\n"
                "Exemplo: `choose pão doce ! pão ! qualquer um`"
            ).build()
            await ctx.send(embed=embed, delete_after=5)
            return

        chosen = random.choice(choices)

        # Montar lista formatada
        options_list = "  ".join(f"`{c}`" for c in choices)

        embed = (
            EmbedBuilder.default()
            .color(Colors.GAMES)
            .title(f"{_FILTER_EMOJI} Escolha Aleatória")
            .author(
                name=f"{ctx.author.display_name} pediu para escolher",
                icon_url=ctx.author.display_avatar.url,
            )
            .description(f"**{chosen}**")
            .field(f"{_FILTER_EMOJI} Opções", options_list, inline=False)
            .build()
        )

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChooseCog(bot))
