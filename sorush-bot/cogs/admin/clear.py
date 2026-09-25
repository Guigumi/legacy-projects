"""
Clear/Purge command system with safety measures
"""
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import asyncio
import logging

from config import Colors
from services.event_bus import event_bus, BotEvent

logger = logging.getLogger(__name__)


# Limits
MAX_MESSAGES = 100  # Maximum messages per clear
MIN_MESSAGES = 1    # Minimum messages to clear
COOLDOWN_SECONDS = 10  # Cooldown between uses


class ConfirmClearView(discord.ui.View):
    """View with confirmation buttons for clearing messages"""
    
    def __init__(self, author: discord.Member, amount: int, target: Optional[discord.Member] = None):
        super().__init__(timeout=30)
        self.author = author
        self.amount = amount
        self.target = target
        self.confirmed = False
        self.message: Optional[discord.Message] = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the command author can use the buttons"""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ apenas quem usou o comando pode confirmar",
                ephemeral=True
            )
            return False
        return True
    
    async def on_timeout(self) -> None:
        """Called when view times out"""
        for child in self.children:
            child.disabled = True
        
        if self.message:
            try:
                embed = discord.Embed(
                    description="⏳ tempo esgotado, operação cancelada",
                    color=Colors.WARNING
                )
                await self.message.edit(embed=embed, view=self)
            except discord.NotFound:
                pass
    
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm the clear operation"""
        self.confirmed = True
        self.stop()
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        embed = discord.Embed(
            description="🗑️ limpando mensagens...",
            color=Colors.PRIMARY
        )
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the clear operation"""
        self.confirmed = False
        self.stop()
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        embed = discord.Embed(
            description="❌ operação cancelada",
            color=Colors.WARNING
        )
        await interaction.response.edit_message(embed=embed, view=self)


class Clear(commands.Cog):
    """Message clearing commands with safety measures"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _create_clear_embed(self, amount: int, target: Optional[discord.Member] = None) -> discord.Embed:
        """Creates the confirmation embed"""
        if target:
            description = f"🗑️ apagar **{amount}** mensagens de {target.mention}?"
        else:
            description = f"🗑️ apagar **{amount}** mensagens?"
        
        embed = discord.Embed(
            description=description,
            color=Colors.WARNING
        )
        embed.set_footer(text="⚠️ essa ação não pode ser desfeita")
        return embed
    
    def _create_success_embed(self, deleted: int, target: Optional[discord.Member] = None) -> discord.Embed:
        """Creates the success embed"""
        if target:
            description = f"✅ **{deleted}** mensagens de {target.mention} foram apagadas"
        else:
            description = f"✅ **{deleted}** mensagens foram apagadas"
        
        return discord.Embed(
            description=description,
            color=Colors.SUCCESS
        )
    
    # ======================== SLASH COMMAND ========================
    
    @app_commands.command(name="limpar", description="Limpa mensagens do canal")
    @app_commands.describe(
        quantidade="Número de mensagens para apagar (1-100)",
        usuario="Apagar apenas mensagens de um usuário específico"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    @app_commands.checks.cooldown(1, COOLDOWN_SECONDS)
    async def clear_slash(
        self,
        interaction: discord.Interaction,
        quantidade: app_commands.Range[int, MIN_MESSAGES, MAX_MESSAGES],
        usuario: Optional[discord.Member] = None
    ):
        """Clear messages from the channel"""
        # Create confirmation view
        view = ConfirmClearView(interaction.user, quantidade, usuario)
        embed = self._create_clear_embed(quantidade, usuario)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()
        
        # Wait for confirmation
        await view.wait()
        
        if not view.confirmed:
            return
        
        # Perform the clear
        try:
            if usuario:
                # Clear messages from specific user
                def check(msg):
                    return msg.author.id == usuario.id
                
                deleted = await interaction.channel.purge(limit=quantidade, check=check)
            else:
                # Clear all messages
                deleted = await interaction.channel.purge(limit=quantidade)
            
            # Send success message
            success_embed = self._create_success_embed(len(deleted), usuario)
            await view.message.edit(embed=success_embed, view=None)
            
            # Emit event
            await event_bus.emit(BotEvent.MESSAGES_CLEARED, interaction.guild.id, {
                'moderator_id': interaction.user.id,
                'count': len(deleted),
                'target_user_id': usuario.id if usuario else None,
                'channel_id': interaction.channel.id
            })
            
        except discord.Forbidden:
            error_embed = discord.Embed(
                description="❌ não tenho permissão para apagar mensagens",
                color=Colors.USER_ERROR
            )
            await view.message.edit(embed=error_embed, view=None)
        
        except discord.HTTPException as e:
            if "14 days" in str(e) or "older than" in str(e).lower():
                error_embed = discord.Embed(
                    description="❌ não posso apagar mensagens com mais de 14 dias",
                    color=Colors.USER_ERROR
                )
            else:
                error_embed = discord.Embed(
                    description=f"❌ erro ao apagar mensagens: {e}",
                    color=Colors.ERROR
                )
            await view.message.edit(embed=error_embed, view=None)
    
    # ======================== PREFIX COMMAND ========================
    
    @commands.command(name="limpar", aliases=["clear", "purge", "prune"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    @commands.cooldown(1, COOLDOWN_SECONDS, commands.BucketType.channel)
    @commands.guild_only()
    async def clear_prefix(
        self,
        ctx: commands.Context,
        quantidade: int,
        usuario: Optional[discord.Member] = None
    ):
        """
        Limpa mensagens do canal
        
        Uso: s!clear <quantidade> [@usuario]
        Exemplo: s!clear 10
        Exemplo: s!clear 50 @usuario
        """
        # Validate amount
        if quantidade < MIN_MESSAGES:
            embed = discord.Embed(
                description=f"❌ a quantidade mínima é **{MIN_MESSAGES}**",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
            return
        
        if quantidade > MAX_MESSAGES:
            embed = discord.Embed(
                description=f"❌ a quantidade máxima é **{MAX_MESSAGES}**",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
            return
        
        # Delete the command message
        try:
            await ctx.message.delete()
        except discord.NotFound:
            pass
        
        # Create confirmation view
        view = ConfirmClearView(ctx.author, quantidade, usuario)
        embed = self._create_clear_embed(quantidade, usuario)
        
        confirm_msg = await ctx.send(embed=embed, view=view)
        view.message = confirm_msg
        
        # Wait for confirmation
        await view.wait()
        
        if not view.confirmed:
            return
        
        # Perform the clear
        try:
            # Delete the confirmation message first
            try:
                await confirm_msg.delete()
            except discord.NotFound:
                pass
            
            if usuario:
                # Clear messages from specific user
                def check(msg):
                    return msg.author.id == usuario.id
                
                deleted = await ctx.channel.purge(limit=quantidade, check=check)
            else:
                # Clear all messages
                deleted = await ctx.channel.purge(limit=quantidade)
            
            # Send temporary success message
            success_embed = self._create_success_embed(len(deleted), usuario)
            await ctx.send(embed=success_embed, delete_after=5)
            
            # Emit event
            await event_bus.emit(BotEvent.MESSAGES_CLEARED, ctx.guild.id, {
                'moderator_id': ctx.author.id,
                'count': len(deleted),
                'target_user_id': usuario.id if usuario else None,
                'channel_id': ctx.channel.id
            })
            
        except discord.Forbidden:
            error_embed = discord.Embed(
                description="❌ não tenho permissão para apagar mensagens",
                color=Colors.ERROR
            )
            await ctx.send(embed=error_embed, delete_after=10)
        
        except discord.HTTPException as e:
            if "14 days" in str(e) or "older than" in str(e).lower():
                error_embed = discord.Embed(
                    description="❌ não posso apagar mensagens com mais de 14 dias",
                    color=Colors.USER_ERROR
                )
            else:
                error_embed = discord.Embed(
                    description=f"❌ erro ao apagar mensagens: {e}",
                    color=Colors.ERROR
                )
            await ctx.send(embed=error_embed, delete_after=10)
    
    # ======================== ERROR HANDLERS ========================
    
    @clear_slash.error
    async def clear_slash_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Error handler for slash command"""
        if isinstance(error, app_commands.CommandOnCooldown):
            embed = discord.Embed(
                description=f"⏳ espera **{error.retry_after:.1f}s** para usar novamente",
                color=Colors.USER_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                description="🔒 você precisa da permissão `Gerenciar Mensagens`",
                color=Colors.USER_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif isinstance(error, app_commands.BotMissingPermissions):
            embed = discord.Embed(
                description="🔒 eu preciso da permissão `Gerenciar Mensagens` e `Ler Histórico`",
                color=Colors.ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @clear_prefix.error
    async def clear_prefix_error(self, ctx: commands.Context, error: commands.CommandError):
        """Error handler for prefix command"""
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                description="📝 uso: `s!clear <quantidade> [@usuario]`\n\nexemplo: `s!clear 10`",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, delete_after=15)
        
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                description="❌ digite um número válido de mensagens (1-100)",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
        
        elif isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                description=f"⏳ espera **{error.retry_after:.1f}s** para usar novamente",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
        
        elif isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description="🔒 você precisa da permissão `Gerenciar Mensagens`",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, delete_after=10)
        
        elif isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                description="🔒 eu preciso da permissão `Gerenciar Mensagens` e `Ler Histórico`",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, delete_after=10)


async def setup(bot: commands.Bot):
    await bot.add_cog(Clear(bot))
