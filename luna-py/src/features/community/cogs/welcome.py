"""
Cog de boas-vindas (Welcome).
Painel interativo para administradores configurarem mensagens e embeds de entrada.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotEmojis, Separators
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from features.community.services.welcome_service import WelcomeService


# ── Helpers ───────────────────────────────────────────────────

async def _build_welcome_dashboard(guild: discord.Guild, welcome_svc: WelcomeService, event_type: str) -> discord.Embed:
    """Monta o embed principal do painel de Welcome."""
    config = await welcome_svc.get_config(guild.id, event_type)

    enabled = config.get("enabled", 0) == 1
    status = f"{BotEmojis.STATUS_ENABLED} Ativado" if enabled else f"{BotEmojis.STATUS_DISABLED} Desativado"

    ch_id = config.get("channel_id")
    ch = guild.get_channel(ch_id) if ch_id else None
    channel_str = ch.mention if ch else "*Nenhum canal selecionado*"

    emoji = config.get("welcome_emoji") or "👋"
    color = config.get("embed_color") or "*Padrão*"
    
    # Validação simples para saber o que está configurado
    content = config.get("content")
    title = config.get("embed_title")
    desc = config.get("embed_description")
    
    has_text = bool(content or title or desc)
    has_images = bool(config.get("embed_thumbnail") or config.get("embed_image"))
    has_author = bool(config.get("embed_author_name"))

    features_str = []
    if has_text: features_str.append("📝 Textos")
    if has_images: features_str.append("🖼️ Imagens")
    if has_author: features_str.append("👤 Autor/Rodapé")
    
    components = " • ".join(features_str) if features_str else "*Nada configurado*"

    description = (
        f"**{Separators.title('Status do Sistema')}**\n"
        f"**Estado:** {status}\n"
        f"**Canal:** {channel_str}\n"
        f"**Emoji Padrão:** {emoji}\n\n"
        
        f"**{Separators.title('Componentes Ativos')}**\n"
        f"{components}\n\n"
        
        f"**{Separators.title('Variáveis Disponíveis')}**\n"
        f"`{{@user}}` — Menção do usuário\n"
        f"`{{user}}` — Nome do usuário\n"
        f"`{{user.id}}` — ID do usuário\n"
        f"`{{server}}` — Nome do servidor\n"
        f"`{{server.member_count}}` — Total de membros\n"
        f"`{{emoji}}` — O emoji padrão configurado acima\n"
        f"`{{user.avatar}}` — URL da foto do usuário (use em imagens)\n"
        f"`{{server.icon}}` — URL da foto do servidor (use em imagens)\n"
    )

    event_name = "Entrada" if event_type == "join" else "Saída"

    return (
        EmbedBuilder.default()
        .author(
            name=f"Configuração de {event_name} — {guild.name}",
            icon_url=guild.icon.url if guild.icon else None,
        )
        .description(description)
        .footer("Use o menu abaixo para editar as opções e testar o resultado")
        .timestamp()
        .build()
    )


# ── Modais ────────────────────────────────────────────────────

class WelcomeTextModal(discord.ui.Modal, title="Textos Principais"):
    content_input = discord.ui.TextInput(
        label="Mensagem fora do Embed (opcional)",
        placeholder="Ex: Bem vindo {@user}!",
        style=discord.TextStyle.short,
        required=False,
        max_length=2000,
    )
    title_input = discord.ui.TextInput(
        label="Título do Embed",
        placeholder="Ex: {server} te dá as boas vindas!",
        style=discord.TextStyle.short,
        required=False,
        max_length=256,
    )
    desc_input = discord.ui.TextInput(
        label="Descrição do Embed",
        placeholder="Ex: Leia as regras e divirta-se, {user}!",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000,
    )

    def __init__(self, parent_view: "WelcomeConfigView", current_config: dict) -> None:
        super().__init__()
        self.parent_view = parent_view
        self.content_input.default = current_config.get("content", "")
        self.title_input.default = current_config.get("embed_title", "")
        self.desc_input.default = current_config.get("embed_description", "")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.parent_view.welcome_svc.update_config(
            interaction.guild.id,
            self.parent_view.event_type,
            changed_by=interaction.user.id,
            content=self.content_input.value,
            embed_title=self.title_input.value,
            embed_description=self.desc_input.value,
        )
        await self.parent_view.refresh(interaction, "Textos atualizados com sucesso!")


class WelcomeImagesModal(discord.ui.Modal, title="Imagens e Cores"):
    color_input = discord.ui.TextInput(
        label="Cor do Embed (HEX)",
        placeholder="Ex: FF0000 para vermelho",
        style=discord.TextStyle.short,
        required=False,
        max_length=7,
    )
    thumb_input = discord.ui.TextInput(
        label="URL da Thumbnail (Miniatura)",
        placeholder="Ex: {user.avatar} ou https://...",
        style=discord.TextStyle.short,
        required=False,
        max_length=1000,
    )
    image_input = discord.ui.TextInput(
        label="URL da Imagem Principal",
        placeholder="Ex: {server.icon} ou https://...",
        style=discord.TextStyle.short,
        required=False,
        max_length=1000,
    )

    def __init__(self, parent_view: "WelcomeConfigView", current_config: dict) -> None:
        super().__init__()
        self.parent_view = parent_view
        self.color_input.default = current_config.get("embed_color", "")
        self.thumb_input.default = current_config.get("embed_thumbnail", "")
        self.image_input.default = current_config.get("embed_image", "")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.parent_view.welcome_svc.update_config(
            interaction.guild.id,
            self.parent_view.event_type,
            changed_by=interaction.user.id,
            embed_color=self.color_input.value,
            embed_thumbnail=self.thumb_input.value,
            embed_image=self.image_input.value,
        )
        await self.parent_view.refresh(interaction, "Imagens e cor atualizadas!")


class WelcomeAuthorFooterModal(discord.ui.Modal, title="Autor e Rodapé"):
    author_name_input = discord.ui.TextInput(
        label="Nome do Autor",
        placeholder="Ex: {server}",
        style=discord.TextStyle.short,
        required=False,
        max_length=256,
    )
    author_icon_input = discord.ui.TextInput(
        label="Ícone do Autor (URL)",
        placeholder="Ex: {server.icon}",
        style=discord.TextStyle.short,
        required=False,
        max_length=1000,
    )
    footer_text_input = discord.ui.TextInput(
        label="Texto do Rodapé",
        placeholder="Ex: Você é o membro #{server.member_count}!",
        style=discord.TextStyle.short,
        required=False,
        max_length=2048,
    )

    def __init__(self, parent_view: "WelcomeConfigView", current_config: dict) -> None:
        super().__init__()
        self.parent_view = parent_view
        self.author_name_input.default = current_config.get("embed_author_name", "")
        self.author_icon_input.default = current_config.get("embed_author_icon", "")
        self.footer_text_input.default = current_config.get("embed_footer_text", "")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.parent_view.welcome_svc.update_config(
            interaction.guild.id,
            self.parent_view.event_type,
            changed_by=interaction.user.id,
            embed_author_name=self.author_name_input.value,
            embed_author_icon=self.author_icon_input.value,
            embed_footer_text=self.footer_text_input.value,
        )
        await self.parent_view.refresh(interaction, "Autor e Rodapé atualizados!")


class WelcomeEmojiModal(discord.ui.Modal, title="Emoji Customizado"):
    emoji_input = discord.ui.TextInput(
        label="Emoji padrão ({emoji})",
        placeholder="Ex: 👋 ou um emoji do servidor",
        style=discord.TextStyle.short,
        required=True,
        max_length=60,
    )

    def __init__(self, parent_view: "WelcomeConfigView", current_config: dict) -> None:
        super().__init__()
        self.parent_view = parent_view
        self.emoji_input.default = current_config.get("welcome_emoji", "👋")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.parent_view.welcome_svc.update_config(
            interaction.guild.id,
            self.parent_view.event_type,
            changed_by=interaction.user.id,
            welcome_emoji=self.emoji_input.value,
        )
        await self.parent_view.refresh(interaction, "Emoji customizado atualizado!")


# ── View ──────────────────────────────────────────────────────

class WelcomeConfigView(discord.ui.View):
    """Painel de configuração de Welcome."""

    def __init__(self, welcome_svc: WelcomeService, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=300)
        self.welcome_svc = welcome_svc
        self.guild = guild
        self.admin_id = admin_id
        self.event_type = "join"
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user("Apenas quem usou o comando pode interagir.").build()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    async def refresh(self, interaction: discord.Interaction, success_msg: str | None = None) -> None:
        embed = await _build_welcome_dashboard(self.guild, self.welcome_svc, self.event_type)
        content = f"{BotEmojis.COMMON_SPARKLES} {success_msg}" if success_msg else None
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    @discord.ui.select(
        placeholder="O que você quer configurar?",
        options=[
            discord.SelectOption(label="Modo: Entrada", value="mode_join", emoji="👋", description="Alternar para configurar mensagens de Boas-vindas"),
            discord.SelectOption(label="Modo: Saída", value="mode_leave", emoji="🚪", description="Alternar para configurar mensagens de Despedida"),
            discord.SelectOption(label="Ativar / Desativar", value="toggle", emoji=BotEmojis.ACTION_TOGGLE, description="Liga ou desliga o sistema no modo atual"),
            discord.SelectOption(label="Textos (Título, Descrição)", value="texts", emoji="📝", description="Mensagem, título e descrição do embed"),
            discord.SelectOption(label="Imagens e Cor", value="images", emoji="🖼️", description="Thumbnail, Imagem Maior e Cor HEX"),
            discord.SelectOption(label="Autor e Rodapé", value="footer", emoji="👤", description="Rodapé e seção do autor (ícones e nomes)"),
            discord.SelectOption(label="Emoji Customizado", value="emoji", emoji="✨", description="Mude o emoji padrão do {emoji}"),
            discord.SelectOption(label="Visualizar Resultado", value="preview", emoji="👁️", description="Veja como a mensagem real ficará!"),
        ],
        row=0,
    )
    async def config_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        action = select.values[0]
        config = await self.welcome_svc.get_config(interaction.guild.id, self.event_type)

        if action == "mode_join":
            self.event_type = "join"
            await self.refresh(interaction)
            return

        elif action == "mode_leave":
            self.event_type = "leave"
            await self.refresh(interaction)
            return

        elif action == "toggle":
            new_state = 0 if config.get("enabled", 0) == 1 else 1
            await self.welcome_svc.update_config(interaction.guild.id, self.event_type, changed_by=interaction.user.id, enabled=new_state)
            state_str = "ATIVADO" if new_state else "DESATIVADO"
            await self.refresh(interaction, f"Sistema de Welcome foi **{state_str}**!")

        elif action == "texts":
            await interaction.response.send_modal(WelcomeTextModal(self, config))

        elif action == "images":
            await interaction.response.send_modal(WelcomeImagesModal(self, config))

        elif action == "footer":
            await interaction.response.send_modal(WelcomeAuthorFooterModal(self, config))

        elif action == "emoji":
            await interaction.response.send_modal(WelcomeEmojiModal(self, config))

        elif action == "preview":
            content, embed = self.welcome_svc.build_welcome_message(interaction.user, config)
            if not content and not embed:
                await interaction.response.send_message(
                    embed=EmbedBuilder.error_user("Você não configurou nenhum texto, título ou imagem para visualizar!").build(),
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                content=content,
                embed=embed,
                ephemeral=True
            )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Selecione o canal para enviar...",
        row=1,
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect) -> None:
        channel = select.values[0]
        await self.welcome_svc.update_config(interaction.guild.id, self.event_type, changed_by=interaction.user.id, channel_id=channel.id)
        await self.refresh(interaction, f"Canal de envio definido para {channel.mention}")

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


# ── Cog ───────────────────────────────────────────────────────

class WelcomeCog(commands.Cog):
    """Cog para envio e configuração de mensagens de boas-vindas."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.svc = bot.welcome_service

    @commands.hybrid_command(name="welcome", description="Configura mensagens de boas-vindas e despedidas (Entrada/Saída)")
    @commands.has_permissions(administrator=True)
    async def welcome_cmd(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not guild:
            return

        embed = await _build_welcome_dashboard(guild, self.svc, "join")
        view = WelcomeConfigView(self.svc, guild, ctx.author.id)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Envia a mensagem de boas-vindas quando alguém entra no servidor."""
        await self._handle_event(member, "join")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Envia a mensagem de despedida quando alguém sai do servidor."""
        await self._handle_event(member, "leave")

    async def _handle_event(self, member: discord.Member, event_type: str) -> None:
        if member.bot:
            return

        guild = member.guild
        config = await self.svc.get_config(guild.id, event_type)
        
        # Verificar se está habilitado e se tem canal definido
        if config.get("enabled", 0) != 1:
            return
            
        channel_id = config.get("channel_id")
        if not channel_id:
            return
            
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        # Construir e enviar a mensagem
        content, embed = self.svc.build_welcome_message(member, config)
        
        if not content and not embed:
            return  # Nada para enviar

        try:
            await channel.send(content=content, embed=embed)
        except discord.Forbidden:
            pass # Sem permissão para enviar no canal configurado
        except Exception:
            pass # Ignorar erros aleatórios

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Inicializa o banco de dados da guilda e envia mensagem mínima de boas-vindas."""
        await self.bot.guild_service.repo.ensure_guild(guild.id)

        channel = guild.system_channel
        if not channel or not channel.permissions_for(guild.me).send_messages:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break

        if not channel:
            return

        try:
            await channel.send(
                f"{BotEmojis.COMMON_SPARKLES} Olá, **{guild.name}**! Eu sou a **Luna**. "
                f"Use `/tutorial` para ver um guia completo de como me usar, "
                f"ou `/config` para configurar o servidor."
            )
        except Exception:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
