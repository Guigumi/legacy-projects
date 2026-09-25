"""
Anonymous Card Command - Send anonymous letters to users via DM
The sender remains completely anonymous (except for reports to bot owner)
"""
import discord
import logging
from discord.ext import commands
from datetime import datetime

from config import OWNER_ID, Colors

logger = logging.getLogger(__name__)


class ReceivedCardView(discord.ui.View):
    """View for the received card with copy and report buttons"""
    
    def __init__(self, message_content: str, sender_id: int, recipient_id: int, bot: commands.Bot):
        super().__init__(timeout=None)  # Persistent view
        self.message_content = message_content
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.bot = bot
    
    @discord.ui.button(label="Copiar", emoji="📋", style=discord.ButtonStyle.secondary)
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Send the raw message content so user can copy"""
        await interaction.response.send_message(
            f"```\n{self.message_content}\n```",
            ephemeral=True
        )
    
    @discord.ui.button(label="Reportar", emoji="🚨", style=discord.ButtonStyle.danger)
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Report the card to bot owner with sender info"""
        try:
            owner = await self.bot.fetch_user(OWNER_ID)
        except discord.NotFound:
            return await interaction.response.send_message(
                "😕 não consegui achar o dono do bot",
                ephemeral=True
            )
        
        # Create report embed for owner (includes sender info)
        report_embed = discord.Embed(
            title="🚨 Report de Carta",
            color=Colors.ERROR,
            timestamp=datetime.now()
        )
        report_embed.add_field(
            name="▸ Enviado por",
            value=f"<@{self.sender_id}> (`{self.sender_id}`)",
            inline=True
        )
        report_embed.add_field(
            name="▸ Recebido por",
            value=f"<@{self.recipient_id}> (`{self.recipient_id}`)",
            inline=True
        )
        report_embed.add_field(
            name="▸ Mensagem",
            value=f"```{self.message_content[:1000]}```",
            inline=False
        )
        
        try:
            await owner.send(embed=report_embed)
            
            # Disable the report button after use
            button.disabled = True
            button.label = "Reportado"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "✅ Report enviado ao dono do bot. Obrigado!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "😕 não consegui enviar o report",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Erro ao enviar report: {e}")
            await interaction.response.send_message(
                "😕 algo deu errado ao reportar",
                ephemeral=True
            )


class MessageModal(discord.ui.Modal, title="✉️ Escreva sua carta anônima"):
    """Modal for writing the anonymous card message"""
    
    message = discord.ui.TextInput(
        label="Mensagem",
        placeholder="Escreva sua mensagem aqui... (será enviada anonimamente)",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1000,
        required=True
    )
    
    def __init__(self, recipient: discord.Member, bot: commands.Bot):
        super().__init__()
        self.recipient = recipient
        self.bot = bot
    
    async def on_submit(self, interaction: discord.Interaction):
        sender_id = interaction.user.id
        
        # Create anonymous card embed
        card_embed = discord.Embed(
            title="✉️ Carta Anônima",
            description=f"alguém te mandou uma mensagem:\n\n`{self.message.value}`",
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )
        card_embed.set_footer(text="use os botões pra copiar ou reportar")
        
        # Create view with buttons
        view = ReceivedCardView(
            message_content=self.message.value,
            sender_id=sender_id,
            recipient_id=self.recipient.id,
            bot=self.bot
        )
        
        # Try to send to recipient's DM
        try:
            await self.recipient.send(embed=card_embed, view=view)
            
            # Confirm to sender (ephemeral so no one sees)
            await interaction.response.send_message(
                "✅ carta enviada!",
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.response.send_message(
                f"😕 **{self.recipient.display_name}** tá com DMs fechadas",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Erro ao enviar carta: {e}")
            await interaction.response.send_message(
                "😕 algo deu errado ao enviar",
                ephemeral=True
            )
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal errors gracefully"""
        logger.error(f"Erro no modal de carta: {error}")
        try:
            await interaction.response.send_message(
                "😟 algo deu errado",
                ephemeral=True
            )
        except:
            pass


class SendCardButton(discord.ui.Button):
    """Button to open the message modal"""
    
    def __init__(self, recipient: discord.Member, author_id: int, bot: commands.Bot):
        super().__init__(
            label="Escrever Carta",
            emoji="✉️",
            style=discord.ButtonStyle.primary
        )
        self.recipient = recipient
        self.author_id = author_id
        self.bot = bot
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "❌ Apenas quem iniciou pode usar!",
                ephemeral=True
            )
        
        modal = MessageModal(self.recipient, self.bot)
        await interaction.response.send_modal(modal)


class CardView(discord.ui.View):
    """View with button to write card"""
    
    def __init__(self, recipient: discord.Member, author_id: int, bot: commands.Bot):
        super().__init__(timeout=120)
        self.add_item(SendCardButton(recipient, author_id, bot))
        self.message = None
    
    async def on_timeout(self):
        """Clean up on timeout"""
        if self.message:
            try:
                await self.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass


class Card(commands.Cog):
    """Send anonymous cards to other users"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="carta",
        aliases=["card", "anonimo", "anonymous"],
        description="Envie uma carta anônima para alguém"
    )
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def carta_command(self, ctx: commands.Context, member: discord.Member):
        """Send an anonymous card to someone's DM
        
        Parameters
        ----------
        member : discord.Member
            The person to send the anonymous card to
        """
        # Delete command message to preserve anonymity
        if ctx.message:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        # Validations
        if member.id == ctx.author.id:
            return await ctx.send(
                "❌ Você não pode enviar uma carta para si mesmo!",
                ephemeral=True
            )
        
        if member.bot:
            return await ctx.send(
                "❌ Você não pode enviar cartas para bots!",
                ephemeral=True
            )
        
        # If slash command, open modal directly
        if ctx.interaction:
            modal = MessageModal(member, self.bot)
            await ctx.interaction.response.send_modal(modal)
        else:
            # If prefix command, send button to open modal
            view = CardView(member, ctx.author.id, self.bot)
            msg = await ctx.send(
                f"✉️ Clique no botão para escrever sua carta anônima para **{member.display_name}**:",
                view=view
            )
            view.message = msg

    @carta_command.error
    async def carta_error(self, ctx: commands.Context, error: Exception):
        """Handle card command errors"""
        # Delete command message to preserve anonymity
        if ctx.message:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"⏳ Aguarde {error.retry_after:.0f}s para enviar outra carta!",
                ephemeral=True
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                "❌ Mencione alguém! Use: `/carta @usuario`",
                ephemeral=True
            )
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(
                "❌ Membro não encontrado!",
                ephemeral=True
            )
        else:
            await ctx.send(
                "❌ Use como slash command: `/carta @usuario`",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Card(bot))
