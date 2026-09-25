"""
Cog de configuração — painel centralizado do servidor.
Comando: !config ou /config

Fluxo principal:
- Botões rápidos para ativar/desativar XP, Logs e Economia.
- Botões para abrir configuração detalhada de XP, Logs e Economia.
- Ajustes gerais (prefixo e features adicionais).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from features.community.cogs.xpconfig import XPConfigPanel, _build_xp_dashboard
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from core.enums import Feature, LOG_CATEGORY_META, LogCategory
from features.community.services import GuildService
from config.settings import BotEmojis

# ── Metadados de Features ─────────────────────────────────────

_FEATURE_INFO: dict[Feature, tuple[str, str]] = {
    Feature.TRACKING: (BotEmojis.COMMON_CHART, "Rastreia mensagens enviadas e tempo em call"),
    Feature.LEVELING: (BotEmojis.COMMON_LVL_UP, "Sistema de XP e níveis por atividade"),
    Feature.LOGGING: (BotEmojis.COMMON_LIST, "Envia logs de ações no canal configurado"),
    Feature.MODERATION: (BotEmojis.COMMON_ADMIN, "Ferramentas de moderação do servidor"),
    Feature.MINECRAFT: (BotEmojis.MINECRAFT, "Permite uso dos comandos de Minecraft neste servidor"),
}


# ── Helpers ───────────────────────────────────────────────────


async def _build_dashboard(guild: discord.Guild, guild_svc: GuildService) -> discord.Embed:
    """Monta o embed do painel principal com todas as configs."""
    config = await guild_svc.get_config(guild.id)
    disabled_log_cats = set(await guild_svc.get_disabled_log_categories(guild.id))

    prefix = config.get("prefix", "!") if config else "!"

    # Log channel
    log_id = config.get("log_channel") if config else None
    log_ch = guild.get_channel(log_id) if log_id else None
    log_str = log_ch.mention if log_ch else "`Não configurado`"

    # Features
    feat_lines: list[str] = []
    for feat in Feature:
        if feat not in _FEATURE_INFO:
            continue
        emoji, desc = _FEATURE_INFO[feat]
        on = await guild_svc.is_feature_enabled(guild.id, feat)
        toggle = BotEmojis.BOX_CHECK if on else BotEmojis.BOX_OFF
        label = feat.value.replace("_", " ").title()
        feat_lines.append(f"{toggle} {emoji} **{label}** — {desc}")

    log_total = len(LogCategory)
    log_enabled = log_total - len(disabled_log_cats)
    feat_text = "\n".join(feat_lines)

    return (
        EmbedBuilder.default()
        .author(
            name=f"Painel — {guild.name}",
            icon_url=guild.icon.url if guild.icon else None,
        )
        .description(
            f"**Prefixo:** `{prefix}`\n"
            f"**Canal de Logs:** {log_str}\n"
            f"**Categorias de Log:** **{log_enabled}/{log_total}** ativas\n"
            f"\n{'─' * 30}\n\n"
            f"{feat_text}"
        )
        .footer("Use o dropdown de ações para ativar/desativar e configurar módulos")
        .timestamp()
        .build()
    )


async def _build_main_panel(
    bot: LunaBot, guild_svc: GuildService, guild: discord.Guild, admin_id: int
) -> tuple[discord.Embed, "ConfigPanel"]:
    """Cria embed + view do painel principal."""
    view = ConfigPanel(bot, guild_svc, guild, admin_id)
    embed = await _build_dashboard(guild, guild_svc)
    return embed, view


# ── Modais ────────────────────────────────────────────────────


class PrefixModal(discord.ui.Modal, title="Alterar Prefixo"):
    prefix_input = discord.ui.TextInput(
        label="Novo prefixo",
        placeholder="Ex: ! ou t! ou >>",
        min_length=1,
        max_length=5,
        required=True,
    )

    def __init__(self, parent_view: "ConfigPanel") -> None:
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        new_prefix = self.prefix_input.value.strip()
        if " " in new_prefix:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("O prefixo não pode conter espaços.").build(),
                ephemeral=True,
            )
            return

        # Bloquear prefixos que conflitam com Discord ou podem causar abuso
        _BLOCKED_PREFIXES = {"@", "/", "#", "<", "@everyone", "@here"}
        if new_prefix in _BLOCKED_PREFIXES or new_prefix.startswith(("@", "<@", "<#")):
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user(
                    f"O prefixo `{new_prefix}` não é permitido pois conflita com a sintaxe do Discord.\n"
                    "Evite: `@`, `/`, `#`, `<`, menções e `@everyone`."
                ).build(),
                ephemeral=True,
            )
            return

        guild_svc = self.parent_view.guild_svc
        await guild_svc.update_config(
            interaction.guild.id,
            changed_by=interaction.user.id,
            prefix=new_prefix,
        )
        embed = await _build_dashboard(interaction.guild, guild_svc)
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} Prefixo alterado para `{new_prefix}`",
            embed=embed,
            view=self.parent_view,
        )




# ── Sub-view: Logs ────────────────────────────────────────────


class LogSubView(discord.ui.View):
    """Sub-painel para canal e categorias de logs."""

    def __init__(
        self, bot: LunaBot, guild_svc: GuildService, guild: discord.Guild, admin_id: int
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_svc = guild_svc
        self.guild = guild
        self.admin_id = admin_id
        self.log_channel_id: int | None = None
        self.disabled_cats: set[str] = set()

    async def mount(self) -> None:
        """Carrega estado atual de canal/categorias de log."""
        config = await self.guild_svc.get_config(self.guild.id)
        self.log_channel_id = config.get("log_channel") if config else None
        self.disabled_cats = set(
            await self.guild_svc.get_disabled_log_categories(self.guild.id)
        )
        self._sync_category_select()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    def _sync_category_select(self) -> None:
        for opt in self.category_select.options:
            enabled = opt.value not in self.disabled_cats
            opt.description = (
                f"{BotEmojis.BOX_CHECK} Ativada"
                if enabled
                else f"{BotEmojis.BOX_OFF} Desativada"
            )

    async def _build_embed(self) -> discord.Embed:
        lines: list[str] = []
        for cat in LogCategory:
            emoji, label = LOG_CATEGORY_META[cat]
            enabled = cat.value not in self.disabled_cats
            status = BotEmojis.BOX_CHECK if enabled else BotEmojis.BOX_OFF
            lines.append(f"{status} {emoji} **{label}**")

        channel_info = (
            f"{BotEmojis.COMMON_LIST} Canal de logs: <#{self.log_channel_id}>"
            if self.log_channel_id
            else f"{BotEmojis.BOX_NONE} Nenhum canal de logs definido"
        )

        return (
            EmbedBuilder.default()
            .author(name="Configuração de Logs")
            .description(
                f"{channel_info}\n\n"
                "Escolha exatamente o que vai para o chat de logs:\n"
                "- Defina/remova o canal\n"
                "- Ative/desative categorias específicas\n\n"
                + "\n".join(lines)
            )
            .footer("Use os menus abaixo para ajustar canal e categorias")
            .build()
        )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Selecionar canal de logs...",
        row=0,
    )
    async def channel_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        channel = select.values[0]
        await self.guild_svc.update_config(
            interaction.guild.id,
            changed_by=interaction.user.id,
            log_channel=channel.id,
        )
        self.log_channel_id = channel.id
        embed = await self._build_embed()
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} Canal de logs definido para {channel.mention}",
            embed=embed,
            view=self,
        )

    @discord.ui.select(
        placeholder="Alternar categorias de logs...",
        min_values=1,
        max_values=len(LogCategory),
        options=[
            discord.SelectOption(
                label=LOG_CATEGORY_META[cat][1],
                value=cat.value,
                emoji=LOG_CATEGORY_META[cat][0],
                description="Ativar ou desativar esta categoria",
            )
            for cat in LogCategory
        ],
        row=1,
    )
    async def category_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        selected = select.values

        for cat_value in selected:
            if cat_value in self.disabled_cats:
                await self.guild_svc.toggle_log_category(
                    interaction.guild.id,
                    cat_value,
                    True,
                    interaction.user.id,
                )
                self.disabled_cats.discard(cat_value)
            else:
                await self.guild_svc.toggle_log_category(
                    interaction.guild.id,
                    cat_value,
                    False,
                    interaction.user.id,
                )
                self.disabled_cats.add(cat_value)

        self._sync_category_select()
        embed = await self._build_embed()
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} {len(selected)} categoria(s) de log atualizada(s).",
            embed=embed,
            view=self,
        )

    @discord.ui.button(
        label="Remover Canal",
        style=discord.ButtonStyle.danger,
        emoji=BotEmojis.ACTION_REMOVE,
        row=2,
    )
    async def remove_channel_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.guild_svc.update_config(
            interaction.guild.id,
            changed_by=interaction.user.id,
            log_channel=None,
        )
        self.log_channel_id = None
        embed = await self._build_embed()
        await interaction.response.edit_message(
            content=f"{BotEmojis.COMMON_SPARKLES} Canal de logs removido.",
            embed=embed,
            view=self,
        )

    @discord.ui.button(
        label="Voltar",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.ACTION_BACK,
        row=2,
    )
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed, view = await _build_main_panel(
            self.bot, self.guild_svc, interaction.guild, self.admin_id
        )
        await interaction.response.edit_message(content=None, embed=embed, view=view)


# ── Sub-view: AutoMod Presets ─────────────────────────────────

class AutoModSubView(discord.ui.View):
    """Sub-painel para presets do AutoMod."""

    def __init__(
        self, bot: LunaBot, guild_svc: GuildService, guild: discord.Guild, admin_id: int
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_svc = guild_svc
        self.guild = guild
        self.admin_id = admin_id
        self.automod_svc = bot.container.automod_service

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
            EmbedBuilder.default("Configuração de AutoMod (Presets)")
            .description(
                "Escolha um dos perfis pré-configurados de segurança:\n\n"
                "🛡️ **Alto:** Ativa todos os filtros. Limite de **3 warns** (duração 1 semana).\n"
                "🛡️ **Médio:** Ativa filtros tranquilos (sem CAPS, repetição ou links). Limite de **5 warns** (duração 1 semana).\n"
                "🛡️ **Baixo:** Filtro completo para membros novos (< 7 dias) e tranquilo para antigos. Limite de **3 warns**.\n\n"
                "*Membros recentes (< 7 dias) em qualquer preset tomam timeout automático de 1h.*"
            )
            .footer("Use os botões abaixo para aplicar um preset.")
            .build()
        )

    async def _apply_preset(self, interaction: discord.Interaction, preset: str) -> None:
        existing = await self.automod_svc.get_config(self.guild.id)
        data = self.automod_svc.build_default_config(existing)

        data["invites_blocked"] = 1
        data["max_mentions"] = 5
        data["preset"] = preset

        if preset == "alto":
            data["block_links"] = 1
            data["max_warnings"] = 3
            data["punishment"] = "timeout"
            data["target_group"] = "all"
            msg = "✅ **Preset Alto** aplicado: todos os filtros ativos, limite de 3 warns."
        elif preset == "medio":
            data["block_links"] = 0
            data["max_warnings"] = 5
            data["punishment"] = "warn_delete"
            data["target_group"] = "all"
            msg = "✅ **Preset Médio** aplicado: apenas filtros tranquilos ativos, limite de 5 warns."
        elif preset == "baixo":
            data["block_links"] = 1
            data["max_warnings"] = 3
            data["punishment"] = "warn_delete"
            data["target_group"] = "recent"
            msg = "✅ **Preset Baixo** aplicado: filtros completos para novos, tranquilos para antigos. Limite de 3 warns."

        await self.automod_svc.save_config(self.guild.id, data)
        embed = self._build_embed()
        await interaction.response.edit_message(
            content=msg,
            embed=embed,
            view=self,
        )

    @discord.ui.button(label="Preset Alto", style=discord.ButtonStyle.danger, row=0)
    async def btn_alto(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._apply_preset(interaction, "alto")

    @discord.ui.button(label="Preset Médio", style=discord.ButtonStyle.primary, row=0)
    async def btn_medio(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._apply_preset(interaction, "medio")

    @discord.ui.button(label="Preset Baixo", style=discord.ButtonStyle.success, row=0)
    async def btn_baixo(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._apply_preset(interaction, "baixo")

    @discord.ui.button(
        label="Voltar",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.ACTION_BACK,
        row=1,
    )
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed, view = await _build_main_panel(
            self.bot, self.guild_svc, interaction.guild, self.admin_id
        )
        await interaction.response.edit_message(content=None, embed=embed, view=view)


# ── Painel Principal ──────────────────────────────────────────


class ConfigPanel(discord.ui.View):
    """Painel centralizado de configuração do servidor."""

    def __init__(
        self, bot: LunaBot, guild_svc: GuildService, guild: discord.Guild, admin_id: int
    ) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_svc = guild_svc
        self.guild = guild
        self.admin_id = admin_id
        self.message: discord.Message | None = None

    async def _toggle_feature_and_refresh(
        self,
        interaction: discord.Interaction,
        feature: Feature,
        display_name: str,
    ) -> None:
        is_enabled = await self.guild_svc.is_feature_enabled(interaction.guild.id, feature)
        new_state = not is_enabled
        await self.guild_svc.toggle_feature(
            interaction.guild.id,
            feature,
            new_state,
            interaction.user.id,
        )

        state_text = "ativada" if new_state else "desativada"
        emoji = BotEmojis.BOX_CHECK if new_state else BotEmojis.BOX_OFF
        embed = await _build_dashboard(interaction.guild, self.guild_svc)
        await interaction.response.edit_message(
            content=f"{emoji} **{display_name}** foi **{state_text}**.",
            embed=embed,
            view=self,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    # ── Row 0: Ações gerais ─────────────────────────────────

    @discord.ui.button(
        label="Prefixo",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.COMMON_NOTE,
        row=0,
    )
    async def prefix_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(PrefixModal(self))

    @discord.ui.button(
        label="Atualizar",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.ACTION_REFRESH,
        row=0,
    )
    async def refresh_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = await _build_dashboard(interaction.guild, self.guild_svc)
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    # ── Row 1: Dropdown de ações ─────────────────────────────

    @discord.ui.select(
        placeholder="Selecionar ação de configuração...",
        options=[
            discord.SelectOption(
                label="Ativar/Desativar XP",
                value="toggle_xp",
                emoji=BotEmojis.COMMON_LVL_UP,
                description="Liga ou desliga o sistema de XP e níveis",
            ),
            discord.SelectOption(
                label="Configurar XP",
                value="config_xp",
                emoji=BotEmojis.COMMON_RAY,
                description="Define quanto e quando usuário ganha XP",
            ),
            discord.SelectOption(
                label="Ativar/Desativar Logs",
                value="toggle_logs",
                emoji=BotEmojis.COMMON_LIST,
                description="Liga ou desliga o módulo de logs",
            ),
            discord.SelectOption(
                label="Configurar Logs",
                value="config_logs",
                emoji=BotEmojis.COMMON_LIST,
                description="Escolhe canal e categorias que entram no log",
            ),
            discord.SelectOption(
                label="Ativar/Desativar Tracking",
                value="toggle_tracking",
                emoji=BotEmojis.COMMON_CHART,
                description="Liga ou desliga o rastreamento de atividade",
            ),
            discord.SelectOption(
                label="Ativar/Desativar Moderação",
                value="toggle_moderation",
                emoji=BotEmojis.COMMON_ADMIN,
                description="Liga ou desliga recursos de moderação",
            ),
            discord.SelectOption(
                label="Configurar AutoMod (Presets)",
                value="config_automod",
                emoji=BotEmojis.COMMON_ADMIN,
                description="Define força e alvo dos filtros de moderação",
            ),

            discord.SelectOption(
                label="[Owner] Minecraft neste servidor",
                value="toggle_minecraft",
                emoji=BotEmojis.MINECRAFT,
                description="Libera comandos de Minecraft (apenas Owner)",
            ),
        ],
        row=1,
    )
    async def module_action_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        action = select.values[0]

        if action == "toggle_xp":
            await self._toggle_feature_and_refresh(
                interaction, Feature.LEVELING, "XP / Níveis"
            )
            return

        if action == "config_xp":
            xp_svc = self.bot.xp_config_service
            view = XPConfigPanel(xp_svc, interaction.guild, self.admin_id)
            embed = await _build_xp_dashboard(interaction.guild, xp_svc)
            await interaction.response.edit_message(content=None, embed=embed, view=view)
            return

        if action == "toggle_logs":
            await self._toggle_feature_and_refresh(interaction, Feature.LOGGING, "Logs")
            return

        if action == "config_logs":
            sub = LogSubView(self.bot, self.guild_svc, interaction.guild, self.admin_id)
            await sub.mount()
            embed = await sub._build_embed()
            await interaction.response.edit_message(content=None, embed=embed, view=sub)
            return


        if action == "toggle_tracking":
            await self._toggle_feature_and_refresh(
                interaction, Feature.TRACKING, "Tracking"
            )
            return

        if action == "toggle_moderation":
            await self._toggle_feature_and_refresh(
                interaction, Feature.MODERATION, "Moderação"
            )
            return

        if action == "config_automod":
            sub = AutoModSubView(self.bot, self.guild_svc, interaction.guild, self.admin_id)
            embed = sub._build_embed()
            await interaction.response.edit_message(content=None, embed=embed, view=sub)
            return



        if action == "toggle_minecraft":
            if not await self.bot.is_owner(interaction.user):
                await interaction.response.send_message(
                    embed=EmbedBuilder.error_user("Apenas o dono do bot pode ativar o Minecraft.").build(),
                    ephemeral=True,
                )
                return
            await self._toggle_feature_and_refresh(
                interaction, Feature.MINECRAFT, "Minecraft"
            )
            return

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


# ── Cog ───────────────────────────────────────────────────────


class ConfigCog(commands.Cog):
    """Painel centralizado de configuração do servidor."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="config", description="Painel de configuração do servidor"
    )
    @commands.has_permissions(administrator=True)
    async def config_cmd(self, ctx: commands.Context) -> None:
        guild_svc = self.bot.guild_service
        embed, view = await _build_main_panel(
            self.bot, guild_svc, ctx.guild, ctx.author.id
        )
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(
        name="prefix", description="Altera o prefixo do bot neste servidor"
    )
    @app_commands.describe(novo_prefixo="O novo prefixo desejado (máx 5 caracteres)")
    @commands.has_permissions(administrator=True)
    async def prefix_cmd(self, ctx: commands.Context, novo_prefixo: str) -> None:
        if len(novo_prefixo) > 5:
            await ctx.send(embed=EmbedBuilder.error_user("O prefixo deve ter no máximo 5 caracteres.").build(), ephemeral=True)
            return
            
        await self.bot.guild_service.update_config(ctx.guild.id, changed_by=ctx.author.id, prefix=novo_prefixo)
        embed = EmbedBuilder.success(f"Prefixo alterado para `{novo_prefixo}`.").build()
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="logs-setup", description="Configura o canal de logs do bot"
    )
    @app_commands.describe(canal="O canal de texto onde os logs serão enviados")
    @commands.has_permissions(administrator=True)
    async def logs_setup_cmd(self, ctx: commands.Context, canal: discord.TextChannel) -> None:
        await self.bot.guild_service.update_config(ctx.guild.id, changed_by=ctx.author.id, log_channel=canal.id)
        embed = EmbedBuilder.success(f"Canal de logs configurado para {canal.mention}.").build()
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigCog(bot))
