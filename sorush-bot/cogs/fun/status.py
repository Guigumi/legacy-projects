"""
User Statistics Command
Mostra estatísticas detalhadas em um menu interativo sem excesso de informação.
"""
import logging
from typing import Optional

import discord
from discord.ext import commands
from discord.ui import Select, View

from services.repositories import user_repo
from services.embed_helpers import (
    format_time, format_number, stat_value,
    section_header, embed_error, embed_cooldown, embed_internal_error,
    BULLET
)
from config import Colors

logger = logging.getLogger(__name__)


CATEGORY_COLORS = {
    "overview": Colors.XP,
    "user_info": Colors.PRIMARY,
    "chat": Colors.PRIMARY,
    "voice": Colors.SUCCESS
}


# Aliases for backward compat
_stat_value = stat_value


class StatsSelect(Select):
    """Menu de seleção de categorias"""

    def __init__(self, member: discord.Member, user_data: dict, guild_id: int):
        self.member = member
        self.user_data = user_data
        self.guild_id = guild_id

        options = [
            discord.SelectOption(
                label="Visão Geral",
                description="Resumo de todas as estatísticas",
                emoji="📊",
                value="overview",
                default=True
            ),
            discord.SelectOption(
                label="Usuário",
                description="Informações do Discord",
                emoji="👤",
                value="user_info"
            ),
            discord.SelectOption(
                label="Chat",
                description="Mensagens, caracteres, palavras",
                emoji="💬",
                value="chat"
            ),
            discord.SelectOption(
                label="Voz",
                description="Tempo em chamadas",
                emoji="🎤",
                value="voice"
            )
        ]

        super().__init__(
            placeholder="📂 Selecione uma categoria...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            category = self.values[0]
            embed = self._get_embed_for_category(category)
            await interaction.response.defer()
            await interaction.edit_original_response(embed=embed)
        except Exception as e:
            logger.error(f"Erro no callback de stats: {e}", exc_info=True)
            await interaction.response.defer()

    def _get_embed_for_category(self, category: str) -> discord.Embed:
        """Retorna o embed para a categoria selecionada"""
        embed_methods = {
            "overview": self._create_overview_embed,
            "user_info": self._create_user_info_embed,
            "chat": self._create_chat_embed,
            "voice": self._create_voice_embed
        }
        method = embed_methods.get(category, self._create_overview_embed)
        return method()

    def _base_embed(self, title: str, color: int) -> discord.Embed:
        embed = discord.Embed(title=title, color=color, description=" ")
        if self.member.display_avatar:
            embed.set_author(name=self.member.display_name, icon_url=self.member.display_avatar.url)
        return embed

    def _create_overview_embed(self) -> discord.Embed:
        """Resumo geral"""
        embed = self._base_embed("", CATEGORY_COLORS["overview"])
        embed.add_field(name="─────〔 Status 〕─────", value="", inline=False)

        messages = self.user_data.get("messages", 0)
        voice_mins = self.user_data.get("voice_mins", 0)
        max_call = self.user_data.get("max_call_time", 0)
        max_chars = self.user_data.get("max_chars_msg", 0)

        if messages == 0 and voice_mins == 0:
            embed.add_field(
                name="Sem dados ainda",
                value="Envie mensagens ou entre em chamada para iniciar.",
                inline=False,
            )
            embed.set_footer(text="Use o menu para navegar")
            return embed

        embed.add_field(name="Tempo em chamada", value=f"{_stat_value(format_time(voice_mins))}", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="Mensagens enviadas", value=f"{_stat_value(format_number(messages))}", inline=True)

        embed.add_field(name="─────〔 Extras 〕─────", value="", inline=False)
        embed.add_field(
            name="Maior tempo em call",
            value=f"{_stat_value(format_time(max_call))}",
            inline=True,
        )
        embed.add_field(
            name="Maior mensagem",
            value=f"{_stat_value(format_number(max_chars))}",
            inline=True,
        )
        embed.set_footer(text="Use o menu para navegar")
        return embed

    def _create_user_info_embed(self) -> discord.Embed:
        """Info do Discord"""
        embed = self._base_embed("", CATEGORY_COLORS["user_info"])
        embed.add_field(name="─────〔 Usuário 〕─────", value="", inline=False)

        created = int(self.member.created_at.timestamp())
        embed.add_field(name="ID da conta", value=f"{_stat_value(str(self.member.id))}", inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="─────〔 Extras 〕─────", value="", inline=False)
        embed.add_field(name="Data de criação da conta", value=f"<t:{created}:R>", inline=False)

        embed.set_footer(text="Use o menu para explorar")
        return embed

    def _create_chat_embed(self) -> discord.Embed:
        """Estatísticas de chat"""
        embed = self._base_embed("", CATEGORY_COLORS["chat"])
        embed.add_field(name="─────〔 Chat 〕─────", value="", inline=False)

        messages = self.user_data.get("messages", 0)
        words_total = self.user_data.get("words_total", 0)
        emojis_used = self.user_data.get("emojis_used", 0)
        attachments = self.user_data.get("attachments_sent", 0)
        links = self.user_data.get("links_shared", 0)
        replies = self.user_data.get("replies_sent", 0)

        embed.add_field(name="Mensagens enviadas", value=_stat_value(format_number(messages)), inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="Palavras enviadas", value=_stat_value(format_number(words_total)), inline=True)

        # Conteúdo adicional
        content = []
        if emojis_used > 0:
            content.append(f"😊 {format_number(emojis_used)} emojis")
        if attachments > 0:
            content.append(f"📎 {format_number(attachments)} anexos")
        if links > 0:
            content.append(f"🔗 {format_number(links)} links")
        if replies > 0:
            content.append(f"↩️ {format_number(replies)} respostas")

        if content:
            embed.add_field(name="Conteúdo", value=" • ".join(content), inline=False)

        return embed

    def _create_voice_embed(self) -> discord.Embed:
        """Estatísticas de voz"""
        embed = self._base_embed("", CATEGORY_COLORS["voice"])
        embed.add_field(name="─────〔 Voz 〕─────", value="", inline=False)

        voice_mins = self.user_data.get("voice_mins", 0)
        voice_sessions = self.user_data.get("voice_sessions", 0)

        embed.add_field(name="Tempo em call", value=_stat_value(format_time(voice_mins)), inline=True)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="Sessões", value=_stat_value(format_number(voice_sessions)), inline=True)

        embed.add_field(name="─────〔 Extras 〕─────", value="", inline=False)
        if voice_sessions > 0:
            avg_duration = voice_mins // voice_sessions
            embed.add_field(name="Média por sessão", value=_stat_value(format_time(avg_duration)), inline=False)

        embed.set_footer(text="Tempo registrado em voz")
        return embed


class StatsView(View):
    """View com o menu de seleção"""

    def __init__(self, member: discord.Member, user_data: dict, guild_id: int, author_id: int):
        super().__init__(timeout=300)
        self.add_item(StatsSelect(member, user_data, guild_id))
        self.author_id = author_id
        self.member = member

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.defer()
            return False
        return True

    async def on_timeout(self):
        pass


class UserStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name='status',
        aliases=['stats', 'estatisticas', 'info'],
        description='📊 Mostra estatísticas detalhadas de um usuário'
    )
    @commands.guild_only()
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def user_status(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Mostra estatísticas completas do usuário com menu interativo"""
        if not ctx.guild:
            await ctx.send("⚠️ Este comando só pode ser usado em servidores!")
            return

        target = user or ctx.author

        try:
            # Buscar dados do usuário com fallbacks seguros
            user_data = user_repo.get_user_full_stats(ctx.guild.id, target.id)
            
            if not user_data:
                await ctx.send(embed=embed_error("Tente novamente em instantes.", title="Não foi possível agora"), ephemeral=True)
                return

            # Criar views e enviar
            view = StatsView(target, user_data, ctx.guild.id, ctx.author.id)
            embed = view.children[0]._create_overview_embed()
            
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Erro no comando user_status: {e}", exc_info=True)
            await ctx.send(embed=embed_internal_error(), ephemeral=True)

    @user_status.error
    async def user_status_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=embed_cooldown(error.retry_after), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UserStats(bot))
