import discord
from discord.ext import commands
import random
import re
import logging
from typing import Optional, Tuple, List
import asyncio

from config import Colors
from services.embed_helpers import embed_cooldown

logger = logging.getLogger(__name__)

# Cooldown tracking
user_cooldowns = {}
COOLDOWN_SECONDS = 1.5


class Dice(commands.Cog):
    """Dice rolling system for RPG"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _parse_dice_notation(self, notation: str) -> Optional[Tuple[int, int, int]]:
        """
        Parses advanced dice notation (e.g., 2d6+3, 3d10-2, d20)
        Returns (num_dice, sides, modifier) or None if invalid
        """
        notation = notation.lower().strip()
        pattern = r'^(\d*)d(\d+)([\+\-]\d+)?$'
        match = re.match(pattern, notation)
        
        if not match:
            return None
        
        num_dice = int(match.group(1)) if match.group(1) else 1
        sides = int(match.group(2))
        modifier = int(match.group(3)) if match.group(3) else 0
        
        if num_dice < 1 or num_dice > 1000:
            return None
        if sides < 2 or sides > 10000:
            return None
        if abs(modifier) > 1000:
            return None
        
        return num_dice, sides, modifier
    
    def _roll_dice(self, num_dice: int, sides: int) -> List[int]:
        """Rolls multiple dice"""
        return [random.randint(1, sides) for _ in range(num_dice)]
    
    def _format_roll_result(self, rolls: List[int], modifier: int = 0) -> str:
        """Formats roll results"""
        if len(rolls) == 1:
            total = rolls[0] + modifier
            if modifier == 0:
                return f"```{rolls[0]}```"
            elif modifier > 0:
                return f"```{rolls[0]} + {modifier} = {total}```"
            else:
                return f"```{rolls[0]} - {abs(modifier)} = {total}```"
        else:
            rolls_text = " + ".join([str(r) for r in rolls])
            total = sum(rolls) + modifier
            if modifier == 0:
                return f"```{rolls_text}\n\nTotal: {total}```"
            elif modifier > 0:
                return f"```{rolls_text} + {modifier}\n\nTotal: {total}```"
            else:
                return f"```{rolls_text} - {abs(modifier)}\n\nTotal: {total}```"
    
    async def _send_roll(self, message: discord.Message, notation: str):
        """Process and send dice roll"""
        result = self._parse_dice_notation(notation)
        
        if not result:
            return False
        
        num_dice, sides, modifier = result
        rolls = self._roll_dice(num_dice, sides)
        total = sum(rolls) + modifier
        
        max_roll = sides * num_dice
        min_roll = num_dice
        
        if total == max_roll + modifier:
            color = Colors.XP
        elif total == min_roll + modifier:
            color = Colors.WARNING
        else:
            color = Colors.PRIMARY
        
        notation_display = f"{num_dice}d{sides}"
        if modifier != 0:
            notation_display += f"{'+' if modifier > 0 else ''}{modifier}"
        
        embed = discord.Embed(title=notation_display, color=color)
        embed.add_field(
            name="Resultado",
            value=self._format_roll_result(rolls, modifier),
            inline=False
        )
        
        if num_dice > 1:
            avg = sum(rolls) / num_dice
            embed.add_field(name="Media", value=f"```{avg:.1f}```", inline=True)
            embed.add_field(name="Min/Max", value=f"```{min(rolls)}/{max(rolls)}```", inline=True)
        
        await message.reply(embed=embed, mention_author=False)
        return True
    
    def _check_cooldown(self, user_id: int) -> bool:
        """Check if user is on cooldown"""
        now = asyncio.get_event_loop().time()
        
        if user_id in user_cooldowns:
            if now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
                return False
        
        user_cooldowns[user_id] = now
        return True
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for dice notation in messages"""
        if message.author.bot:
            return
        
        content = message.content.strip()
        
        # Check if message is just dice notation
        if self._parse_dice_notation(content):
            if not self._check_cooldown(message.author.id):
                embed = discord.Embed(
                    title="Calma ai",
                    description="Aguarde 1.5s.",
                    color=Colors.USER_ERROR,
                )
                await message.reply(embed=embed, mention_author=False)
                return
            
            await self._send_roll(message, content)
    
    @commands.hybrid_command(name="init", aliases=["iniciativa"], description="Rolar iniciativa")
    @commands.cooldown(1, 1.5, commands.BucketType.user)
    async def init(self, ctx: commands.Context, bonus: int = 0):
        """Rola iniciativa (1d20 + bonus)"""
        if abs(bonus) > 50:
            embed = discord.Embed(
                title="Bonus invalido",
                description="Use valor entre -50 e +50",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        roll = random.randint(1, 20)
        total = roll + bonus
        
        if roll == 20:
            color = Colors.XP
            quality = "Critico!"
        elif roll == 1:
            color = Colors.WARNING
            quality = "Falha!"
        else:
            color = Colors.PRIMARY
            quality = ""
        
        embed = discord.Embed(title="Iniciativa", color=color)
        
        if bonus != 0:
            embed.add_field(
                name="Rolagem",
                value=f"```1d20: {roll}\nBonus: {'+' if bonus > 0 else ''}{bonus}\n\nTotal: {total}```",
                inline=False
            )
        else:
            embed.add_field(name="Resultado", value=f"```{total}```", inline=False)
        
        if quality:
            embed.add_field(name="Status", value=quality, inline=False)
        
        embed.set_footer(text=f"{ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
    
    @init.error
    async def init_error(self, ctx: commands.Context, error: Exception):
        """Handles initiative command errors"""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=embed_cooldown(error.retry_after), ephemeral=True)
        else:
            logger.error(f"Initiative command error: {error}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Dice(bot))
