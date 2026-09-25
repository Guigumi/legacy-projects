from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotEmojis
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from features.admin.services.automod_service import ViolationResult

logger = logging.getLogger(__name__)

# ── Mapeamento de tipo de violação → descrição legível ──────────────────────────

_VTYPE_LABEL: dict[str, str] = {
    "invite_link":  "link de convite de servidor",
    "link":         "link externo",
    "blocked_word": "palavra proibida",
    "mentions":     "excesso de menções",
    "caps":         "abuso de letras maiúsculas",
    "repeat":       "flood de caracteres repetidos",
    "spam":         "envio em massa de mensagens",
}

_PRESET_LABELS = {
    "alto":  "Alto — 3 warns, todos os filtros ativos",
    "medio": "Médio — 5 warns, filtros tranquilos",
    "baixo": "Baixo — 3 warns, completo p/ novos / tranquilo p/ antigos",
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _format_ids(raw: str, kind: str) -> str:
    ids = [x.strip() for x in raw.split(",") if x.strip().isdigit()]
    if not ids:
        return "Nenhum"
    if kind == "channel":
        return " ".join(f"<#{i}>" for i in ids)
    return " ".join(f"<@&{i}>" for i in ids)


def _status_line(val: int | None) -> str:
    return f"{BotEmojis.STATUS_ENABLED} Ativo" if val else f"{BotEmojis.STATUS_DISABLED} Desativado"


# ── Modais ───────────────────────────────────────────────────────────────────


class AutoModFiltersModal(discord.ui.Modal, title="Filtros do AutoMod"):
    bloquear_convites = discord.ui.TextInput(
        label="Bloquear convites? (sim/não)",
        placeholder="sim",
        max_length=3,
        required=False,
    )
    bloquear_links = discord.ui.TextInput(
        label="Bloquear links externos? (sim/não)",
        placeholder="não",
        max_length=3,
        required=False,
    )
    limite_mencoes = discord.ui.TextInput(
        label="Limite de menções por mensagem (1–50)",
        placeholder="5",
        max_length=2,
        required=False,
    )

    def __init__(self, parent_view: "AutoModView", config: dict) -> None:
        super().__init__()
        self.parent_view = parent_view
        invites = config.get("invites_blocked", 0)
        links = config.get("block_links", 0)
        mentions = config.get("max_mentions", 5)
        self.bloquear_convites.default = "sim" if invites else "não"
        self.bloquear_links.default = "sim" if links else "não"
        self.limite_mencoes.default = str(mentions)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        svc = self.parent_view.service
        existing = await svc.get_config(interaction.guild_id)
        data = svc.build_default_config(existing)

        conv = self.bloquear_convites.value.strip().lower()
        if conv in ("sim", "s", "yes", "y", "1"):
            data["invites_blocked"] = 1
        elif conv in ("não", "nao", "n", "no", "0"):
            data["invites_blocked"] = 0

        links_v = self.bloquear_links.value.strip().lower()
        if links_v in ("sim", "s", "yes", "y", "1"):
            data["block_links"] = 1
        elif links_v in ("não", "nao", "n", "no", "0"):
            data["block_links"] = 0

        try:
            ment = int(self.limite_mencoes.value.strip())
            if 1 <= ment <= 50:
                data["max_mentions"] = ment
        except (ValueError, AttributeError):
            pass

        await svc.save_config(interaction.guild_id, data)
        await self.parent_view.refresh(interaction, success="Filtros atualizados!")


class AutoModWordsModal(discord.ui.Modal, title="Palavras Bloqueadas"):
    palavras = discord.ui.TextInput(
        label="Palavras (separadas por vírgula)",
        placeholder="spam, palavrão, proibido",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, parent_view: "AutoModView", config: dict) -> None:
        super().__init__()
        self.parent_view = parent_view
        self.palavras.default = config.get("blocked_words", "")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        svc = self.parent_view.service
        existing = await svc.get_config(interaction.guild_id)
        data = svc.build_default_config(existing)
        data["blocked_words"] = ",".join(
            w.strip() for w in self.palavras.value.split(",") if w.strip()
        )
        await svc.save_config(interaction.guild_id, data)
        await self.parent_view.refresh(interaction, success="Lista de palavras atualizada!")


class AutoModIgnoreModal(discord.ui.Modal, title="Canais e Cargos Ignorados"):
    canal_id = discord.ui.TextInput(
        label="ID do canal para toggle na whitelist",
        placeholder="Deixe vazio para não alterar",
        required=False,
        max_length=20,
    )
    cargo_id = discord.ui.TextInput(
        label="ID do cargo para toggle na whitelist",
        placeholder="Deixe vazio para não alterar",
        required=False,
        max_length=20,
    )
    canal_log_id = discord.ui.TextInput(
        label="ID do canal de log do AutoMod",
        placeholder="Deixe vazio para não alterar",
        required=False,
        max_length=20,
    )

    def __init__(self, parent_view: "AutoModView", config: dict) -> None:
        super().__init__()
        self.parent_view = parent_view
        log_id = config.get("log_channel_id")
        self.canal_log_id.default = str(log_id) if log_id else ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        svc = self.parent_view.service
        existing = await svc.get_config(interaction.guild_id)
        data = svc.build_default_config(existing)
        changed = []

        if self.canal_id.value.strip():
            try:
                cid = int(self.canal_id.value.strip())
                data["ignored_channels"] = svc.toggle_id(data["ignored_channels"], cid)
                changed.append("canal")
            except ValueError:
                pass

        if self.cargo_id.value.strip():
            try:
                rid = int(self.cargo_id.value.strip())
                data["ignored_roles"] = svc.toggle_id(data["ignored_roles"], rid)
                changed.append("cargo")
            except ValueError:
                pass

        if self.canal_log_id.value.strip():
            try:
                data["log_channel_id"] = int(self.canal_log_id.value.strip())
                changed.append("canal de log")
            except ValueError:
                pass

        await svc.save_config(interaction.guild_id, data)
        msg = f"Whitelist atualizada ({', '.join(changed)})!" if changed else "Nenhuma alteração feita."
        await self.parent_view.refresh(interaction, success=msg)


# ── Select de Preset ─────────────────────────────────────────────────────────


class PresetSelect(discord.ui.Select):
    """Dropdown para selecionar preset do AutoMod."""

    def __init__(self, parent_view: "AutoModView") -> None:
        self.parent_view = parent_view
        super().__init__(
            placeholder="Selecione um preset...",
            options=[
                discord.SelectOption(
                    label="Alto",
                    value="alto",
                    description="3 warns, todos os filtros ativos, timeout geral",
                    emoji="🔴",
                ),
                discord.SelectOption(
                    label="Médio",
                    value="medio",
                    description="5 warns, filtros tranquilos, warn_delete",
                    emoji="🟡",
                ),
                discord.SelectOption(
                    label="Baixo",
                    value="baixo",
                    description="3 warns, completo p/ novos, tranquilo p/ antigos",
                    emoji="🟢",
                ),
            ],
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        preset = self.values[0]
        svc = self.parent_view.service
        existing = await svc.get_config(interaction.guild_id)
        data = svc.build_default_config(existing)

        data["invites_blocked"] = 1
        data["max_mentions"] = 5
        data["preset"] = preset

        if preset == "alto":
            data["block_links"] = 1
            data["max_warnings"] = 3
            data["punishment"] = "timeout"
            data["target_group"] = "all"
            msg = "**Preset Alto** aplicado — todos os filtros ativos, 3 warns."
        elif preset == "medio":
            data["block_links"] = 0
            data["max_warnings"] = 5
            data["punishment"] = "warn_delete"
            data["target_group"] = "all"
            msg = "**Preset Médio** aplicado — filtros tranquilos, 5 warns."
        else:
            data["block_links"] = 1
            data["max_warnings"] = 3
            data["punishment"] = "warn_delete"
            data["target_group"] = "recent"
            msg = "**Preset Baixo** aplicado — completo para novos, tranquilo para antigos."

        await svc.save_config(interaction.guild_id, data)
        # Remove o select de preset do painel após aplicar
        self.parent_view.remove_item(self)
        await self.parent_view.refresh(interaction, success=msg)


# ── View principal ────────────────────────────────────────────────────────────


class AutoModView(discord.ui.View):
    """Painel interativo de configuração do AutoMod."""

    def __init__(self, service, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=300)
        self.service = service
        self.guild = guild
        self.admin_id = admin_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("Apenas quem usou o comando pode interagir.").build(),
                ephemeral=True,
            )
            return False
        return True

    async def _build_embed(self) -> discord.Embed:
        config = await self.service.get_config(self.guild.id)
        if not config:
            return (
                EmbedBuilder.default("AutoMod — Configuração")
                .description(
                    "O AutoMod ainda não foi configurado neste servidor.\n\n"
                    "Use **Preset** para aplicar uma configuração rápida, "
                    "ou **Filtros** para ajustar manualmente."
                )
                .build()
            )

        words_raw = config.get("blocked_words", "")
        words_fmt = (
            ", ".join(f"`{w.strip()}`" for w in words_raw.split(",") if w.strip())
            or "Nenhuma"
        )
        log_ch_id = config.get("log_channel_id")
        log_ch = f"<#{log_ch_id}>" if log_ch_id else "Não definido"
        preset_name = config.get("preset", "alto").upper()
        max_warns = config.get("max_warnings", 3)

        return (
            EmbedBuilder.default("AutoMod — Configuração")
            .description(
                f"**Preset Ativo:** `{preset_name}`\n"
                f"**Limite de Warns:** **{max_warns}** (duração 1 semana)\n"
                f"**Filtro de Convites:** {_status_line(config.get('invites_blocked'))}\n"
                f"**Filtro de Links:** {_status_line(config.get('block_links'))}\n"
                f"**Flood de Menções:** máx. **{config.get('max_mentions', 5)}** por mensagem\n"
                f"**Palavras Bloqueadas:** {words_fmt}\n"
                f"**Canal de Log:** {log_ch}\n"
                f"**Canais Ignorados:** {_format_ids(config.get('ignored_channels', ''), 'channel')}\n"
                f"**Cargos Ignorados:** {_format_ids(config.get('ignored_roles', ''), 'role')}"
            )
            .footer("Use o menu abaixo para configurar")
            .build()
        )

    async def refresh(
        self, interaction: discord.Interaction, success: str | None = None
    ) -> None:
        embed = await self._build_embed()
        content = f"{BotEmojis.COMMON_SPARKLES} {success}" if success else None
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    @discord.ui.select(
        placeholder="O que deseja configurar?",
        options=[
            discord.SelectOption(
                label="Atualizar Status",
                value="status",
                emoji=BotEmojis.COMMON_LIST,
                description="Recarrega o painel com as configurações atuais",
            ),
            discord.SelectOption(
                label="Preset",
                value="preset",
                emoji=BotEmojis.COMMON_RAY,
                description="Aplicar um perfil de segurança pré-configurado",
            ),
            discord.SelectOption(
                label="Filtros",
                value="filters",
                emoji=BotEmojis.COMMON_ADMIN,
                description="Configurar convites, links e limite de menções",
            ),
            discord.SelectOption(
                label="Palavras Bloqueadas",
                value="words",
                emoji=BotEmojis.COMMON_TEXTS,
                description="Editar a lista de palavras proibidas",
            ),
            discord.SelectOption(
                label="Whitelist / Canal de Log",
                value="ignore",
                emoji=BotEmojis.COMMON_FOLDER,
                description="Canais/cargos ignorados e canal de log",
            ),
        ],
        row=0,
    )
    async def action_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        action = select.values[0]
        config = await self.service.get_config(interaction.guild_id) or {}

        if action == "status":
            await self.refresh(interaction)

        elif action == "preset":
            # Injeta o sub-select de preset na view
            preset_select = PresetSelect(self)
            self.add_item(preset_select)
            await self.refresh(interaction, success="Selecione o preset no menu abaixo:")

        elif action == "filters":
            await interaction.response.send_modal(AutoModFiltersModal(self, config))

        elif action == "words":
            await interaction.response.send_modal(AutoModWordsModal(self, config))

        elif action == "ignore":
            await interaction.response.send_modal(AutoModIgnoreModal(self, config))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


# ── Cog ──────────────────────────────────────────────────────────────────────


class AutoModCog(commands.Cog, name="AutoMod"):
    """Filtros automáticos de segurança e moderação do chat."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service = bot.container.automod_service

    # ── Comando único ────────────────────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(
        name="automod",
        description="Painel de configuração do AutoMod (filtros automáticos do servidor).",
    )
    async def automod_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        view = AutoModView(self.service, interaction.guild, interaction.user.id)
        embed = await view._build_embed()
        msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = msg

    # ── Listeners de Mensagens ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        await self._check_message(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not after.guild or after.author.bot:
            return
        await self._check_message(after)

    async def _check_message(self, message: discord.Message) -> None:
        """Verifica uma mensagem contra todos os filtros do AutoMod."""
        if not isinstance(message.author, discord.Member):
            return

        if (
            message.author.guild_permissions.manage_messages
            or message.author.guild_permissions.administrator
        ):
            return

        config = await self.service.get_config(message.guild.id)
        if not config:
            return

        if self.service.is_ignored_channel(config, message.channel.id):
            return
        member_role_ids = [r.id for r in message.author.roles]
        if self.service.is_ignored_role(config, member_role_ids):
            return

        is_recent_member = False
        joined = message.author.joined_at
        if joined:
            from config.settings import now_brt
            days_in_server = (now_brt() - joined).days
            if days_in_server < 7:
                is_recent_member = True

        mention_count = len(message.mentions) + len(message.role_mentions)
        result = await self.service.analyze_message(
            message.guild.id,
            message.author.id,
            message.content,
            mention_count,
            is_recent_member=is_recent_member,
        )

        if result.violated:
            await self._apply_moderation(message, result, config)

    async def _apply_moderation(
        self,
        message: discord.Message,
        result: ViolationResult,
        config: dict,
    ) -> None:
        """Exclui a mensagem, emite warn e alerta o usuário e o canal de log."""
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        label = _VTYPE_LABEL.get(result.vtype or "", result.vtype or "violação")
        if result.vtype == "blocked_word" and result.detail:
            label = f"palavra proibida (`{result.detail}`)"

        total_warns = await self.bot.user_service.add_warning(
            message.guild.id, message.author.id, reason=label
        )

        is_recent = False
        joined = message.author.joined_at
        if joined:
            from config.settings import now_brt
            days_in_server = (now_brt() - joined).days
            if days_in_server < 7:
                is_recent = True

        timeout_msg = ""
        punishment_taken = "Aviso (Warn)"

        import datetime
        if is_recent:
            try:
                await message.author.timeout(datetime.timedelta(hours=1), reason="AutoMod - Membro recente")
                timeout_msg = "\n**Punição:** Timeout de 1 hora (Membro recente)."
                punishment_taken = "Timeout 1h (Membro recente)"
            except discord.Forbidden:
                punishment_taken = "Aviso (Falha ao aplicar Timeout)"
        else:
            max_warns = config.get("max_warnings", 3)
            if total_warns >= max_warns:
                try:
                    await message.author.timeout(
                        datetime.timedelta(hours=1),
                        reason=f"AutoMod - Limite de {max_warns} warns atingido",
                    )
                    timeout_msg = f"\n**Punição:** Timeout de 1 hora (Atingiu o limite de {max_warns} warns)."
                    punishment_taken = f"Timeout 1h (Limite de {max_warns} warns)"
                except discord.Forbidden:
                    punishment_taken = f"Aviso (Falha ao aplicar Timeout por limite de {max_warns} warns)"

        embed_chat = (
            EmbedBuilder.error_user("Mensagem removida pelo AutoMod!")
            .description(
                f"{message.author.mention}, sua mensagem foi removida por **{label}**.\n"
                f"Você possui agora **{total_warns}** aviso(s).{timeout_msg}"
            )
            .build()
        )
        try:
            alert = await message.channel.send(embed=embed_chat)

            async def delete_alert():
                await asyncio.sleep(10)
                try:
                    await alert.delete()
                except Exception:
                    pass

            self.bot.loop.create_task(delete_alert())
        except Exception:
            pass

        log_channel_id = config.get("log_channel_id")
        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)
            if not log_channel and isinstance(log_channel_id, int):
                try:
                    log_channel = await self.bot.fetch_channel(log_channel_id)
                except Exception:
                    log_channel = None

            if log_channel and isinstance(log_channel, discord.TextChannel):
                content_preview = (message.content or "")[:300]
                if len(message.content or "") > 300:
                    content_preview += "..."

                embed_log = (
                    EmbedBuilder.error_user("AutoMod — Ação Tomada")
                    .description(
                        f"**Usuário:** {message.author.mention} (`{message.author.id}`)\n"
                        f"**Canal:** {message.channel.mention}\n"
                        f"**Regra violada:** {label}\n"
                        f"**Warns totais:** {total_warns}\n"
                        f"**Punição:** {punishment_taken}\n"
                        f"**Conteúdo:**\n```{content_preview}```"
                    )
                    .build()
                )
                try:
                    await log_channel.send(embed=embed_log)
                except discord.Forbidden:
                    logger.warning(
                        "AutoMod: sem permissão para enviar no canal de log %s",
                        log_channel_id,
                    )


async def setup(bot: LunaBot) -> None:
    await bot.add_cog(AutoModCog(bot))
