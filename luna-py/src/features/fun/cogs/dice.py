"""
Cog de dados — detecta notação de dados em mensagens sem prefixo.
Formatos suportados:
  d20        → 1d20
  50d100     → 50d100
  d20+5      → 1d20 + 5
  d20-10     → 1d20 - 10
"""

from __future__ import annotations

import logging
import random
import re

import discord
from discord.ext import commands

from config.settings import BotEmojis, Colors
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder

logger = logging.getLogger(__name__)

# Regex: captura opcional quantidade, "d", lados, opcional modificador (+/- número)
DICE_RE = re.compile(
    r"^(\d{0,4})d(\d{1,5})([+-]\d{1,5})?$",
    re.IGNORECASE,
)

MAX_DICE = 100  # máximo de dados por rolagem
MAX_SIDES = 10_000  # máximo de lados
MAX_MODIFIER = 10_000


class DiceCog(commands.Cog):
    """Detecta e rola dados automaticamente no chat."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot

    @commands.command(name="dados", aliases=["dado"])
    async def dados_cmd(self, ctx: commands.Context) -> None:
        """Instrui o usuário sobre como usar o sistema de dados."""
        embed = EmbedBuilder.error_user(
            "Para rolar dados, digite a notação direto no chat.\n"
            "Exemplos: `d20`, `2d6`, `d10+5`"
        ).build()
        await ctx.reply(embed=embed, mention_author=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Ignorar bots e DMs
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()

        # Rejeitar rapidamente mensagens que não parecem dados
        if not content or "d" not in content.lower():
            return

        match = DICE_RE.match(content)
        if not match:
            return

        # ── Parsing ───────────────────────────────────────────
        raw_qty, raw_sides, raw_mod = match.groups()
        qty = int(raw_qty) if raw_qty else 1
        sides = int(raw_sides)
        modifier = int(raw_mod) if raw_mod else 0

        # ── Validação ────────────────────────────────────────
        if qty < 1 or qty > MAX_DICE:
            embed = EmbedBuilder.error_user(
                f"Quantidade de dados deve ser entre **1** e **{MAX_DICE}**."
            ).build()
            await message.reply(embed=embed, delete_after=10)
            return

        if sides < 2 or sides > MAX_SIDES:
            embed = EmbedBuilder.error_user(
                f"Um dado precisa ter entre **2** e **{MAX_SIDES}** lados."
            ).build()
            await message.reply(embed=embed, delete_after=10)
            return

        if abs(modifier) > MAX_MODIFIER:
            embed = EmbedBuilder.error_user(
                f"Modificador deve ser entre **-{MAX_MODIFIER}** e **+{MAX_MODIFIER}**."
            ).build()
            await message.reply(embed=embed, delete_after=10)
            return

        # ── Rolagem ──────────────────────────────────────────
        rolls = [random.randint(1, sides) for _ in range(qty)]
        total = sum(rolls) + modifier

        # ── Formatação ───────────────────────────────────────
        # Notação legível
        notation = f"{qty}d{sides}"
        if modifier > 0:
            notation += f"+{modifier}"
        elif modifier < 0:
            notation += str(modifier)

        # Montar descrição
        if qty == 1:
            result_line = f"**{rolls[0]}**"
            if modifier:
                sign = "+" if modifier > 0 else ""
                result_line += f" ({sign}{modifier}) = **{total}**"
        else:
            # Mostrar dados individuais (limitar a 30 para não poluir)
            if qty <= 30:
                dice_str = ", ".join(str(r) for r in rolls)
            else:
                shown = ", ".join(str(r) for r in rolls[:25])
                dice_str = f"{shown}, ... (+{qty - 25} dados)"

            result_line = f"`[{dice_str}]`"
            if modifier:
                sign = "+" if modifier > 0 else ""
                result_line += f" ({sign}{modifier})"
            result_line += f"\n**Total: {total}**"

        embed = (
            EmbedBuilder.default()
            .color(Colors.GAMES)
            .title(f"{BotEmojis.COMMON_GAMES} Rolagem de Dados")
            .author(
                name=f"{message.author.display_name} rolou {notation}",
                icon_url=message.author.display_avatar.url,
            )
            .description(result_line)
            .build()
        )

        # Remover o footer padrão para manter limpo
        embed.set_footer(text=notation)

        await message.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DiceCog(bot))
