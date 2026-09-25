"""
Bot Information
"""
import platform
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from config import BOT_VERSION, BOT_UPDATE_DATE, Colors
from services.repositories import stats_repo

logger = logging.getLogger(__name__)


class BotInfo(commands.Cog):
    """Cog to display bot information"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_uptime(self) -> str:
        """Calculates formatted uptime"""
        if not hasattr(self.bot, 'start_time') or not self.bot.start_time:
            return "N/A"
        
        now = datetime.now(timezone.utc)
        delta = now - self.bot.start_time
        
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        
        return " ".join(parts)

    def _get_command_count(self) -> int:
        """Counts non-hidden commands"""
        return sum(1 for cmd in self.bot.walk_commands() if not cmd.hidden)

    def _get_database_stats(self) -> dict:
        """Gets database statistics"""
        try:
            return stats_repo.get_global_user_stats()
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
        
        return {
            'total_users': 0,
            'total_messages': 0,
            'total_voice_mins': 0,
            'total_xp': 0
        }

    def _format_voice_time(self, minutes: int) -> str:
        """Formats minutes in readable format"""
        hours, mins = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:,}h {mins}m"
        return f"{mins}m"

    def _create_embed(self) -> discord.Embed:
        """Creates embed with bot information"""
        embed = discord.Embed(
            title="",
            description=" ",
            color=Colors.PRIMARY,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Author with bot avatar
        if self.bot.user.avatar:
            embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar.url)
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        # Discord statistics (inline)
        guild_count = len(self.bot.guilds)
        user_count = sum(g.member_count or 0 for g in self.bot.guilds)
        
        embed.add_field(name="─────〔 Informações 〕─────", value="", inline=False)
        
        embed.add_field(
            name="Versão",
            value=f"```{BOT_VERSION}```",
            inline=True
        )
        embed.add_field(
            name="Latência",
            value=f"```{self.bot.latency * 1000:.0f}ms```",
            inline=True
        )
        embed.add_field(
            name="Uptime",
            value=f"```{self._get_uptime()}```",
            inline=True
        )
        
        embed.add_field(name="─────〔 Estatísticas 〕─────", value="", inline=False)
        
        embed.add_field(
            name="Servidores",
            value=f"```{guild_count:,}```",
            inline=True
        )
        embed.add_field(
            name="Usuários",
            value=f"```{user_count:,}```",
            inline=True
        )
        embed.add_field(
            name="Update",
            value=f"```{BOT_UPDATE_DATE}```",
            inline=True
        )
        
        embed.set_footer(text=f"Sorush Bot v{BOT_VERSION}")
        
        return embed

    @commands.hybrid_command(
        name="bot",
        aliases=["botinfo"],
        description="Mostra informações sobre o bot"
    )
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def botinfo(self, ctx: commands.Context):
        """Displays detailed bot information"""
        embed = self._create_embed()
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BotInfo(bot))
