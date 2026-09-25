"""
Automatic role assignment on member join
Uses guild_repo (SQLite) instead of JSON files.
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Literal

from services.repositories import guild_repo
from services.event_bus import event_bus, BotEvent
from services.embed_helpers import embed_success, embed_error, embed_info, embed_warning

logger = logging.getLogger(__name__)


class AutoRole(commands.Cog):
    """Automatic role assignment on member join"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.hybrid_command(name="autorole", description="Configurar cargo automático ao entrar")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    @app_commands.describe(
        role="Cargo para dar automaticamente",
        action="on para ativar, off para desativar"
    )
    async def autorole_command(self, ctx: commands.Context, role: discord.Role = None, action: Literal["on", "off"] = None):
        """
        Configura cargo automático para novos membros
        Uso: s!autorole @cargo on|off
        """
        config = guild_repo.get_autorole(ctx.guild.id)
        
        if role is None:
            if config["enabled"] and config["role_id"]:
                guild_role = ctx.guild.get_role(config["role_id"])
                role_name = guild_role.mention if guild_role else f"ID: {config['role_id']} (não encontrado)"
                embed = embed_success(f"**cargo:** {role_name}\n**status:** ✅ ligado", title="⚙️ autorole tá on")
            else:
                embed = embed_info(
                    "autorole tá desligado.\n\n"
                    "**como usa:** `s!autorole @cargo on`\n"
                    "**desativar:** `s!autorole @cargo off`",
                    title="⚙️ autorole"
                )
            await ctx.send(embed=embed)
            return
        
        if action is None:
            embed = embed_error(
                "tem que falar se é `on` ou `off`!\n\n"
                "**exemplo:** `s!autorole @cargo on`"
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        if role >= ctx.guild.me.top_role:
            embed = embed_error("não posso dar um cargo igual ou maior que o meu!")
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        if role.managed:
            embed = embed_error("esse cargo é gerenciado por uma integração (bot/booster), não posso usar!")
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        if action == "on":
            if guild_repo.set_autorole(ctx.guild.id, role.id, enabled=True):
                embed = embed_success(
                    f"Novos membros receberão o cargo {role.mention} automaticamente!",
                    title="✅ AutoRole Ativado",
                    footer=f"Configurado por {ctx.author.display_name}"
                )
                await event_bus.emit(BotEvent.CONFIG_CHANGED, guild_id=ctx.guild.id, data={"setting": "autorole", "value": role.id})
            else:
                embed = embed_error("Erro ao salvar configuração!")
        else:
            guild_repo.disable_autorole(ctx.guild.id)
            embed = embed_warning("Novos membros não receberão mais cargo automático.", title="🔴 AutoRole Desativado")
            await event_bus.emit(BotEvent.CONFIG_CHANGED, guild_id=ctx.guild.id, data={"setting": "autorole", "value": None})
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Assigns role when a new member joins"""
        if member.bot:
            return
        
        config = guild_repo.get_autorole(member.guild.id)
        
        if not config["enabled"] or not config["role_id"]:
            return
        
        role = member.guild.get_role(config["role_id"])
        if role is None:
            return
        
        try:
            await member.add_roles(role, reason="AutoRole: Cargo automático ao entrar")
        except discord.Forbidden:
            logger.debug(f"AutoRole: sem permissão para {member.guild.name}")
        except discord.HTTPException as e:
            logger.debug(f"AutoRole falhou para {member}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
