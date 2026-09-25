import discord
from discord.ext import commands
from datetime import datetime
from typing import Dict, Any, Optional
import asyncio
import logging

from services.repositories import stats_repo
from services.embed_helpers import format_time, format_number, embed_cooldown, embed_internal_error
from config import Colors

logger = logging.getLogger(__name__)


CACHE_TIMEOUT = 300

class ServerInfo(commands.Cog):
    """Cog for server information with database statistics"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache: Dict[int, Dict[str, Any]] = {}

    def _format_number(self, num: int) -> str:
        """Formats number with separators"""
        return f"{num:,}" if isinstance(num, int) else "0"

    def _get_cached(self, guild_id: int, key: str) -> Optional[Any]:
        """Gets cached data if valid"""
        if guild_id not in self.cache:
            return None
        timestamp, data = self.cache[guild_id].get(key, (0, None))
        if datetime.now().timestamp() - timestamp < CACHE_TIMEOUT:
            return data
        return None

    def _set_cached(self, guild_id: int, key: str, data: Any) -> None:
        """Stores data in cache"""
        if guild_id not in self.cache:
            self.cache[guild_id] = {}
        self.cache[guild_id][key] = (datetime.now().timestamp(), data)

    def _collect_data(self, guild: discord.Guild) -> Dict[str, Any]:
        """Collects server data including database stats"""
        guild_id = guild.id

        members = self._get_cached(guild_id, 'members')
        if not members:
            members = {
                'total': guild.member_count or len(guild.members),
                'humans': len([m for m in guild.members if not m.bot]),
                'bots': len([m for m in guild.members if m.bot])
            }
            self._set_cached(guild_id, 'members', members)

        channels = self._get_cached(guild_id, 'channels')
        if not channels:
            channels = {
                'text': len(guild.text_channels),
                'voice': len(guild.voice_channels),
                'categories': len(guild.categories),
                'forums': len([c for c in guild.channels if isinstance(c, discord.ForumChannel)])
            }
            self._set_cached(guild_id, 'channels', channels)

        # Get database statistics
        db_stats = self._get_cached(guild_id, 'db_stats')
        if not db_stats:
            try:
                db_stats = stats_repo.get_extended_guild_stats(guild_id)
                self._set_cached(guild_id, 'db_stats', db_stats)
            except Exception as e:
                logger.error(f"Error getting DB stats for guild {guild_id}: {e}")
                db_stats = {}

        return {'members': members, 'channels': channels, 'db_stats': db_stats}

    def _build_embed(self, guild: discord.Guild, data: Dict[str, Any], author: discord.Member) -> discord.Embed:
        """Builds embed with server information"""
        members = data['members']
        channels = data['channels']

        created_timestamp = int(guild.created_at.timestamp())
        
        embed = discord.Embed(
            title="",
            description=" ",
            color=Colors.INFO
        )
        
        # Author with server name and icon
        if guild.icon:
            embed.set_author(name=guild.name, icon_url=guild.icon.url)
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="─────〔 Servidor 〕─────", value="", inline=False)
        
        # Essential info only (inline)
        embed.add_field(name="Pessoas", value=f"```{members['total']}```", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="Canais", value=f"```{channels['text'] + channels['voice']}```", inline=True)
        
        embed.add_field(name="─────〔 Informações 〕─────", value="", inline=False)
        
        embed.add_field(name="Criado em", value=f"<t:{created_timestamp}:D>", inline=True)
        
        if guild.owner:
            embed.add_field(name="", value="", inline=True)
            embed.add_field(name="Dono", value=guild.owner.mention, inline=True)
        
        return embed

    @commands.hybrid_command(name="server", aliases=["serverinfo"], description="Informações do servidor")
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def server(self, ctx: commands.Context):
        """Displays server information"""
        if not ctx.guild:
            return await ctx.send("❌ Este comando só pode ser usado em servidores!")

        try:
            async with asyncio.timeout(5):
                data = self._collect_data(ctx.guild)
                embed = self._build_embed(ctx.guild, data, ctx.author)
                await ctx.reply(embed=embed, mention_author=False)

        except asyncio.TimeoutError:
            logger.warning(f"Timeout collecting server info for guild {ctx.guild.id}")
            await ctx.send("⏳ Tempo limite excedido!", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Sem permissão para ver informações do servidor!", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in server command for guild {ctx.guild.id}: {e}")
            await ctx.send(f"❌ Erro: {str(e)[:100]}", ephemeral=True)

    @server.error
    async def server_error(self, ctx: commands.Context, error: Exception):
        """Handles command errors"""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Aguarde {error.retry_after:.1f}s", ephemeral=True)
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ Este comando só funciona em servidores!", ephemeral=True)
        else:
            logger.error(f"Unhandled error in server command: {error}")
            await ctx.send(f"❌ Erro: {str(error)[:100]}", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerInfo(bot))