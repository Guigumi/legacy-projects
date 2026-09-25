"""
Cog server — exibe informações do servidor.
Admins têm um botão extra para editar configurações rapidamente.
"""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands

from core.utils.embed_builder import EmbedBuilder
from core.utils.dev_edit import inject_dev_edit
from core.enums import Feature
from config.settings import BotEmojis, OWNER_ID

# ── Helpers ───────────────────────────────────────────────────


def _fmt_date(dt: datetime.datetime | None) -> str:
    if not dt:
        return "?"
    ts = int(dt.timestamp())
    return f"<t:{ts}:D> (<t:{ts}:R>)"


def _boost_tier(guild: discord.Guild) -> str:
    tier = guild.premium_tier
    emoji = {
        1: BotEmojis.BOOST_LV1,
        2: BotEmojis.BOOST_LV2,
        3: BotEmojis.BOOST_LV3,
    }.get(tier, BotEmojis.COMMON_BOOST)
    
    label = {0: "Sem boost", 1: "Nível 1", 2: "Nível 2", 3: "Nível 3"}.get(tier, "?")
    return f"{emoji} {label}"


def _verification_level(guild: discord.Guild) -> str:
    levels = {
        discord.VerificationLevel.none: "Nenhuma",
        discord.VerificationLevel.low: "Baixa",
        discord.VerificationLevel.medium: "Média",
        discord.VerificationLevel.high: "Alta",
        discord.VerificationLevel.highest: "Máxima",
    }
    return levels.get(guild.verification_level, "?")


def _feature_label(feat: Feature) -> str:
    labels = {
        Feature.TRACKING: "Tracking",
        Feature.LEVELING: "Leveling",
        Feature.LOGGING: "Logging",
        Feature.MODERATION: "Moderação",
        Feature.MINECRAFT: "Minecraft",
    }
    return labels.get(feat, feat.value.replace("_", " ").title())


def _format_features(disabled: list[str]) -> str:
    disabled_set = set(disabled)
    enabled_features: list[str] = []
    disabled_features: list[str] = []

    for feat in Feature:
        line = (
            f"{BotEmojis.BOX_CHECK if feat.value not in disabled_set else BotEmojis.BOX_OFF} "
            f"{_feature_label(feat)}"
        )
        if feat.value not in disabled_set:
            enabled_features.append(line)
        else:
            disabled_features.append(line)

    sections: list[str] = []
    if enabled_features:
        sections.append(
            f"{BotEmojis.STATUS_ENABLED} Ativas ({len(enabled_features)}/{len(Feature)})"
        )
        sections.extend(enabled_features)

    if disabled_features:
        if sections:
            sections.append("")
        sections.append(
            f"{BotEmojis.STATUS_DISABLED} Desativadas ({len(disabled_features)}/{len(Feature)})"
        )
        sections.extend(disabled_features)

    return "\n".join(sections)


# ── Embed Builder ─────────────────────────────────────────────


async def _build_server_embed(guild: discord.Guild, bot: commands.Bot) -> discord.Embed:
    """Constrói embed com informações do servidor."""

    # Contadores
    total_members = guild.member_count or 0
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    categories = len(guild.categories)
    roles = len(guild.roles) - 1  # Remove @everyone
    emojis = len(guild.emojis)
    boosts = guild.premium_subscription_count or 0

    # Dono
    owner = guild.owner

    # Config do bot
    guild_svc = bot.guild_service
    config = await guild_svc.get_config(guild.id)
    prefix = config.get("prefix", "!") if config else "!"
    disabled = await guild_svc.get_disabled_features(guild.id)

    features_str = _format_features(disabled)

    # Icon
    icon_url = guild.icon.url if guild.icon else None

    embed = (
        EmbedBuilder.default()
        .author(name=guild.name, icon_url=icon_url)
        .description(
            f"**{BotEmojis.COMMON_ID} ID:** `{guild.id}`\n"
            f"**{BotEmojis.COMMON_OWNER} Dono:** {owner.mention if owner else '?'}\n"
            f"**{BotEmojis.COMMON_CALENDAR} Criado em:** {_fmt_date(guild.created_at)}"
        )
        .field(f"{BotEmojis.COMMON_USERS} Membros", f"`{total_members}`", inline=True)
        .field(f"{BotEmojis.COMMON_MESSAGE} Canais de Texto", f"`{text_channels}`", inline=True)
        .field(f"{BotEmojis.COMMON_VOICE} Canais de Voz", f"`{voice_channels}`", inline=True)
        .field(f"{BotEmojis.COMMON_FOLDER} Categorias", f"`{categories}`", inline=True)
        .field(f"{BotEmojis.COMMON_TAG} Cargos", f"`{roles}`", inline=True)
        .field(f"{BotEmojis.COMMON_EMOJI} Emojis", f"`{emojis}`", inline=True)
        .field(f"{BotEmojis.COMMON_BOOST} Boosts", f"`{boosts}` ({_boost_tier(guild)})", inline=True)
        .field(f"{BotEmojis.COMMON_LOCK} Verificação", f"`{_verification_level(guild)}`", inline=True)
        .field(f"{BotEmojis.COMMON_CHANNEL} Prefixo", f"`{prefix}`", inline=True)
        .field(f"{BotEmojis.ACTION_SETTINGS} Features", features_str, inline=False)
        .footer(f"Server Info • {guild.name}")
        .timestamp()
    )

    if icon_url:
        embed.thumbnail(icon_url)

    if guild.banner:
        embed.image(guild.banner.url)

    return embed.build()


# ── Admin Edit Modal ──────────────────────────────────────────


class EditServerModal(discord.ui.Modal, title="Editar Servidor"):
    """Modal para admins editarem configs rápidas."""

    new_prefix = discord.ui.TextInput(
        label="Prefixo",
        placeholder="Ex: ! ou t!",
        max_length=5,
        required=False,
    )

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_svc = self.bot.guild_service
        changes: list[str] = []

        # Prefixo
        new_prefix = self.new_prefix.value.strip()
        if new_prefix:
            await guild_svc.update_config(
                interaction.guild.id,
                changed_by=interaction.user.id,
                prefix=new_prefix,
            )
            changes.append(f"Prefixo → `{new_prefix}`")

        if changes:
            desc = "\n".join(f"{BotEmojis.COMMON_SPARKLES} {c}" for c in changes)
            embed = EmbedBuilder.success(
                f"Configurações atualizadas!\n\n{desc}"
            ).build()
        else:
            embed = EmbedBuilder.alert("Nenhuma alteração feita.").build()

        await interaction.response.send_message(embed=embed)


# ── View ──────────────────────────────────────────────────────


class ServerView(discord.ui.View):
    """View com botão de editar para admins."""

    def __init__(
        self, bot: commands.Bot, author_id: int, *, is_admin: bool = False
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.author_id = author_id

        if not is_admin:
            self.remove_item(self.edit_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    @discord.ui.button(
        label="Editar",
        emoji=BotEmojis.ACTION_EDIT,
        style=discord.ButtonStyle.primary,
    )
    async def edit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = EditServerModal(self.bot)
        await interaction.response.send_modal(modal)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# ── Cog ───────────────────────────────────────────────────────


class ServerCog(commands.Cog):
    """Informações do servidor."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="server",
        aliases=["sv", "serverinfo"],
        description="Mostra informações do servidor",
    )
    async def server(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            embed = EmbedBuilder.error_user(
                "Este comando só pode ser usado em servidores."
            ).build()
            await ctx.send(embed=embed)
            return

        # Verificar se é admin
        is_admin = ctx.author.guild_permissions.administrator

        embed = await _build_server_embed(ctx.guild, self.bot)
        view = ServerView(self.bot, ctx.author.id, is_admin=is_admin)

        # Buscar config para preencher valores do modal
        config = await self.bot.guild_service.get_config(ctx.guild.id)
        prefix = config.get("prefix", "!")
        log_channel_id = config.get("log_channel")
        welcome_channel_id = config.get("welcome_channel")
        tracking = 1 if config.get("tracking_enabled") else 0

        inject_dev_edit(
            view,
            bot=self.bot,
            table="guild_config",
            pk_values={"guild_id": ctx.guild.id},
            fields=[
                {"name": "prefix", "label": "Prefixo", "value": prefix},
                {"name": "log_channel", "label": "Canal de Logs (ID)", "value": log_channel_id or ""},
                {"name": "welcome_channel", "label": "Canal Welcome (ID)", "value": welcome_channel_id or ""},
                {"name": "tracking_enabled", "label": "Tracking (0/1)", "value": tracking},
            ],
            modal_title="Config da Guild",
        )

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerCog(bot))
