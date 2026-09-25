import discord
from discord.ext import commands
import logging

from config import Colors

logger = logging.getLogger(__name__)


class Roles(commands.Cog):
    """Cog to list server roles"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="cargos", aliases=["roles"], description="Lista todos os cargos do servidor")
    @commands.guild_only()
    async def roles(self, ctx: commands.Context):
        """Lists all server roles in order"""
        try:
            role_list = sorted(ctx.guild.roles, key=lambda r: r.position, reverse=True)
            
            if not role_list or len(role_list) == 1:
                embed = discord.Embed(title="🏅 Roles", description="nenhum cargo encontrado", color=Colors.WARNING)
                return await ctx.send(embed=embed, ephemeral=True)
            
            embed = discord.Embed(
                title="🏅 Roles",
                color=Colors.PRIMARY
            )
            embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            embed.add_field(name="Total", value=f"```{len(role_list) - 1}```", inline=True)
            
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)
            
            # List roles with character limit
            roles_text = ""
            field_count = 0
            
            for role in role_list:
                if role.name == "@everyone":
                    continue
                
                members = len(role.members)
                role_entry = f"{role.mention} • {members} membro{'s' if members != 1 else ''}\n"
                
                # If adding this line exceeds the limit, create new field
                if len(roles_text) + len(role_entry) > 1020:
                    if roles_text:
                        embed.add_field(
                            name="Cargos" if field_count == 0 else "​",
                            value=roles_text.strip(),
                            inline=False
                        )
                    roles_text = role_entry
                    field_count += 1
                else:
                    roles_text += role_entry
            
            # Add last field
            if roles_text:
                embed.add_field(
                    name="Cargos" if field_count == 0 else "​",
                    value=roles_text.strip(),
                    inline=False
                )
            
            embed.set_footer(text=f"Solicitado por {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            
            await ctx.send(embed=embed)
        
        except Exception as e:
            logger.error(f"Error in roles command for guild {ctx.guild.id}: {e}")
            embed = discord.Embed(
                title="Nao foi possivel agora",
                description="Tente novamente em instantes.",
                color=Colors.ERROR,
            )
            await ctx.send(embed=embed, ephemeral=True)

    @roles.error
    async def roles_error(self, ctx: commands.Context, error: Exception):
        """Handles command errors"""
        if isinstance(error, commands.NoPrivateMessage):
            embed = discord.Embed(
                title="Nao posso aqui",
                description="Este comando so funciona em servidores.",
                color=Colors.USER_ERROR,
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            logger.error(f"Unhandled error in roles command: {error}")
            embed = discord.Embed(
                title="Nao foi possivel agora",
                description="Tente novamente em instantes.",
                color=Colors.ERROR,
            )
            await ctx.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
