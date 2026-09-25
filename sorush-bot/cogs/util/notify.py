"""
Keyword notification system
Uses notification_repo (SQLite) instead of JSON files.
"""
import discord
from discord.ext import commands
import logging

from services.repositories import notification_repo, guild_repo
from services.embed_helpers import embed_success, embed_error, embed_info, embed_warning

logger = logging.getLogger(__name__)

MAX_KEYWORDS = 10


class Notify(commands.Cog):
    """Keyword notification system"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # In-memory cache per guild (rebuilt on first message)
        self._cache: dict[int, dict[int, list[str]]] = {}
    
    def _invalidate_cache(self, guild_id: int):
        self._cache.pop(guild_id, None)
    
    def _get_guild_keywords(self, guild_id: int) -> dict[int, list[str]]:
        if guild_id not in self._cache:
            self._cache[guild_id] = notification_repo.get_all_guild_keywords(guild_id)
        return self._cache[guild_id]
    
    @commands.hybrid_group(name="notify", description="Sistema de notificações por palavra-chave")
    async def notify_group(self, ctx: commands.Context):
        """Notification command group"""
        if ctx.invoked_subcommand is None:
            keywords = notification_repo.get_keywords(ctx.guild.id, ctx.author.id)
            
            if keywords:
                keywords_list = ", ".join([f"`{kw}`" for kw in keywords])
                embed = embed_info(f"```{keywords_list}```", title="🔔 notificações")
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            else:
                embed = embed_info(
                    "não tem nada configurado\nusa `notify add <palavra>` pra adicionar",
                    title="🔔 notificações"
                )
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed, ephemeral=True)
    
    @notify_group.command(name="add", description="Adicionar palavra-chave")
    @commands.guild_only()
    async def notify_add(self, ctx: commands.Context, *, keyword: str):
        """Adiciona uma palavra-chave para notificação"""
        keyword = keyword.lower().strip()
        
        if len(keyword) < 2:
            return await ctx.send(embed=embed_error("muito curto, min 2 letras"), ephemeral=True)
        
        if len(keyword) > 50:
            return await ctx.send(embed=embed_error("muito longo, max 50 letras"), ephemeral=True)
        
        count = notification_repo.keyword_count(ctx.guild.id, ctx.author.id)
        if count >= MAX_KEYWORDS:
            return await ctx.send(embed=embed_error(f"já tem {MAX_KEYWORDS} palavras, remove alguma primeiro"), ephemeral=True)
        
        success = notification_repo.add_keyword(ctx.guild.id, ctx.author.id, keyword)
        if not success:
            return await ctx.send(embed=embed_error(f"`{keyword}` já tá na lista"), ephemeral=True)
        
        self._invalidate_cache(ctx.guild.id)
        embed = embed_success("", title="✅ adicionado")
        embed.add_field(name="Keyword", value=f"```{keyword}```", inline=True)
        await ctx.send(embed=embed, ephemeral=True)
    
    @notify_group.command(name="remove", description="Remover palavra-chave")
    @commands.guild_only()
    async def notify_remove(self, ctx: commands.Context, *, keyword: str):
        """Remove uma palavra-chave das notificações"""
        keyword = keyword.lower().strip()
        
        success = notification_repo.remove_keyword(ctx.guild.id, ctx.author.id, keyword)
        if not success:
            return await ctx.send(embed=embed_error(f"`{keyword}` não tá na sua lista"), ephemeral=True)
        
        self._invalidate_cache(ctx.guild.id)
        embed = embed_success("", title="✅ removido")
        embed.add_field(name="Keyword", value=f"```{keyword}```", inline=True)
        await ctx.send(embed=embed, ephemeral=True)
    
    @notify_group.command(name="clear", description="Limpar todas as palavras-chave")
    @commands.guild_only()
    async def notify_clear(self, ctx: commands.Context):
        """Remove todas as palavras-chave"""
        removed = notification_repo.clear_keywords(ctx.guild.id, ctx.author.id)
        self._invalidate_cache(ctx.guild.id)
        
        embed = embed_success(f"todas as keywords removidas ({removed})", title="🗑️ limpo")
        await ctx.send(embed=embed, ephemeral=True)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Checks messages for keywords"""
        if message.author.bot or not message.guild:
            return
        
        # Feature toggle check
        if not guild_repo.is_feature_enabled(message.guild.id, "notifications"):
            return
        
        content_lower = message.content.lower()
        if not content_lower:
            return
        
        guild_id = message.guild.id
        all_keywords = self._get_guild_keywords(guild_id)
        
        for user_id, keywords in all_keywords.items():
            if user_id == message.author.id:
                continue
            
            member = message.guild.get_member(user_id)
            if not member:
                continue
            
            if not message.channel.permissions_for(member).read_messages:
                continue
            
            for keyword in keywords:
                if keyword in content_lower:
                    try:
                        embed = discord.Embed(
                            title="🔔 Keyword Alert",
                            color=0xFFFACE,
                            url=message.jump_url
                        )
                        embed.set_author(
                            name=message.guild.name,
                            icon_url=message.guild.icon.url if message.guild.icon else None
                        )
                        embed.add_field(name="Keyword", value=f"```{keyword}```", inline=True)
                        embed.add_field(name="Canal", value=message.channel.mention, inline=True)
                        embed.add_field(name="Autor", value=message.author.mention, inline=True)
                        embed.add_field(name="Mensagem", value=f"```{message.content[:200]}```", inline=False)
                        await member.send(embed=embed)
                    except discord.Forbidden:
                        logger.debug(f"Cannot send notification to user {user_id} (DMs closed)")
                    except Exception as e:
                        logger.error(f"Error sending notification to user {user_id}: {e}")
                    break


async def setup(bot: commands.Bot):
    await bot.add_cog(Notify(bot))
