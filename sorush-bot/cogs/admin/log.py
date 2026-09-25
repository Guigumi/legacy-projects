"""
Complete server logging system – all config in SQLite via guild_repo
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional, Literal
import logging

from services.repositories import guild_repo
from services.embed_helpers import embed_success, embed_error, embed_info, embed_warning
from services.event_bus import event_bus, BotEvent
from config import Colors

logger = logging.getLogger(__name__)


class LogColors:
    DELETE = 0xED4245
    EDIT = 0xFEE75C
    JOIN = 0x57F287
    LEAVE = 0xED4245
    BAN = 0xED4245
    VOICE = 0x5865F2


class Log(commands.Cog):
    """Complete server logging system"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _get_log_channel(self, guild_id: int) -> Optional[discord.TextChannel]:
        channel_id = guild_repo.get_log_channel(guild_id)
        if not channel_id:
            return None
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None
        return guild.get_channel(channel_id)
    
    def _is_event_enabled(self, guild_id: int, event: str) -> bool:
        return guild_repo.is_log_event_enabled(guild_id, event)
    
    # ======================== COMMANDS ========================
    
    @commands.hybrid_command(name="logs", description="Configurar canal de logs")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    @app_commands.describe(channel="Canal para enviar os logs")
    async def log_command(self, ctx: commands.Context, channel: discord.TextChannel):
        if guild_repo.set_log_channel(ctx.guild.id, channel.id, enabled=True):
            embed = embed_success(
                f"tá configurado no {channel.mention}",
                title="✅ logs on"
            )
            embed.add_field(
                name="Vou anotar:",
                value="• mensagens apagadas/editadas\n"
                      "• entradas/saídas de membros\n"
                      "• mudanças de perfil\n"
                      "• alterações de cargos\n"
                      "• banimentos/unbanimentos\n"
                      "• atividade em canais de voz",
                inline=False
            )
            embed.set_footer(text="usa /logconfig pra mexer no que eu anoto")
            await event_bus.emit(BotEvent.CONFIG_CHANGED, guild_id=ctx.guild.id, data={"setting": "log_channel", "value": channel.id})
            await ctx.send(embed=embed)
        else:
            await ctx.send(embed=embed_error("erro ao salvar"), ephemeral=True)

    @commands.hybrid_command(name="log", description="Configurar canal de logs (atalho)")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    @app_commands.describe(channel="Canal para enviar os logs")
    async def log_command_shortcut(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.log_command(ctx, channel)
    
    @commands.hybrid_command(name="nologs", aliases=["logdesativar"], description="Desativar logs")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def log_off(self, ctx: commands.Context):
        channel_id = guild_repo.get_log_channel(ctx.guild.id)
        if channel_id:
            guild_repo.set_log_channel(ctx.guild.id, channel_id, enabled=False)
        await ctx.send(embed=embed_warning("parei de anotar as coisas", title="🔴 logs off"))
    
    @commands.hybrid_command(name="logconfig", description="Ativar/desativar eventos específicos")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    @app_commands.describe(evento="Tipo de evento", estado="Ativar ou desativar")
    async def log_toggle(
        self, ctx: commands.Context,
        evento: Literal["messages", "members", "roles", "bans", "voice", "all"],
        estado: Literal["on", "off"]
    ):
        if not guild_repo.get_log_channel(ctx.guild.id):
            return await ctx.send(embed=embed_error("configura o canal primeiro com /logs"), ephemeral=True)
        
        enabled = estado == "on"
        
        if evento == "all":
            events = guild_repo.get_log_events(ctx.guild.id)
            for e in ["messages", "members", "roles", "bans", "voice"]:
                events[e] = enabled
            guild_repo.set_log_events(ctx.guild.id, events)
        else:
            guild_repo.set_log_event(ctx.guild.id, evento, enabled)
        
        status = "✅ ligado" if enabled else "🔴 desligado"
        embed = embed_success(f"**{evento.upper()}**: {status}", title="⚙️ log config") if enabled else embed_warning(f"**{evento.upper()}**: {status}", title="⚙️ log config")
        await ctx.send(embed=embed)
    
    # ======================== EVENT LISTENERS ========================
    
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not self._is_event_enabled(message.guild.id, "messages"):
            return
        channel = self._get_log_channel(message.guild.id)
        if not channel:
            return
        
        content = message.content[:512] if message.content else "*(sem conteúdo)*"
        embed = discord.Embed(
            description=f"**Autor:** {message.author.mention}\n**Canal:** {message.channel.mention}\n\n```\n{content}\n```",
            color=LogColors.DELETE, timestamp=datetime.now()
        )
        embed.set_author(name="🗑️ Mensagem Apagada", icon_url=message.author.display_avatar.url)
        if message.attachments:
            attachments = ", ".join([f"📎 {att.filename}" for att in message.attachments])
            embed.add_field(name="Anexos", value=attachments, inline=False)
        embed.set_thumbnail(url=message.author.display_avatar.replace(size=64).url)
        await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.content == after.content or not before.guild:
            return
        if not self._is_event_enabled(before.guild.id, "messages"):
            return
        channel = self._get_log_channel(before.guild.id)
        if not channel:
            return
        
        before_content = before.content[:300] if before.content else "*(sem conteúdo)*"
        after_content = after.content[:300] if after.content else "*(sem conteúdo)*"
        embed = discord.Embed(
            description=f"**Autor:** {before.author.mention}\n**Canal:** {before.channel.mention}\n\n**Antes:**\n```\n{before_content}\n```\n**Depois:**\n```\n{after_content}\n```\n[Ir para mensagem]({before.jump_url})",
            color=LogColors.EDIT, timestamp=datetime.now()
        )
        embed.set_author(name="✏️ Mensagem Editada", icon_url=before.author.display_avatar.url)
        embed.set_thumbnail(url=before.author.display_avatar.replace(size=64).url)
        await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        if not self._is_event_enabled(member.guild.id, "members"):
            return
        channel = self._get_log_channel(member.guild.id)
        if not channel:
            return
        
        account_age = datetime.now(member.created_at.tzinfo) - member.created_at
        days = account_age.days
        embed = discord.Embed(
            description=f"**Membro:** {member.mention}\n**ID:** `{member.id}`\n**Idade da Conta:** `{days} dias`\n**Total de Membros:** `{member.guild.member_count}`",
            color=LogColors.JOIN, timestamp=datetime.now()
        )
        embed.set_author(name="➕ Membro Entrou", icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.replace(size=64).url)
        await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        if not self._is_event_enabled(member.guild.id, "members"):
            return
        channel = self._get_log_channel(member.guild.id)
        if not channel:
            return
        
        joined_at = member.joined_at
        time_in_guild = datetime.now(joined_at.tzinfo) - joined_at
        days = time_in_guild.days
        roles_list = ", ".join([role.mention for role in member.roles[1:]][:10]) if member.roles[1:] else "Nenhum"
        
        was_kicked = False
        kicker = "Sistema"
        kick_reason = "Não especificado"
        try:
            async for entry in member.guild.audit_logs(action=discord.AuditLogAction.kick, limit=10):
                if entry.target.id == member.id and (datetime.now(entry.created_at.tzinfo) - entry.created_at).total_seconds() < 5:
                    was_kicked = True
                    kicker = entry.user.mention
                    if entry.reason:
                        kick_reason = entry.reason
                    break
        except Exception:
            pass
        
        if was_kicked:
            description = f"**Membro:** {member}\n**ID:** `{member.id}`\n**Tipo:** 🦵 Kickado\n**Responsável:** {kicker}\n**Motivo:** {kick_reason}\n**Tempo no Servidor:** `{days} dias`\n**Total de Membros:** `{member.guild.member_count}`\n**Cargos:** {roles_list}"
            title = "🦵 Membro Kickado"
            color = 0xFF7043
        else:
            description = f"**Membro:** {member}\n**ID:** `{member.id}`\n**Tipo:** 👋 Saída Normal\n**Tempo no Servidor:** `{days} dias`\n**Total de Membros:** `{member.guild.member_count}`\n**Cargos:** {roles_list}"
            title = "➖ Membro Saiu"
            color = LogColors.LEAVE
        
        embed = discord.Embed(description=description, color=color, timestamp=datetime.now())
        embed.set_author(name=title, icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.replace(size=64).url)
        await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if after.bot:
            return
        channel = None
        for guild in self.bot.guilds:
            if guild.get_member(after.id):
                log_channel = self._get_log_channel(guild.id)
                if log_channel:
                    channel = log_channel
                    break
        if not channel:
            return
        
        if before.name != after.name:
            embed = discord.Embed(
                description=f"**Usuário:** {after.mention}\n**Antes:** `{before.name}`\n**Depois:** `{after.name}`",
                color=Colors.INFO, timestamp=datetime.now()
            )
            embed.set_author(name="📝 Username Alterado", icon_url=after.display_avatar.url)
            embed.set_thumbnail(url=after.display_avatar.replace(size=64).url)
            await channel.send(embed=embed)
        elif before.avatar != after.avatar:
            embed = discord.Embed(
                description=f"**Usuário:** {after.mention}",
                color=Colors.INFO, timestamp=datetime.now()
            )
            embed.set_author(name="🖼️ Avatar Alterado", icon_url=after.display_avatar.url)
            embed.set_image(url=after.display_avatar.replace(size=64).url)
            await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return
        channel = self._get_log_channel(after.guild.id)
        if not channel:
            return
        
        if before.display_name != after.display_name:
            embed = discord.Embed(
                description=f"**Membro:** {after.mention}\n**Antes:** `{before.display_name}`\n**Depois:** `{after.display_name}`",
                color=Colors.INFO, timestamp=datetime.now()
            )
            embed.set_author(name="📝 Nome Alterado", icon_url=after.display_avatar.url)
            embed.set_thumbnail(url=after.display_avatar.replace(size=64).url)
            await channel.send(embed=embed)
        
        before_roles = set(before.roles)
        after_roles = set(after.roles)
        if before_roles != after_roles:
            added_roles = after_roles - before_roles
            removed_roles = before_roles - after_roles
            text = f"**Membro:** {after.mention}\n"
            if added_roles:
                roles_added = ", ".join([role.mention for role in added_roles if role.name != "@everyone"])
                if roles_added:
                    text += f"\n✅ **Adicionado:** {roles_added}"
            if removed_roles:
                roles_removed = ", ".join([role.mention for role in removed_roles if role.name != "@everyone"])
                if roles_removed:
                    text += f"\n❌ **Removido:** {roles_removed}"
            embed = discord.Embed(description=text, color=Colors.PRIMARY, timestamp=datetime.now())
            embed.set_author(name="🔄 Cargos Alterados", icon_url=after.display_avatar.url)
            embed.set_thumbnail(url=after.display_avatar.replace(size=64).url)
            await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if user.bot:
            return
        if not self._is_event_enabled(guild.id, "bans"):
            return
        channel = self._get_log_channel(guild.id)
        if not channel:
            return
        
        moderator = "Desconhecido"
        reason = "Sem motivo especificado"
        try:
            ban_entry = await guild.fetch_ban(user)
            if ban_entry.reason:
                reason = ban_entry.reason
        except Exception:
            pass
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=10):
                if entry.target.id == user.id:
                    moderator = f"{entry.user.mention}"
                    break
        except Exception:
            pass
        
        embed = discord.Embed(
            description=f"**Usuário:** {user}\n**ID:** `{user.id}`\n**Moderador:** {moderator}\n**Motivo:** {reason}",
            color=LogColors.BAN, timestamp=datetime.now()
        )
        embed.set_author(name="🔨 Membro Banido", icon_url=user.display_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.replace(size=64).url)
        await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if user.bot:
            return
        if not self._is_event_enabled(guild.id, "bans"):
            return
        channel = self._get_log_channel(guild.id)
        if not channel:
            return
        
        embed = discord.Embed(
            description=f"**Usuário:** {user}\n**ID:** `{user.id}`",
            color=Colors.SUCCESS, timestamp=datetime.now()
        )
        embed.set_author(name="✅ Membro Desbanido", icon_url=user.display_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.replace(size=64).url)
        await channel.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        if not self._is_event_enabled(member.guild.id, "voice"):
            return
        channel = self._get_log_channel(member.guild.id)
        if not channel:
            return
        
        if before.channel is None and after.channel is not None:
            embed = discord.Embed(
                description=f"**Membro:** {member.mention}\n**Canal:** {after.channel.mention}",
                color=LogColors.JOIN, timestamp=datetime.now()
            )
            embed.set_author(name="🎤 Entrou em Call", icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.replace(size=64).url)
            await channel.send(embed=embed)
        elif before.channel is not None and after.channel is None:
            embed = discord.Embed(
                description=f"**Membro:** {member.mention}\n**Canal:** {before.channel.mention}",
                color=LogColors.LEAVE, timestamp=datetime.now()
            )
            embed.set_author(name="🎤 Saiu da Call", icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.replace(size=64).url)
            await channel.send(embed=embed)
        elif before.channel != after.channel:
            embed = discord.Embed(
                description=f"**Membro:** {member.mention}\n**Saiu de:** {before.channel.mention}\n**Entrou em:** {after.channel.mention}",
                color=LogColors.VOICE, timestamp=datetime.now()
            )
            embed.set_author(name="🔄 Moveu de Call", icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.replace(size=64).url)
            await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Log(bot))
