import discord
from discord.ext import commands
import random
import re
import logging
from typing import List

from config import Colors
from services.embed_helpers import embed_cooldown

logger = logging.getLogger(__name__)


class Choose(commands.Cog):
    """Escolhe aleatoriamente entre opções fornecidas"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _parse_options(self, raw: str) -> List[str]:
        """Parse input into options list supporting |, , and quotes"""
        s = (raw or "").strip()
        if not s:
            return []

        # Prefer pipe if present
        if "|" in s:
            parts = [p.strip() for p in s.split("|")]
        elif "," in s:
            parts = [p.strip() for p in s.split(",")]
        else:
            # Split by whitespace but keep quoted groups
            parts = re.findall(r'"([^"]+)"|\'([^\']+)\'|([^\s]+)', s)
            # parts is list of tuples; pick non-empty group
            parts = [a or b or c for (a, b, c) in parts]

        # Remove empties and duplicates while preserving order
        seen = set()
        options: List[str] = []
        for p in parts:
            item = p.strip()
            if item and item not in seen:
                seen.add(item)
                options.append(item)
        return options

    @commands.hybrid_command(name="escolher", aliases=["choose", "pick"], description="Escolhe aleatoriamente entre opções")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def choose(self, ctx: commands.Context, *, opcoes: str):
        """
        Escolhe aleatoriamente entre opções
        Uso:
        - s!choose pizza | hambúrguer | sushi
        - s!choose "Dark Souls" | "Hollow Knight" | Celeste
        - s!choose opção1, opção2, opção3
        """
        options = self._parse_options(opcoes)
        if len(options) < 2:
            embed = discord.Embed(
                title="🎲 ops",
                description="preciso de pelo menos 2 opções\n\n**uso:** `s!choose pizza | hambúrguer`",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        choice = random.choice(options)

        embed = discord.Embed(title="", description=" ", color=Colors.SUCCESS)
        embed.add_field(name="─────〔 Choose 〕─────", value="", inline=False)
        embed.add_field(name="Escolhido", value=f"```{choice}```", inline=True)
        await ctx.send(embed=embed)

    @choose.error
    async def choose_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=embed_cooldown(error.retry_after), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Choose(bot))
