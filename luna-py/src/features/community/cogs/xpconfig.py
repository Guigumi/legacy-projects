"""
Cog de configuração de XP — painel interativo para admins.
Comando: !xpconfig ou /xpconfig

Permite configurar:
1. XP necessário para upar 1 level
2. XP por ação (chat, call, reação)
3. Canais bloqueados ou com boost de XP
4. Cargos com boost de XP
5. Cargos ganhos ao atingir determinado nível
"""

from __future__ import annotations

import discord
from discord.ext import commands

from config.settings import BotEmojis, Separators
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from features.community.services import XPConfigService

# ── Helpers ───────────────────────────────────────────────────


async def _build_xp_dashboard(guild: discord.Guild, xp_svc: XPConfigService) -> discord.Embed:
    """Monta o embed principal do painel de XP."""
    config = await xp_svc.get_config(guild.id)
    channel_configs = await xp_svc.get_channel_configs(guild.id)
    boost_roles = await xp_svc.get_boost_roles(guild.id)
    level_roles = await xp_svc.get_level_roles(guild.id)

    # Seção 1: XP por level
    xp_per_lvl = config.get("xp_per_level", 100)

    # Seção 2: XP por ação
    xp_msg = config.get("xp_per_message", 5)
    xp_voice = config.get("xp_per_voice_min", 3)
    xp_react = config.get("xp_per_reaction", 2)

    # Seção 3: Canais
    blocked_channels = []
    boost_channels = []
    for cc in channel_configs:
        ch = guild.get_channel(cc["channel_id"])
        ch_name = ch.mention if ch else f"`#{cc['channel_id']}`"
        if cc["mode"] == "blocked":
            blocked_channels.append(f"{BotEmojis.COMMON_BLOCK} {ch_name}")
        elif cc["mode"] == "boost":
            boost_channels.append(
                f"{BotEmojis.COMMON_BOOST} {ch_name} — **{cc['multiplier']}x**"
            )

    channels_text = ""
    if blocked_channels:
        channels_text += (
            "**Bloqueados (sem XP):**\n" + "\n".join(blocked_channels) + "\n"
        )
    if boost_channels:
        channels_text += "**Com Boost:**\n" + "\n".join(boost_channels) + "\n"
    if not channels_text:
        channels_text = "*Nenhum canal configurado*"

    # Seção 4: Cargos com boost
    if boost_roles:
        roles_text = "\n".join(
            f"{BotEmojis.COMMON_DIAMOND} <@&{br['role_id']}> — **{br['multiplier']}x**"
            for br in boost_roles
        )
    else:
        roles_text = "*Nenhum cargo com boost*"

    # Seção 5: Cargos por nível
    policy = config.get("role_policy", "stack")
    policy_str = "Acumular (Stack)" if policy == "stack" else "Substituir (Replace)"
    if level_roles:
        level_text = "\n".join(
            f"{BotEmojis.COMMON_LVL_UP} **Nível {lr['level']}** → <@&{lr['role_id']}>"
            for lr in level_roles
        )
    else:
        level_text = "*Nenhum cargo por nível configurado*"

    # Seção 6: Anúncios
    lvl_mode = config.get("level_up_mode", "current")
    lvl_ch_id = config.get("level_up_channel_id")
    
    if lvl_mode == "disabled":
        anuncio_text = f"{BotEmojis.STATUS_DISABLED} Desativado"
    elif lvl_mode == "specific" and lvl_ch_id:
        ch = guild.get_channel(lvl_ch_id)
        anuncio_text = f"{BotEmojis.LOCATION} Específico: {ch.mention if ch else f'`#{lvl_ch_id}`'}"
    else:
        anuncio_text = f"{BotEmojis.COMMON_MESSAGE} Atual (Onde upou)"

    msg_text = config.get("level_up_message") or "Parabéns {@user}! Você evoluiu para o **Nível {level}**!"

    description = (
        f"**{Separators.title('XP por Nível')}**\n"
        f"```{xp_per_lvl} XP por nível```\n"
        f"Fórmula: `nível × {xp_per_lvl}` XP para subir\n"
        f"Ex: Nível 5 → precisa de **{5 * xp_per_lvl}** XP total\n\n"
        f"**{Separators.title('XP por Ação')}**\n"
        f"{BotEmojis.COMMON_TROPHY} Meta: **{xp_per_lvl}** XP por nível\n"
        f"{BotEmojis.COMMON_MESSAGE} Mensagem: **{xp_msg}** XP\n"
        f"{BotEmojis.COMMON_VOICE} Voz (por minuto): **{xp_voice}** XP\n"
        f"{BotEmojis.COMMON_REACTION} Reação: **{xp_react}** XP\n\n"
        f"**{Separators.title('Anúncio de Nível')}**\n"
        f"{anuncio_text} *(Use `/xp-anuncio`)*\n"
        f"Texto: `{msg_text}`\n"
        f"Variáveis: `{{@user}}`, `{{user}}`, `{{level_new}}`, `{{level_old}}`, `{{xp}}`, `{{roles}}`\n\n"
        f"**{Separators.title('Canais')}**\n"
        f"{channels_text}\n"
        f"**{Separators.title('Cargos com Boost')}**\n"
        f"{roles_text}\n\n"
        f"**{Separators.title('Cargos por Nível')}**\n"
        f"Política: **{policy_str}**\n"
        f"{level_text}"
    )


    return (
        EmbedBuilder.default()
        .author(
            name=f"Configuração de XP — {guild.name}",
            icon_url=guild.icon.url if guild.icon else None,
        )
        .description(description)
        .footer("Use os botões abaixo para editar cada seção")
        .timestamp()
        .build()
    )


async def _build_level_up_preview(guild: discord.Guild, xp_svc: XPConfigService, member: discord.Member) -> discord.Embed:
    """Preview visual de como será emitido o Level Up."""
    config = await xp_svc.get_config(guild.id)
    msg_title = config.get("level_up_title") or f"{BotEmojis.COMMON_SPARKLES} Novo Nível Alcançado!"
    msg_text = config.get("level_up_message")
    
    if not msg_text:
        msg_text = "Parabéns {@user}! Você evoluiu para o **Nível {level_new}**!"

    def apply_tags(text: str) -> str:
        text = text.replace("{@user}", member.mention)
        text = text.replace("{user}", member.display_name)
        text = text.replace("{level}", "10")
        text = text.replace("{level_new}", "10")
        text = text.replace("{level_old}", "9")
        text = text.replace("{xp}", "1500")
        return text

    msg_title = apply_tags(msg_title)
    msg_text = apply_tags(msg_text)

    roles_mentions = "<@&123456789>"
    if "{roles}" in msg_text:
        msg_text = msg_text.replace("{roles}", roles_mentions)
    
    if "{roles}" in msg_title:
        msg_title = msg_title.replace("{roles}", "")

    return (
        EmbedBuilder.default()
        .author(name=msg_title, icon_url=member.display_avatar.url)
        .description(msg_text)
        .build()
    )

# ── Modais ────────────────────────────────────────────────────


class XPPerLevelModal(discord.ui.Modal, title="XP por Nível"):
    """Modal para configurar XP necessário por nível."""

    xp_input = discord.ui.TextInput(
        label="XP necessário por nível",
        placeholder="Ex: 100 (nível 5 = 500 XP)",
        min_length=1,
        max_length=6,
        required=True,
    )

    def __init__(self, parent_view: XPConfigPanel) -> None:
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = int(self.xp_input.value.strip())
            if value < 10 or value > 100000:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Valor inválido. Use um número entre 10 e 100.000.",
            )
            return

        xp_svc = self.parent_view.xp_svc
        await xp_svc.update_config(
            interaction.guild.id,
            changed_by=interaction.user.id,
            xp_per_level=value,
        )
        embed = await _build_xp_dashboard(interaction.guild, xp_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} XP por nível alterado para **{value}**",
            embed=embed,
            view=self.parent_view,
        )


class XPPerActionModal(discord.ui.Modal, title="XP por Ação"):
    """Modal para configurar XP por ação."""

    xp_msg = discord.ui.TextInput(
        label="XP por mensagem",
        placeholder="Ex: 5",
        min_length=1,
        max_length=5,
        required=True,
    )
    xp_voice = discord.ui.TextInput(
        label="XP por minuto em call",
        placeholder="Ex: 3",
        min_length=1,
        max_length=5,
        required=True,
    )
    xp_react = discord.ui.TextInput(
        label="XP por reação",
        placeholder="Ex: 2",
        min_length=1,
        max_length=5,
        required=True,
    )

    def __init__(self, parent_view: XPConfigPanel) -> None:
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            msg_val = int(self.xp_msg.value.strip())
            voice_val = int(self.xp_voice.value.strip())
            react_val = int(self.xp_react.value.strip())
            if any(v < 0 or v > 10000 for v in (msg_val, voice_val, react_val)):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Valores inválidos. Use números entre 0 e 10.000.",
            )
            return

        xp_svc = self.parent_view.xp_svc
        await xp_svc.update_config(
            interaction.guild.id,
            changed_by=interaction.user.id,
            xp_per_message=msg_val,
            xp_per_voice_min=voice_val,
            xp_per_reaction=react_val,
        )
        embed = await _build_xp_dashboard(interaction.guild, xp_svc)
        await interaction.response.edit_message(
            content=(
                f"{BotEmojis.COMMON_SPARKLES} XP por ação atualizado: "
                f"{BotEmojis.COMMON_MESSAGE} {msg_val} | "
                f"{BotEmojis.COMMON_VOICE} {voice_val} | "
                f"{BotEmojis.COMMON_REACTION} {react_val}"
            ),
            embed=embed,
            view=self.parent_view,
        )


class LevelUpTitleModal(discord.ui.Modal, title="Título do Nível"):
    """Modal para configurar título do anúncio de Level Up."""

    title_input = discord.ui.TextInput(
        label="Texto do Título",
        placeholder="Ex: Novo Nível Alcançado!",
        style=discord.TextStyle.short,
        min_length=1,
        max_length=256,
        required=True,
    )

    def __init__(self, parent_view: "LevelUpMessagePanelView") -> None:
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = self.title_input.value.strip()

        await self.parent_view.xp_svc.update_config(
            interaction.guild.id,
            changed_by=interaction.user.id,
            level_up_title=val,
        )
        embed = await _build_level_up_preview(interaction.guild, self.parent_view.xp_svc, interaction.user)
        content_text = await self.parent_view.get_status_text()
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} Título de anúncio atualizado!\n{content_text}",
            embed=embed,
            view=self.parent_view,
        )


class LevelUpMessageModal(discord.ui.Modal, title="Mensagem de Nível"):
    """Modal para configurar texto do anúncio de Level Up."""

    message_input = discord.ui.TextInput(
        label="Texto da Mensagem",
        placeholder="Parabéns {@user}! {level_old} -> {level_new} | {roles}",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1000,
        required=True,
    )

    def __init__(self, parent_view: "LevelUpMessagePanelView") -> None:
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = self.message_input.value.strip()

        await self.parent_view.xp_svc.update_config(
            interaction.guild.id,
            changed_by=interaction.user.id,
            level_up_message=val,
        )
        embed = await _build_level_up_preview(interaction.guild, self.parent_view.xp_svc, interaction.user)
        content_text = await self.parent_view.get_status_text()
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} Mensagem de anúncio atualizada!\n{content_text}",
            embed=embed,
            view=self.parent_view,
        )


class ChannelBoostMultiplierModal(discord.ui.Modal, title="Multiplicador do Canal"):
    """Modal para definir o multiplicador de boost de XP de um canal."""

    multiplier_input = discord.ui.TextInput(
        label="Multiplicador de XP",
        placeholder="Ex: 2.0 (dobro do XP) ou 1.5 (50% a mais)",
        min_length=1,
        max_length=5,
        required=True,
    )

    def __init__(self, parent_view: ChannelConfigSubView, channel_id: int) -> None:
        super().__init__()
        self.parent_view = parent_view
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = float(self.multiplier_input.value.strip().replace(",", "."))
            if value < 0.1 or value > 10.0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Valor inválido. Use um número entre 0.1 e 10.0.",
            )
            return

        xp_svc = self.parent_view.xp_svc
        await xp_svc.set_channel_boost(interaction.guild.id, self.channel_id, value)
        ch = interaction.guild.get_channel(self.channel_id)
        ch_name = ch.mention if ch else f"`#{self.channel_id}`"

        main_view = XPConfigPanel(xp_svc, interaction.guild, self.parent_view.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, xp_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_BOOST} {ch_name} agora dá **{value}x** XP",
            embed=embed,
            view=main_view,
        )


class RoleBoostMultiplierModal(discord.ui.Modal, title="Multiplicador do Cargo"):
    """Modal para definir o multiplicador de boost de XP de um cargo."""

    multiplier_input = discord.ui.TextInput(
        label="Multiplicador de XP",
        placeholder="Ex: 1.5 (50% a mais) ou 2.0 (dobro)",
        min_length=1,
        max_length=5,
        required=True,
    )

    def __init__(self, parent_view: BoostRoleSubView, role_id: int) -> None:
        super().__init__()
        self.parent_view = parent_view
        self.role_id = role_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = float(self.multiplier_input.value.strip().replace(",", "."))
            if value < 1.0 or value > 10.0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Valor inválido. Use um número entre 1.0 e 10.0.",
            )
            return

        xp_svc = self.parent_view.xp_svc
        await xp_svc.set_boost_role(interaction.guild.id, self.role_id, value)

        main_view = XPConfigPanel(xp_svc, interaction.guild, self.parent_view.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, xp_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_DIAMOND} <@&{self.role_id}> agora dá **{value}x** XP",
            embed=embed,
            view=main_view,
        )


class LevelRoleModal(discord.ui.Modal, title="Cargo por Nível"):
    """Modal para definir nível de um cargo-recompensa."""

    level_input = discord.ui.TextInput(
        label="Nível necessário",
        placeholder="Ex: 5, 10, 20",
        min_length=1,
        max_length=5,
        required=True,
    )

    def __init__(self, parent_view: LevelRoleSubView, role_id: int) -> None:
        super().__init__()
        self.parent_view = parent_view
        self.role_id = role_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = int(self.level_input.value.strip())
            if value < 1 or value > 1000:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Nível inválido. Use um número entre 1 e 1000.",
            )
            return

        xp_svc = self.parent_view.xp_svc
        await xp_svc.set_level_role(interaction.guild.id, value, self.role_id)

        main_view = XPConfigPanel(xp_svc, interaction.guild, self.parent_view.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, xp_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_LVL_UP} <@&{self.role_id}> será dado no **Nível {value}**",
            embed=embed,
            view=main_view,
        )


# ── Sub-views ─────────────────────────────────────────────────


class ChannelConfigSubView(discord.ui.View):
    """Sub-painel para configurar canais (bloquear ou dar boost)."""

    def __init__(
        self, xp_svc: XPConfigService, guild: discord.Guild, admin_id: int, action: str = "blocked"
    ) -> None:
        super().__init__(timeout=180)
        self.xp_svc = xp_svc
        self.guild = guild
        self.admin_id = admin_id
        self.action = action  # "blocked" ou "boost"
        self.selected_channel_id: int | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    def _build_embed(self) -> discord.Embed:
        if self.action == "blocked":
            return (
                EmbedBuilder.default()
                .author(name="Bloquear Canal de XP")
                .description(
                    "Selecione um canal onde **nenhum XP** será ganho.\n\n"
                    "*Útil para canais de spam, bots ou off-topic.*"
                )
                .footer("Selecione um canal abaixo")
                .build()
            )
        else:
            return (
                EmbedBuilder.default()
                .author(name="Canal com Boost de XP")
                .description(
                    "Selecione um canal que dará **XP extra**.\n\n"
                    "*Após selecionar, defina o multiplicador (ex: 2.0 = dobro).*"
                )
                .footer("Selecione um canal abaixo")
                .build()
            )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.voice],
        placeholder="Selecionar canal...",
        row=0,
    )
    async def channel_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ):
        channel = select.values[0]

        if self.action == "blocked":
            await self.xp_svc.set_channel_blocked(interaction.guild.id, channel.id)
            main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
            embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
            await interaction.response.edit_message(
                content=f"{BotEmojis.COMMON_BLOCK} {channel.mention} agora **não dá XP**",
                embed=embed,
                view=main_view,
            )
        else:
            # Boost: pedir multiplicador via modal
            self.selected_channel_id = channel.id
            await interaction.response.send_modal(
                ChannelBoostMultiplierModal(self, channel.id)
            )

    @discord.ui.button(
        label="Voltar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_BACK, row=1
    )
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=None, embed=embed, view=main_view
        )


class RemoveChannelSubView(discord.ui.View):
    """Sub-painel para remover configuração de canal."""

    def __init__(self, xp_svc: XPConfigService, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=180)
        self.xp_svc = xp_svc
        self.guild = guild
        self.admin_id = admin_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.voice],
        placeholder="Selecionar canal para remover config...",
        row=0,
    )
    async def channel_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ):
        channel = select.values[0]
        await self.xp_svc.remove_channel_config(interaction.guild.id, channel.id)
        main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} Configuração de XP removida de {channel.mention}",
            embed=embed,
            view=main_view,
        )

    @discord.ui.button(
        label="Voltar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_BACK, row=1
    )
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=None, embed=embed, view=main_view
        )


class BoostRoleSubView(discord.ui.View):
    """Sub-painel para configurar cargos com boost de XP."""

    def __init__(self, xp_svc: XPConfigService, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=180)
        self.xp_svc = xp_svc
        self.guild = guild
        self.admin_id = admin_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    def _build_embed(self) -> discord.Embed:
        return (
            EmbedBuilder.default()
            .author(name="Cargo com Boost de XP")
            .description(
                "Selecione um cargo que receberá **multiplicador de XP**.\n\n"
                "*Membros com esse cargo ganharão XP extra em todas as ações.\n"
                "Se um membro tiver vários cargos com boost, o maior multiplicador é usado.*"
            )
            .footer("Selecione um cargo abaixo")
            .build()
        )

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Selecionar cargo...",
        row=0,
    )
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ):
        role = select.values[0]
        await interaction.response.send_modal(RoleBoostMultiplierModal(self, role.id))

    @discord.ui.button(
        label="Voltar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_BACK, row=1
    )
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=None, embed=embed, view=main_view
        )


class RemoveBoostRoleSubView(discord.ui.View):
    """Sub-painel para remover boost de um cargo."""

    def __init__(self, xp_svc: XPConfigService, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=180)
        self.xp_svc = xp_svc
        self.guild = guild
        self.admin_id = admin_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Selecionar cargo para remover boost...",
        row=0,
    )
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ):
        role = select.values[0]
        await self.xp_svc.remove_boost_role(interaction.guild.id, role.id)
        main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_DIAMOND} Boost removido de <@&{role.id}>",
            embed=embed,
            view=main_view,
        )

    @discord.ui.button(
        label="Voltar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_BACK, row=1
    )
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=None, embed=embed, view=main_view
        )


class LevelRoleSubView(discord.ui.View):
    """Sub-painel para configurar cargos por nível."""

    def __init__(self, xp_svc: XPConfigService, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=180)
        self.xp_svc = xp_svc
        self.guild = guild
        self.admin_id = admin_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    def _build_embed(self) -> discord.Embed:
        return (
            EmbedBuilder.default()
            .author(name="Cargo por Nível")
            .description(
                "Selecione um cargo que será **dado automaticamente** "
                "quando o membro atingir um nível específico.\n\n"
                "*Após selecionar o cargo, defina o nível necessário.*"
            )
            .footer("Selecione um cargo abaixo")
            .build()
        )

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Selecionar cargo-recompensa...",
        row=0,
    )
    async def role_select(
        self, interaction: discord.Interaction, select: discord.ui.RoleSelect
    ):
        role = select.values[0]
        await interaction.response.send_modal(LevelRoleModal(self, role.id))

    @discord.ui.button(
        label="Voltar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_BACK, row=1
    )
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=None, embed=embed, view=main_view
        )


class RemoveLevelRoleSubView(discord.ui.View):
    """Sub-painel para remover cargo de nível."""

    def __init__(
        self, xp_svc: XPConfigService, guild: discord.Guild, admin_id: int, level_roles: list[dict]
    ) -> None:
        super().__init__(timeout=180)
        self.xp_svc = xp_svc
        self.guild = guild
        self.admin_id = admin_id

        # Montar select options dinamicamente
        options = []
        for lr in level_roles[:25]:  # Discord limita 25 opções
            role = guild.get_role(lr["role_id"])
            role_name = role.name if role else f"ID: {lr['role_id']}"
            options.append(
                discord.SelectOption(
                    label=f"Nível {lr['level']} → {role_name}",
                    value=f"{lr['level']}:{lr['role_id']}",
                    emoji=BotEmojis.COMMON_LVL_UP,
                )
            )

        if options:
            self.remove_select.options = options
        else:
            self.remove_select.disabled = True
            self.remove_select.options = [
                discord.SelectOption(label="Nenhum cargo configurado", value="none")
            ]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    @discord.ui.select(placeholder="Selecionar para remover...", row=0)
    async def remove_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        value = select.values[0]
        if value == "none":
            return

        level_str, role_id_str = value.split(":")
        level = int(level_str)
        role_id = int(role_id_str)

        await self.xp_svc.remove_level_role(interaction.guild.id, level, role_id)
        main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} Cargo <@&{role_id}> removido do **Nível {level}**",
            embed=embed,
            view=main_view,
        )

    @discord.ui.button(
        label="Voltar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_BACK, row=1
    )
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        main_view = XPConfigPanel(self.xp_svc, interaction.guild, self.admin_id)
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=None, embed=embed, view=main_view
        )


class LevelUpMessagePanelView(discord.ui.View):
    """Sub-painel para visualização e edição da Mensagem de Nível."""

    def __init__(self, xp_svc: XPConfigService, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=300)
        self.xp_svc = xp_svc
        self.guild = guild
        self.admin_id = admin_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    @discord.ui.button(
        label="Editar Título", style=discord.ButtonStyle.primary, emoji=BotEmojis.ACTION_EDIT, row=0
    )
    async def edit_title_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelUpTitleModal(self))

    @discord.ui.button(
        label="Editar Descrição", style=discord.ButtonStyle.primary, emoji=BotEmojis.ACTION_EDIT, row=0
    )
    async def edit_desc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LevelUpMessageModal(self))

    async def get_status_text(self) -> str:
        config = await self.xp_svc.get_config(self.guild.id)
        mode = config.get("level_up_mode", "current")
        cid = config.get("level_up_channel_id")
        
        if mode == "disabled":
            m_text = f"{BotEmojis.STATUS_DISABLED} Desativado"
        elif mode == "specific":
            m_text = f"{BotEmojis.COMMON_PIN} Canal Fixo (<#{cid}>)" if cid else f"{BotEmojis.COMMON_PIN} Canal Fixo ({BotEmojis.STATUS_WARNING} Sem canal definido)"
        else:
            m_text = f"{BotEmojis.COMMON_MESSAGE} Chat Atual (onde upou)"
            
        return f"{BotEmojis.COMMON_TIP} **Preview Interativo**: Configure a exibição do Level Up abaixo.\n{BotEmojis.COMMON_MESSAGE} **Envio Atual**: {m_text}"

    @discord.ui.button(
        label="Funções", style=discord.ButtonStyle.secondary, emoji=BotEmojis.COMMON_MESSAGE, row=0
    )
    async def functions_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        help_text = (
            "`{@user}` : Menciona o usuário (ex: <@12345>)\n"
            "`{user}` : Nome de exibição do usuário\n"
            "`{level_new}` ou `{level}` : O nível atingido\n"
            "`{level_old}` : O nível anterior\n"
            "`{xp}` : A pontuação total de XP atual do usuário\n"
            "`{roles}` : Insere a lista de cargos ganhos (se houver)\n\n"
            "Estas *Tags* formam seu anúncio dinamicamente. Podem ser inseridas no **Título** (exceto `{roles}`) e na **Descrição**."
        )
        embed = (
            EmbedBuilder.default()
            .author(name="Variáveis de Nível")
            .description(help_text)
            .build()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, view=discord.ui.View())

    @discord.ui.select(
        placeholder="Onde postar os Levels?",
        options=[
            discord.SelectOption(
                label="Chat Atual", value="current", description="Onde o membro acabou de upar"
            ),
            discord.SelectOption(
                label="Canal Fixo", value="specific", description="Sempre no mesmo lugar"
            ),
            discord.SelectOption(
                label="Desativado", value="disabled", description="Não avisar nivelamento"
            ),
        ],
        row=1,
    )
    async def mode_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        mode = select.values[0]
        await self.xp_svc.update_config(interaction.guild.id, changed_by=interaction.user.id, level_up_mode=mode)
        embed = await _build_level_up_preview(interaction.guild, self.xp_svc, interaction.user)
        await interaction.response.edit_message(content=await self.get_status_text(), embed=embed, view=self)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Vincular ao canal fixo...",
        row=2,
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = select.values[0]
        await self.xp_svc.update_config(
            interaction.guild.id, changed_by=interaction.user.id, level_up_mode="specific", level_up_channel_id=channel.id
        )
        embed = await _build_level_up_preview(interaction.guild, self.xp_svc, interaction.user)
        await interaction.response.edit_message(content=await self.get_status_text(), embed=embed, view=self)

    @discord.ui.button(
        label="Voltar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_BACK, row=3
    )
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        main_view = XPConfigPanel(self.xp_svc, self.guild, self.admin_id)
        embed = await _build_xp_dashboard(self.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=None, embed=embed, view=main_view
        )


# ── Painel Principal ──────────────────────────────────────────


class XPConfigPanel(discord.ui.View):
    """Painel centralizado de configuração de XP.

    Navegação por Select Menu -- opcoes agrupadas por categoria para clareza.
    """

    def __init__(self, xp_svc: XPConfigService, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=300)
        self.xp_svc = xp_svc
        self.guild = guild
        self.admin_id = admin_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True


    # Row 0: Menu principal agrupado por categoria
    @discord.ui.select(
        placeholder="O que deseja configurar?",
        options=[
            # XP Base
            discord.SelectOption(
                label="XP por Nivel",
                value="xp_level",
                emoji=BotEmojis.COMMON_LVL_UP,
                description="Quantidade de XP necessaria para subir um nivel",
            ),
            discord.SelectOption(
                label="XP por Acao",
                value="xp_action",
                emoji=BotEmojis.COMMON_RAY,
                description="XP ganho por mensagem, voz e reacao",
            ),
            # Canais
            discord.SelectOption(
                label="Canal — Bloquear XP",
                value="block_channel",
                emoji=BotEmojis.COMMON_BLOCK,
                description="Impedir que XP seja ganho em um canal",
            ),
            discord.SelectOption(
                label="Canal — Adicionar Boost",
                value="boost_channel",
                emoji=BotEmojis.COMMON_BOOST,
                description="Multiplicar o XP ganho em um canal especifico",
            ),
            discord.SelectOption(
                label="Canal — Remover Config",
                value="remove_channel",
                emoji=BotEmojis.ACTION_REMOVE,
                description="Restaurar comportamento padrao de um canal",
            ),
            # Cargos com Boost
            discord.SelectOption(
                label="Cargo — Adicionar Boost",
                value="boost_role",
                emoji=BotEmojis.COMMON_DIAMOND,
                description="Dar multiplicador de XP a um cargo",
            ),
            discord.SelectOption(
                label="Cargo — Remover Boost",
                value="remove_boost_role",
                emoji=BotEmojis.ACTION_REMOVE,
                description="Remover o multiplicador de XP de um cargo",
            ),
            # Cargos por Nivel
            discord.SelectOption(
                label="Cargo por Nivel — Adicionar",
                value="level_role",
                emoji=BotEmojis.COMMON_LVL_UP,
                description="Dar um cargo automaticamente ao atingir um nivel",
            ),
            discord.SelectOption(
                label="Cargo por Nivel — Remover",
                value="remove_level_role",
                emoji=BotEmojis.ACTION_REMOVE,
                description="Remover um cargo que era dado por nivel",
            ),
            discord.SelectOption(
                label="Cargo por Nivel — Politica",
                value="role_policy",
                emoji=BotEmojis.COMMON_ADMIN,
                description="Escolher se cargos por nivel acumulam ou se substituem",
            ),
            # Anuncio de Level Up
            discord.SelectOption(
                label="Mensagem de Nivel",
                value="level_msg",
                emoji=BotEmojis.COMMON_MESSAGE,
                description="Texto e canal do anuncio ao subir de nivel",
            ),
        ],
        row=0,
    )
    async def nav_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        action = select.values[0]

        if action == "xp_level":
            await interaction.response.send_modal(XPPerLevelModal(self))

        elif action == "xp_action":
            await interaction.response.send_modal(XPPerActionModal(self))

        elif action == "level_msg":
            view = LevelUpMessagePanelView(self.xp_svc, self.guild, self.admin_id)
            embed = await _build_level_up_preview(self.guild, self.xp_svc, interaction.user)
            msg_preview_content = await view.get_status_text()
            await interaction.response.edit_message(content=msg_preview_content, embed=embed, view=view)

        elif action == "block_channel":
            sub = ChannelConfigSubView(
                self.xp_svc, interaction.guild, self.admin_id, action="blocked"
            )
            embed = sub._build_embed()
            await interaction.response.edit_message(content=None, embed=embed, view=sub)

        elif action == "boost_channel":
            sub = ChannelConfigSubView(
                self.xp_svc, interaction.guild, self.admin_id, action="boost"
            )
            embed = sub._build_embed()
            await interaction.response.edit_message(content=None, embed=embed, view=sub)

        elif action == "remove_channel":
            sub = RemoveChannelSubView(self.xp_svc, interaction.guild, self.admin_id)
            embed = (
                EmbedBuilder.default()
                .author(name="Remover Config de Canal")
                .description("Selecione o canal cuja configuracao de XP sera removida.")
                .footer("O canal voltara ao comportamento padrao")
                .build()
            )
            await interaction.response.edit_message(content=None, embed=embed, view=sub)

        elif action == "boost_role":
            sub = BoostRoleSubView(self.xp_svc, interaction.guild, self.admin_id)
            embed = sub._build_embed()
            await interaction.response.edit_message(content=None, embed=embed, view=sub)

        elif action == "remove_boost_role":
            sub = RemoveBoostRoleSubView(self.xp_svc, interaction.guild, self.admin_id)
            embed = (
                EmbedBuilder.default()
                .author(name="Remover Boost de Cargo")
                .description("Selecione o cargo cujo boost de XP sera removido.")
                .footer("O cargo voltara ao comportamento padrao")
                .build()
            )
            await interaction.response.edit_message(content=None, embed=embed, view=sub)

        elif action == "level_role":
            sub = LevelRoleSubView(self.xp_svc, interaction.guild, self.admin_id)
            embed = sub._build_embed()
            await interaction.response.edit_message(content=None, embed=embed, view=sub)

        elif action == "remove_level_role":
            level_roles = await self.xp_svc.get_level_roles(interaction.guild.id)
            if not level_roles:
                embed = EmbedBuilder.error_user(
                    "Nenhum cargo por nivel configurado."
                ).build()
                await interaction.response.edit_message(embed=embed, view=self)
                return
            sub = RemoveLevelRoleSubView(
                self.xp_svc, interaction.guild, self.admin_id, level_roles
            )
            embed = (
                EmbedBuilder.default()
                .author(name="Remover Cargo por Nivel")
                .description("Selecione o cargo-nivel a ser removido.")
                .footer("O cargo nao sera mais dado automaticamente")
                .build()
            )
            await interaction.response.edit_message(content=None, embed=embed, view=sub)

        elif action == "role_policy":
            config = await self.xp_svc.get_config(interaction.guild.id)
            current_policy = config.get("role_policy", "stack")
            sub = RolePolicySubView(self.xp_svc, interaction.guild, self.admin_id)
            embed = sub._build_embed(current_policy)
            await interaction.response.edit_message(content=None, embed=embed, view=sub)


    # Row 1: Botao de atualizacao
    @discord.ui.button(
        label="Atualizar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_REFRESH, row=1
    )
    async def refresh_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = await _build_xp_dashboard(interaction.guild, self.xp_svc)
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


# ── Cog ───────────────────────────────────────────────────────


class XPConfigCog(commands.Cog):
    """Painel de configuração de XP para administradores."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="xpconfig", description="Painel de configuração de XP do servidor"
    )
    @commands.has_permissions(administrator=True)
    async def xpconfig_cmd(self, ctx: commands.Context) -> None:
        xp_svc = self.bot.xp_config_service
        view = XPConfigPanel(xp_svc, ctx.guild, ctx.author.id)
        embed = await _build_xp_dashboard(ctx.guild, xp_svc)
        await ctx.send(embed=embed, view=view)

    @discord.app_commands.command(
        name="xp-anuncio", description="Configura onde os anúncios de level up aparecerão"
    )
    @discord.app_commands.describe(
        modo="O modo de anúncio (Atual, Específico ou Desativado)",
        canal="[Opcional] O canal específico para enviar (só necessário se modo for Específico)",
    )
    @discord.app_commands.choices(
        modo=[
            discord.app_commands.Choice(name="Atual (onde upou)", value="current"),
            discord.app_commands.Choice(name="Canal Específico", value="specific"),
            discord.app_commands.Choice(name="Nenhum (Desativado)", value="disabled"),
        ]
    )
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def xp_anuncio_cmd(
        self,
        interaction: discord.Interaction,
        modo: discord.app_commands.Choice[str],
        canal: discord.TextChannel | None = None,
    ) -> None:
        if modo.value == "specific" and not canal:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("Você precisa especificar um canal para esse modo!").build()
            )
            return

        xp_svc = self.bot.xp_config_service
        channel_id = canal.id if canal else None

        await xp_svc.update_config(
            interaction.guild.id,
            changed_by=interaction.user.id,
            level_up_mode=modo.value,
            level_up_channel_id=channel_id,
        )

        embed = (
            EmbedBuilder.success("Preferências de Level Up Salvas!")
            .description(
                f"**O novo modo é:** {modo.name}\n"
                f"**Canal:** {canal.mention if canal and modo.value == 'specific' else 'N/A'}"
            )
            .build()
        )
        await interaction.response.send_message(embed=embed)


class RolePolicySubView(discord.ui.View):
    """Sub-painel para alternar a política de cargos por nível (stack vs replace)."""

    def __init__(self, xp_svc: XPConfigService, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=180)
        self.xp_svc = xp_svc
        self.guild = guild
        self.admin_id = admin_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    def _build_embed(self, current_policy: str) -> discord.Embed:
        policy_name = "Acumular (Stack)" if current_policy == "stack" else "Substituir (Replace)"
        return (
            EmbedBuilder.default()
            .author(name="Política de Cargos por Nível")
            .description(
                f"Defina como os cargos por nível serão gerenciados ao subir de nível.\n\n"
                f"• **Acumular (Stack):** O membro mantém todos os cargos de nível já conquistados.\n"
                f"• **Substituir (Replace):** O membro fica apenas com o cargo do maior nível atingido (os anteriores são removidos).\n\n"
                f"Configuração atual: **{policy_name}**"
            )
            .footer("Escolha uma das opções abaixo")
            .build()
        )

    @discord.ui.button(
        label="Acumular (Stack)", style=discord.ButtonStyle.primary, emoji="📚", row=0
    )
    async def btn_stack(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.xp_svc.update_config(self.guild.id, changed_by=interaction.user.id, role_policy="stack")
        main_view = XPConfigPanel(self.xp_svc, self.guild, self.admin_id)
        embed = await _build_xp_dashboard(self.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} Política alterada para **Acumular (Stack)**",
            embed=embed,
            view=main_view,
        )

    @discord.ui.button(
        label="Substituir (Replace)", style=discord.ButtonStyle.primary, emoji="🔄", row=0
    )
    async def btn_replace(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.xp_svc.update_config(self.guild.id, changed_by=interaction.user.id, role_policy="replace")
        main_view = XPConfigPanel(self.xp_svc, self.guild, self.admin_id)
        embed = await _build_xp_dashboard(self.guild, self.xp_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} Política alterada para **Substituir (Replace)**",
            embed=embed,
            view=main_view,
        )

    @discord.ui.button(
        label="Voltar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_BACK, row=1
    )
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        main_view = XPConfigPanel(self.xp_svc, self.guild, self.admin_id)
        embed = await _build_xp_dashboard(self.guild, self.xp_svc)
        await interaction.response.edit_message(content=None, embed=embed, view=main_view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(XPConfigCog(bot))
