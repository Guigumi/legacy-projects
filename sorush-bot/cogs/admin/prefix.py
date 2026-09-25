"""
Custom prefix management for servers
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

from config import Colors
from services.repositories import guild_repo
from services.event_bus import event_bus, BotEvent

logger = logging.getLogger(__name__)


def get_prefix(bot, message) -> list:
    """Gets the prefix for a server"""
    default = ["s!", "S!"]
    
    if message.guild:
        guild_prefix = guild_repo.get_prefix(message.guild.id)
        if guild_prefix and guild_prefix != "!":  # "!" is the default in schema
            return commands.when_mentioned_or(guild_prefix)(bot, message)
    
    return commands.when_mentioned_or(*default)(bot, message)


class Prefix(commands.Cog):
    """Command to manage server prefix"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.hybrid_command(name="prefix", aliases=["prefixo"], description="Alterar prefixo do bot")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def prefix_command(self, ctx: commands.Context, novo_prefixo: str = None):
        """
        Altera o prefixo do bot no servidor
        Uso: s!prefixo <novo_prefixo>
        """
        if not novo_prefixo:
            current = guild_repo.get_prefix(ctx.guild.id)
            if current == "!":  # Default in schema
                current = "s!"
            embed = discord.Embed(title="", description=" ", color=Colors.INFO)
            embed.add_field(name="─────〔 Prefixo 〕─────", value="", inline=False)
            embed.add_field(name="Agora é", value=f"```{current}```", inline=True)
            embed.add_field(name="", value="", inline=True)
            embed.add_field(name="Pra mudar", value="`s!prefix <novo>`", inline=True)
            await ctx.send(embed=embed)
            return
        
        if len(novo_prefixo) > 5:
            embed = discord.Embed(title="❌ ops", description="muito grande, max 5 letras", color=Colors.USER_ERROR)
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        if " " in novo_prefixo:
            embed = discord.Embed(title="❌ ops", description="sem espaços, por favor", color=Colors.USER_ERROR)
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        # Verificar caracteres inválidos
        invalid_chars = ['`', '@', '#', '<', '>']
        if any(char in novo_prefixo for char in invalid_chars):
            embed = discord.Embed(
                title="❌ ops",
                description="não pode usar esses caracteres: ` @ # < >",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        # Save to database via guild_repo
        if guild_repo.set_prefix(ctx.guild.id, novo_prefixo):
            embed = discord.Embed(title="", description=" ", color=Colors.SUCCESS)
            embed.add_field(name="─────〔 Prefixo Alterado 〕─────", value="", inline=False)
            embed.add_field(name="Novo prefixo", value=f"```{novo_prefixo}```", inline=True)
            embed.set_footer(text=f"quem mudou: {ctx.author.display_name}")
            await ctx.send(embed=embed)
            logger.info(f"Prefix changed to '{novo_prefixo}' for guild {ctx.guild.id}")
            await event_bus.emit(BotEvent.PREFIX_CHANGED, ctx.guild.id, {
                'new_prefix': novo_prefixo,
                'changed_by': ctx.author.id
            })
        else:
            embed = discord.Embed(title="❌ ops", description="erro ao salvar", color=Colors.ERROR)
            await ctx.send(embed=embed, ephemeral=True)
            logger.error(f"Failed to save prefix for guild {ctx.guild.id}")
    
    @commands.hybrid_command(name="resetprefix", description="Resetar prefixo para o padrão")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def reset_prefix(self, ctx: commands.Context):
        """Reseta o prefixo do servidor para o padrão (s!)"""
        if guild_repo.set_prefix(ctx.guild.id, "s!"):
            embed = discord.Embed(
                title="⚙️ prefixo",
                description="voltei pro padrão: `s!`",
                color=Colors.SUCCESS
            )
            logger.info(f"Prefix reset to default for guild {ctx.guild.id}")
        else:
            embed = discord.Embed(title="❌ ops", description="erro ao salvar", color=Colors.ERROR)
            logger.error(f"Failed to reset prefix for guild {ctx.guild.id}")
        
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Prefix(bot))
