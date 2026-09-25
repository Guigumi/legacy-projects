"""
Lógica de negócio para logging — formata embeds e envia para o canal configurado.

Inclui sistema de agrupamento de eventos de voz por sessão de usuário,
editando um único embed dinâmico em vez de enviar múltiplas mensagens.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import discord

from core.utils.embed_builder import EmbedBuilder
from core.events import BotEvent
from core.enums import LogCategory
from features.community.services import GuildService
from config.settings import BotEmojis

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────

_MAX_CONTENT = 1024  # Limite de chars para conteúdo de mensagem no embed

# Mapeamento evento interno → (emoji, título)
_EVENT_META: dict[BotEvent, tuple[str, str]] = {
    BotEvent.CONFIG_CHANGED: (BotEmojis.ACTION_SETTINGS, "Configuração alterada"),
    BotEvent.FEATURE_TOGGLED: (BotEmojis.ACTION_REFRESH, "Feature alternada"),
    BotEvent.USER_LEVELED_UP: (BotEmojis.COMMON_LVL_UP, "Level up!"),
    BotEvent.WARNING_ISSUED: (BotEmojis.STATUS_WARNING, "Aviso aplicado"),
    BotEvent.AUTOROLE_GIVEN: (BotEmojis.COMMON_TAG, "Cargo automático dado"),
    BotEvent.AUTOROLE_CONFIG: (BotEmojis.COMMON_TAG, "AutoRole configurado"),
    BotEvent.NOTIFICATION_CREATED: (BotEmojis.COMMON_LIST, "Notificação criada"),
}

# Eventos internos que NÃO vão para o canal de logs (spam)
_SILENT_EVENTS: set[BotEvent] = {
    BotEvent.MESSAGE_TRACKED,
    BotEvent.VOICE_TRACKED,
}

# Mapeamento tipo de canal → label
_CHANNEL_TYPES: dict[type, str] = {
    discord.TextChannel: f"{BotEmojis.COMMON_MESSAGE} texto",
    discord.VoiceChannel: f"{BotEmojis.COMMON_VOICE} voz",
    discord.CategoryChannel: f"{BotEmojis.COMMON_FOLDER} categoria",
    discord.StageChannel: f"{BotEmojis.MIC_ON} palco",
    discord.ForumChannel: f"{BotEmojis.COMMON_LIST} fórum",
}

# Temporizadores da sessão de voz
_SESSION_UPDATE_DEBOUNCE = 2  # Segundos para agrupar ações rápidas em uma única edição
_SESSION_REFRESH_INTERVAL = (
    300  # Atualiza o embed periodicamente durante sessões longas
)
_SESSION_IDLE_TIMEOUT = (
    6 * 60 * 60
)  # Fecha a sessão se não houver atividade por muito tempo


# ── Helpers ───────────────────────────────────────────────────


def _truncate(text: str, limit: int = _MAX_CONTENT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _channel_mention(channel: discord.abc.Messageable) -> str:
    """Retorna a menção do canal de forma segura (DMChannel/GroupChannel não têm .mention)."""
    if hasattr(channel, "mention"):
        return channel.mention  # type: ignore[union-attr]
    return f"`#{channel}`"


def _format_actor(actor: discord.abc.User | None) -> str:
    """Formata executor da ação para texto de log."""
    if actor is None:
        return "*Não identificado*"
    return f"{actor.mention} (`{actor}`)"


def _format_event_data(data: dict[str, Any], guild: discord.Guild | None) -> str:
    """Converte o dict de dados do evento interno em linhas legíveis."""
    lines: list[str] = []
    for key, value in data.items():
        if key in ("user_id", "changed_by", "toggled_by") and guild:
            member = guild.get_member(value)
            display = member.mention if member else f"`{value}`"
            label = {"user_id": "Usuário", "changed_by": "Por", "toggled_by": "Por"}[
                key
            ]
            lines.append(f"**{label}:** {display}")
        elif key == "feature":
            lines.append(f"**Feature:** `{value}`")
        elif key == "enabled":
            state = (BotEmojis.BOX_CHECK + " Ativada") if value else (BotEmojis.BOX_OFF + " Desativada")
            lines.append(f"**Estado:** {state}")
        elif key == "fields":
            lines.append(f"**Campos:** {', '.join(f'`{f}`' for f in value)}")
        elif key == "new_level":
            lines.append(f"**Novo nível:** {value}")
        elif key == "old_level":
            continue  # Não exibir old_level no log
        elif key == "role_id" and guild:
            role = guild.get_role(value)
            display = role.mention if role else f"`{value}`"
            lines.append(f"**Cargo:** {display}")
        elif key == "mode":
            lines.append(f"**Modo:** `{value}`")
        else:
            lines.append(f"**{key}:** `{value}`")
    return "\n".join(lines) if lines else "*Sem detalhes*"


# ── Sessão de Voz ─────────────────────────────────────────────


@dataclass
class VoiceAction:
    """Uma ação individual dentro de uma sessão de voz."""

    timestamp: float
    emoji: str
    text: str


@dataclass
class VoiceSession:
    """Agrupa todas as ações de voz de um membro em um único embed."""

    member_id: int
    member_display: str
    member_avatar_url: str
    guild_id: int
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    current_channel: str | None = None
    actions: list[VoiceAction] = field(default_factory=list)
    message: discord.Message | None = None
    finalized: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def add_action(self, emoji: str, text: str) -> None:
        self.actions.append(
            VoiceAction(
                timestamp=time.time(),
                emoji=emoji,
                text=text,
            )
        )

    def _summarize_actions(self) -> str:
        """Gera resumo agrupado das ações com contagem."""
        counts: dict[str, int] = {}
        order: list[str] = []
        for action in self.actions:
            key = f"{action.emoji} {action.text}"
            if key not in counts:
                counts[key] = 0
                order.append(key)
            counts[key] += 1

        lines: list[str] = []
        for key in order:
            count = counts[key]
            if count > 1:
                lines.append(f"▸ {key} **×{count}**")
            else:
                lines.append(f"▸ {key}")
        return "\n".join(lines) if lines else "*Nenhuma ação registrada*"

    def _build_timeline(self) -> str:
        """Gera timeline cronológica das ações."""
        lines: list[str] = []
        for action in self.actions:
            ts = int(action.timestamp)
            lines.append(f"<t:{ts}:T> {action.emoji} {action.text}")
        return "\n".join(lines) if lines else ""

    def build_embed(self) -> discord.Embed:
        """Constrói o embed atual da sessão."""
        start_ts = int(self.start_time)

        if self.finalized and self.end_time:
            end_ts = int(self.end_time)
            duration_secs = int(self.end_time - self.start_time)
            mins, secs = divmod(duration_secs, 60)
            hours, mins = divmod(mins, 60)
            if hours > 0:
                duration_str = f"{hours}h {mins}m {secs}s"
            elif mins > 0:
                duration_str = f"{mins}m {secs}s"
            else:
                duration_str = f"{secs}s"

            time_line = f"{BotEmojis.COMMON_WATCH} <t:{start_ts}:T> — <t:{end_ts}:T>  (`{duration_str}`)"
            color = discord.Color(0x747F8D)  # Cinza — sessão encerrada
            status_icon = BotEmojis.STATUS_STOPPED
            status_text = "Sessão encerrada"
        else:
            time_line = f"{BotEmojis.COMMON_WATCH} <t:{start_ts}:T> — **agora**"
            color = discord.Color(0x43B581)  # Verde — em call
            status_icon = BotEmojis.STATUS_LIVE
            status_text = "Na call"

        channel_line = f"{BotEmojis.COMMON_CHANNEL} {self.current_channel}" if self.current_channel else ""

        # Resumo compacto
        summary = self._summarize_actions()

        # Timeline detalhada (últimas 15 entradas para não estourar o embed)
        timeline_entries = self.actions[-15:]
        timeline_lines: list[str] = []
        for action in timeline_entries:
            ts = int(action.timestamp)
            timeline_lines.append(f"<t:{ts}:T> {action.emoji} {action.text}")

        if len(self.actions) > 15:
            hidden = len(self.actions) - 15
            timeline_lines.insert(0, f"*... +{hidden} ações anteriores*")

        timeline = "\n".join(timeline_lines)

        desc_parts = [
            f"{status_icon} **{status_text}**",
            time_line,
        ]
        if channel_line:
            desc_parts.append(channel_line)

        desc_parts.append("")  # linha em branco
        desc_parts.append(f"**──── Resumo ────**\n{summary}")

        if timeline:
            desc_parts.append(f"\n**──── Histórico ────**\n{timeline}")

        description = "\n".join(desc_parts)

        # Truncar se necessário (limite embed description = 4096)
        if len(description) > 4000:
            description = description[:3997] + "..."

        embed = (
            EmbedBuilder.default()
            .color(color)
            .author(
                name=self.member_display,
                icon_url=self.member_avatar_url,
            )
            .description(description)
            .footer(f"ID: {self.member_id}")
            .timestamp()
            .build()
        )
        return embed


class LoggingService:
    """Formata embeds de log e envia para o canal configurado."""

    def __init__(self, guild_service: GuildService) -> None:
        self.guild_service = guild_service
        # Sessões ativas: {guild_id: {member_id: VoiceSession}}
        self._voice_sessions: dict[int, dict[int, VoiceSession]] = {}
        # Tasks de atualização/refresh por sessão
        self._update_tasks: dict[tuple[int, int], asyncio.Task] = {}
        self._refresh_tasks: dict[tuple[int, int], asyncio.Task] = {}

    # ── Canal de logs ─────────────────────────────────────────

    async def _get_log_channel(
        self, guild: discord.Guild
    ) -> discord.TextChannel | None:
        """Retorna o canal de logs configurado ou None.

        guild.get_channel() retorna GuildChannel | None, então validamos
        que o canal é realmente um TextChannel antes de retornar.
        """
        config = await self.guild_service.get_config(guild.id)
        if not config:
            return None
        channel_id = config.get("log_channel")
        if not channel_id:
            return None
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return None
        return channel

    async def _send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
        category: LogCategory | None = None,
        *,
        files: list[discord.File] | None = None,
    ) -> discord.Message | None:
        """Envia embed ao canal de logs, verificando se a categoria está ativa."""
        # Verificar se a categoria está habilitada
        if category is not None:
            enabled = await self.guild_service.is_log_category_enabled(
                guild.id, category.value
            )
            if not enabled:
                return None

        channel = await self._get_log_channel(guild)
        if not channel:
            return None
        try:
            return await channel.send(embed=embed, files=files or [])
        except discord.Forbidden:
            logger.warning(
                "Sem permissão para logs em #%s (guild %s)", channel.name, guild.id
            )
        except discord.HTTPException as exc:
            logger.warning("Erro ao enviar log: %s", exc)
        return None

    async def _edit_log_message(
        self,
        message: discord.Message,
        embed: discord.Embed,
    ) -> bool:
        """Edita uma mensagem de log existente. Retorna True se sucesso."""
        try:
            await message.edit(embed=embed)
            return True
        except discord.NotFound:
            logger.debug("Mensagem de log não encontrada para editar.")
            return False
        except discord.Forbidden:
            logger.warning("Sem permissão para editar mensagem de log.")
            return False
        except discord.HTTPException as exc:
            logger.warning("Erro ao editar log: %s", exc)
            return False

    async def _find_recent_audit_actor(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int,
        *,
        within_seconds: int = 20,
    ) -> discord.abc.User | None:
        """Busca executor recente em audit log para um alvo."""
        if not guild.me or not guild.me.guild_permissions.view_audit_log:
            return None

        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                if not entry.target or getattr(entry.target, "id", None) != target_id:
                    continue

                # Ignora entradas antigas para reduzir falsos positivos
                age = discord.utils.utcnow() - entry.created_at
                if age.total_seconds() > within_seconds:
                    continue
                return entry.user
        except discord.Forbidden:
            return None
        except discord.HTTPException:
            return None
        return None

    async def _find_recent_member_update_actor(
        self,
        guild: discord.Guild,
        target_id: int,
        *,
        within_seconds: int = 20,
    ) -> discord.abc.User | None:
        """Busca executor de alterações administrativas no membro (mute/deaf/etc)."""
        return await self._find_recent_audit_actor(
            guild,
            discord.AuditLogAction.member_update,
            target_id,
            within_seconds=within_seconds,
        )

    # ══════════════════════════════════════════════════════════
    #  EVENTOS INTERNOS (EventBus)
    # ══════════════════════════════════════════════════════════

    async def log_internal_event(
        self,
        guild: discord.Guild,
        event_type: BotEvent,
        data: dict[str, Any],
    ) -> None:
        """Formata e envia log de evento interno do EventBus."""
        if event_type in _SILENT_EVENTS:
            return

        # Suprimir level-up quando o sistema de XP está desativado no servidor
        if event_type == BotEvent.USER_LEVELED_UP:
            from core.enums import Feature
            leveling_on = await self.guild_service.is_feature_enabled(
                guild.id, Feature.LEVELING
            )
            if not leveling_on:
                return

        _emoji, title = _EVENT_META.get(
            event_type, (BotEmojis.COMMON_LIST, event_type.value)
        )
        details = _format_event_data(data, guild)

        embed = (
            EmbedBuilder.default()
            .author(name=title)
            .description(details)
            .footer(f"Evento: {event_type.value}")
            .timestamp()
            .build()
        )
        await self._send_log(guild, embed, LogCategory.BOT_EVENTS)

    # ── Helpers de mensagem ───────────────────────────────────

    @staticmethod
    def _extract_image_url(message: discord.Message) -> str | None:
        """Extrai a primeira URL de imagem da mensagem (attachments ou embeds)."""
        # Attachments de imagem
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                return att.url
        # Embeds com imagem
        for emb in message.embeds:
            if emb.image and emb.image.url:
                return emb.image.url
            if emb.thumbnail and emb.thumbnail.url:
                return emb.thumbnail.url
        return None

    @staticmethod
    def _describe_attachments(message: discord.Message) -> list[str]:
        """Retorna linhas descritivas dos attachments (não-imagem)."""
        lines: list[str] = []
        for att in message.attachments:
            is_image = att.content_type and att.content_type.startswith("image/")
            if not is_image:
                size_kb = att.size / 1024
                if size_kb >= 1024:
                    size_str = f"{size_kb / 1024:.1f} MB"
                else:
                    size_str = f"{size_kb:.0f} KB"
                lines.append(
                    f"{BotEmojis.COMMON_CLIP} `{att.filename}` ({size_str})"
                )
        return lines

    @staticmethod
    def _describe_stickers(message: discord.Message) -> list[str]:
        """Retorna linhas descritivas dos stickers."""
        return [f"{BotEmojis.COMMON_STICKER} Sticker: **{s.name}**" for s in message.stickers]

    # ── Log de mensagens ──────────────────────────────────────

    async def log_message_delete(self, message: discord.Message) -> None:
        guild = message.guild
        if not guild:
            return

        files: list[discord.File] = []

        actor = await self._find_recent_audit_actor(
            guild,
            discord.AuditLogAction.message_delete,
            message.author.id,
            within_seconds=5,
        )

        lines: list[str] = []

        if actor and actor.id != message.author.id:
            author_name = f"{actor.display_name} (admin)"
            author_icon = actor.display_avatar.url
            footer_text = f"Admin ID: {actor.id} • Alvo ID: {message.author.id}"
            
            lines.append(f"Deletou a mensagem de: {message.author.mention} em {_channel_mention(message.channel)}")
        else:
            author_name = message.author.display_name
            author_icon = message.author.display_avatar.url
            footer_text = f"Autor ID: {message.author.id}"
            
            lines.append(f"Deletou mensagem em {_channel_mention(message.channel)}:")

        if message.content:
            lines.append(f"```{_truncate(message.content, 1800)}```")
        else:
            lines.append("*Sem texto*")

        sticker_lines = self._describe_stickers(message)
        if sticker_lines:
            lines.append("")
            lines.extend(sticker_lines)

        att_lines = self._describe_attachments(message)
        if att_lines:
            lines.append("")
            lines.extend(att_lines)

        description = "\n".join(lines)

        builder = (
            EmbedBuilder.default()
            .color(discord.Color(0xFF6B6B))
            .author(
                name=author_name,
                icon_url=author_icon,
            )
            .description(description)
            .footer(footer_text)
            .timestamp()
        )

        image_url = self._extract_image_url(message)
        if image_url:
            builder.image(image_url)

        embed = builder.build()
        await self._send_log(guild, embed, LogCategory.MESSAGES, files=files)

    async def log_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        guild = before.guild
        if not guild:
            return

        jump = after.jump_url

        old = _truncate(before.content, 900) if before.content else "*vazio*"
        new = _truncate(after.content, 900) if after.content else "*vazio*"

        lines: list[str] = [
            f"Editou mensagem em {_channel_mention(before.channel)}: [Ir para a mensagem]({jump})",
            "",
            "**Antes:**",
            f"```{old}```",
            "",
            "**Depois:**",
            f"```{new}```",
        ]

        description = "\n".join(lines)

        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0xFFA500))
            .author(
                name=before.author.display_name,
                icon_url=before.author.display_avatar.url,
            )
            .description(description)
            .footer(f"Autor ID: {before.author.id}")
            .timestamp()
            .build()
        )
        await self._send_log(guild, embed, LogCategory.MESSAGES)

    # ══════════════════════════════════════════════════════════
    #  VOZ — Sistema de sessão agrupada
    # ══════════════════════════════════════════════════════════

    def _get_session(self, guild_id: int, member_id: int) -> VoiceSession | None:
        """Retorna a sessão ativa ou None."""
        return self._voice_sessions.get(guild_id, {}).get(member_id)

    def _create_session(
        self,
        member: discord.Member,
        channel_name: str,
    ) -> VoiceSession:
        """Cria uma nova sessão de voz para o membro."""
        guild_id = member.guild.id
        if guild_id not in self._voice_sessions:
            self._voice_sessions[guild_id] = {}

        session = VoiceSession(
            member_id=member.id,
            member_display=str(member),
            member_avatar_url=member.display_avatar.url,
            guild_id=guild_id,
            current_channel=channel_name,
        )
        self._voice_sessions[guild_id][member.id] = session
        return session

    def _remove_session(self, guild_id: int, member_id: int) -> VoiceSession | None:
        """Remove e retorna a sessão, se existir."""
        guild_sessions = self._voice_sessions.get(guild_id)
        if guild_sessions:
            session = guild_sessions.pop(member_id, None)
            if not guild_sessions:
                self._voice_sessions.pop(guild_id, None)
            return session
        return None

    def _cancel_session_tasks(self, guild_id: int, member_id: int) -> None:
        """Cancela tasks de atualização e refresh de uma sessão."""
        key = (guild_id, member_id)
        for task_map in (self._update_tasks, self._refresh_tasks):
            task = task_map.pop(key, None)
            if task and not task.done():
                task.cancel()

    def _schedule_update(self, guild: discord.Guild, member_id: int) -> None:
        """Agenda uma atualização debounced do embed da sessão."""

        key = (guild.id, member_id)
        task = self._update_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()

        async def _run_update():
            try:
                await asyncio.sleep(_SESSION_UPDATE_DEBOUNCE)
                session = self._get_session(guild.id, member_id)
                if session and not session.finalized:
                    await self._update_session_embed(guild, session)
            except asyncio.CancelledError:
                pass

        self._update_tasks[key] = asyncio.create_task(_run_update())

    def _ensure_refresh(self, guild: discord.Guild, member_id: int) -> None:
        """Garante que a sessão seja atualizada periodicamente durante chamadas longas."""

        key = (guild.id, member_id)
        existing = self._refresh_tasks.get(key)
        if existing and not existing.done():
            return

        async def _refresh_loop():
            try:
                while True:
                    await asyncio.sleep(_SESSION_REFRESH_INTERVAL)
                    session = self._get_session(guild.id, member_id)
                    if not session or session.finalized:
                        break
                    await self._update_session_embed(guild, session)

                    # Finaliza se ultrapassar o tempo máximo de sessão
                    if time.time() - session.start_time > _SESSION_IDLE_TIMEOUT:
                        await self._finalize_session(
                            guild, member_id, reason="Sessão encerrada por tempo limite"
                        )
                        break
            except asyncio.CancelledError:
                pass

        self._refresh_tasks[key] = asyncio.create_task(_refresh_loop())

    async def _update_session_embed(
        self,
        guild: discord.Guild,
        session: VoiceSession,
    ) -> None:
        """Envia ou edita o embed da sessão no canal de logs."""
        async with session._lock:
            embed = session.build_embed()

            if session.message is not None:
                success = await self._edit_log_message(session.message, embed)
                if success:
                    return
                # Se falhou (mensagem deletada), enviar uma nova
                session.message = None

            # Enviar novo embed
            msg = await self._send_log(guild, embed, LogCategory.VOICE)
            if msg:
                session.message = msg

    async def _finalize_session(
        self,
        guild: discord.Guild,
        member_id: int,
        reason: str | None = None,
    ) -> None:
        """Finaliza a sessão: marca como encerrada, atualiza embed, limpa."""
        session = self._get_session(guild.id, member_id)
        if not session or session.finalized:
            return

        session.finalized = True
        session.end_time = time.time()
        self._cancel_session_tasks(guild.id, member_id)

        if reason:
            session.add_action(BotEmojis.STATUS_INFO, reason)

        await self._update_session_embed(guild, session)
        self._remove_session(guild.id, member_id)

    async def log_voice_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        guild = member.guild
        session = self._get_session(guild.id, member.id)

        # ── Entrou em um canal de voz ─────────────────────────
        if before.channel is None and after.channel is not None:
            # Se já existia uma sessão fantasma, finalizar
            if session and not session.finalized:
                session.finalized = True
                session.end_time = time.time()
                await self._update_session_embed(guild, session)
                self._remove_session(guild.id, member.id)

            session = self._create_session(member, after.channel.mention)
            session.add_action(BotEmojis.AUDIO_ON, f"Entrou em {after.channel.mention}")
            await self._update_session_embed(guild, session)
            self._schedule_update(guild, member.id)
            self._ensure_refresh(guild, member.id)
            return

        # ── Saiu de um canal de voz ───────────────────────────
        if before.channel is not None and after.channel is None:
            if session:
                session.add_action(BotEmojis.AUDIO_OFF, f"Saiu de {before.channel.mention}")
                session.current_channel = None
                await self._finalize_session(guild, member.id)
            else:
                # Sessão não existia (bot reiniciou?), enviar embed simples
                embed = (
                    EmbedBuilder.default()
                    .color(discord.Color(0xF04747))
                    .author(
                        name=f"{member}",
                        icon_url=member.display_avatar.url,
                    )
                    .description(
                        f"{BotEmojis.STATUS_STOPPED} **Sessão encerrada**\n"
                        f"{BotEmojis.COMMON_CHANNEL} {before.channel.mention}\n\n"
                        f"{BotEmojis.AUDIO_OFF} Saiu de {before.channel.mention}"
                    )
                    .footer(f"ID: {member.id}")
                    .timestamp()
                    .build()
                )
                await self._send_log(guild, embed, LogCategory.VOICE)
            return

        # ── Trocou de canal ───────────────────────────────────
        if (
            before.channel is not None
            and after.channel is not None
            and before.channel.id != after.channel.id
        ):
            if session:
                session.add_action(
                    BotEmojis.ACTION_TOGGLE,
                    f"Trocou: {before.channel.mention} → {after.channel.mention}",
                )
                session.current_channel = after.channel.mention
                await self._update_session_embed(guild, session)
                self._schedule_update(guild, member.id)
                self._ensure_refresh(guild, member.id)
            else:
                # Criar sessão retroativamente
                session = self._create_session(member, after.channel.mention)
                session.add_action(
                    BotEmojis.ACTION_TOGGLE,
                    f"Trocou: {before.channel.mention} → {after.channel.mention}",
                )
                await self._update_session_embed(guild, session)
                self._schedule_update(guild, member.id)
                self._ensure_refresh(guild, member.id)
            return

        # ── Mudanças de estado (mute/deaf impostos por moderação) ──
        changes: list[tuple[str, str]] = []

        member_update_actor: discord.abc.User | None = None
        if before.mute != after.mute or before.deaf != after.deaf:
            member_update_actor = await self._find_recent_member_update_actor(
                guild,
                member.id,
            )

        if before.mute != after.mute:
            if after.mute:
                changes.append(
                    (
                        BotEmojis.MIC_OFF,
                        f"mutou • {_format_actor(member_update_actor)}",
                    )
                )
            else:
                changes.append(
                    (
                        BotEmojis.MIC_ON,
                        f"desmutou • {_format_actor(member_update_actor)}",
                    )
                )

        if before.deaf != after.deaf:
            if after.deaf:
                changes.append(
                    (
                        BotEmojis.AUDIO_OFF,
                        f"Ensurdecido • : {_format_actor(member_update_actor)}",
                    )
                )
            else:
                changes.append(
                    (
                        BotEmojis.AUDIO_ON,
                        f"Desensurdecido •: {_format_actor(member_update_actor)}",
                    )
                )

        if not changes:
            return

        if session:
            for emoji, text in changes:
                session.add_action(emoji, text)
            await self._update_session_embed(guild, session)
            self._schedule_update(guild, member.id)
            self._ensure_refresh(guild, member.id)
        else:
            # Sem sessão ativa — criar uma retroativa
            ch_mention = after.channel.mention if after.channel else "*Desconhecido*"
            session = self._create_session(member, ch_mention)
            for emoji, text in changes:
                session.add_action(emoji, text)
            await self._update_session_embed(guild, session)
            self._schedule_update(guild, member.id)
            self._ensure_refresh(guild, member.id)

    # ══════════════════════════════════════════════════════════
    #  MEMBROS
    # ══════════════════════════════════════════════════════════

    async def log_member_join(self, member: discord.Member) -> None:
        created = int(member.created_at.timestamp())
        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0x43B581))
            .author(name=member.display_name, icon_url=member.display_avatar.url)
            .description(
                f"Entrou no servidor.\n"
                f"**Conta criada:** <t:{created}:R>\n"
                f"**Total de membros:** {member.guild.member_count}"
            )
            .footer(f"ID: {member.id}")
            .timestamp()
            .build()
        )
        await self._send_log(member.guild, embed, LogCategory.MEMBERS)

    async def log_member_remove(self, member: discord.Member) -> None:
        kick_actor = await self._find_recent_audit_actor(
            member.guild, discord.AuditLogAction.kick, member.id
        )

        if kick_actor is not None:
            embed = (
                EmbedBuilder.default()
                .color(discord.Color(0xFF4444))
                .author(name=f"{kick_actor.display_name} (admin)", icon_url=kick_actor.display_avatar.url)
                .description(
                    f"Expulsou o membro: {member.mention} (`{member}`)"
                )
                .footer(f"Admin ID: {kick_actor.id} • Alvo ID: {member.id}")
                .timestamp()
                .build()
            )
            await self._send_log(member.guild, embed, LogCategory.MODERATION)
            return

        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        roles_str = ", ".join(roles) if roles else "*Nenhum*"

        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0xF04747))
            .author(name=member.display_name, icon_url=member.display_avatar.url)
            .description(
                f"Saiu do servidor.\n"
                f"**Cargos:** {_truncate(roles_str, 512)}\n"
                f"**Total de membros:** {member.guild.member_count}"
            )
            .footer(f"ID: {member.id}")
            .timestamp()
            .build()
        )
        await self._send_log(member.guild, embed, LogCategory.MEMBERS)

    async def log_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        guild = before.guild
        changes: list[str] = []

        if before.nick != after.nick:
            old = before.nick or before.name
            new = after.nick or after.name
            changes.append(f"**Apelido:** `{old}` → `{new}`")

        added = set(after.roles) - set(before.roles)
        removed = set(before.roles) - set(after.roles)
        for role in added:
            if role != guild.default_role:
                changes.append(f"**Cargo adicionado:** {role.mention}")
        for role in removed:
            if role != guild.default_role:
                changes.append(f"**Cargo removido:** {role.mention}")

        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                ts = int(after.timed_out_until.timestamp())
                changes.append(f"**Timeout até:** <t:{ts}:f>")
            else:
                changes.append("**Timeout removido**")

        if not changes:
            return

        actor = await self._find_recent_audit_actor(
            guild, discord.AuditLogAction.member_update, after.id, within_seconds=10
        )
        
        if actor and actor.id != after.id:
            author_name = f"{actor.display_name} (admin)"
            author_icon = actor.display_avatar.url
            footer_text = f"Admin ID: {actor.id} • Alvo ID: {after.id}"
            desc = f"Atualizou o membro: {after.mention}\n" + "\n".join(f"▸ {c}" for c in changes)
        else:
            author_name = after.display_name
            author_icon = after.display_avatar.url
            footer_text = f"ID: {after.id}"
            desc = f"Atualizou o próprio perfil:\n" + "\n".join(f"▸ {c}" for c in changes)

        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0x7289DA))
            .author(name=author_name, icon_url=author_icon)
            .description(desc)
            .footer(footer_text)
            .timestamp()
            .build()
        )
        await self._send_log(guild, embed, LogCategory.MEMBERS)

    # ══════════════════════════════════════════════════════════
    #  CANAIS
    # ══════════════════════════════════════════════════════════

    async def log_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        tipo = _CHANNEL_TYPES.get(type(channel), "outro")
        actor = await self._find_recent_audit_actor(
            channel.guild, discord.AuditLogAction.channel_create, channel.id
        )

        if actor:
            author_name = f"{actor.display_name} (admin)"
            author_icon = actor.display_avatar.url
            footer_text = f"Admin ID: {actor.id} • Canal ID: {channel.id}"
        else:
            author_name = "Sistema"
            author_icon = channel.guild.icon.url if channel.guild.icon else None
            footer_text = f"Canal ID: {channel.id}"

        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0x43B581))
            .author(name=author_name, icon_url=author_icon)
            .description(
                f"Criou o canal {channel.mention}\n"
                f"**Tipo:** {tipo}\n"
                f"**Categoria:** {channel.category.name if channel.category else '*Nenhuma*'}"
            )
            .footer(footer_text)
            .timestamp()
            .build()
        )
        await self._send_log(channel.guild, embed, LogCategory.CHANNELS)

    async def log_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        tipo = _CHANNEL_TYPES.get(type(channel), "outro")
        actor = await self._find_recent_audit_actor(
            channel.guild, discord.AuditLogAction.channel_delete, channel.id
        )

        if actor:
            author_name = f"{actor.display_name} (admin)"
            author_icon = actor.display_avatar.url
            footer_text = f"Admin ID: {actor.id} • Canal ID: {channel.id}"
        else:
            author_name = "Sistema"
            author_icon = channel.guild.icon.url if channel.guild.icon else None
            footer_text = f"Canal ID: {channel.id}"

        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0xF04747))
            .author(name=author_name, icon_url=author_icon)
            .description(
                f"Deletou o canal `#{channel.name}`\n"
                f"**Tipo:** {tipo}\n"
                f"**Categoria:** {channel.category.name if channel.category else '*Nenhuma*'}"
            )
            .footer(footer_text)
            .timestamp()
            .build()
        )
        await self._send_log(channel.guild, embed, LogCategory.CHANNELS)

    # ══════════════════════════════════════════════════════════
    #  CARGOS
    # ══════════════════════════════════════════════════════════

    async def log_role_create(self, role: discord.Role) -> None:
        actor = await self._find_recent_audit_actor(
            role.guild, discord.AuditLogAction.role_create, role.id
        )

        if actor:
            author_name = f"{actor.display_name} (admin)"
            author_icon = actor.display_avatar.url
            footer_text = f"Admin ID: {actor.id} • Cargo ID: {role.id}"
        else:
            author_name = "Sistema"
            author_icon = role.guild.icon.url if role.guild.icon else None
            footer_text = f"Cargo ID: {role.id}"

        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0x43B581))
            .author(name=author_name, icon_url=author_icon)
            .description(
                f"Criou o cargo {role.mention}\n"
                f"**Cor:** `{role.color}`\n"
                f"**Posição:** {role.position}"
            )
            .footer(footer_text)
            .timestamp()
            .build()
        )
        await self._send_log(role.guild, embed, LogCategory.ROLES)

    async def log_role_delete(self, role: discord.Role) -> None:
        actor = await self._find_recent_audit_actor(
            role.guild, discord.AuditLogAction.role_delete, role.id
        )

        if actor:
            author_name = f"{actor.display_name} (admin)"
            author_icon = actor.display_avatar.url
            footer_text = f"Admin ID: {actor.id} • Cargo ID: {role.id}"
        else:
            author_name = "Sistema"
            author_icon = role.guild.icon.url if role.guild.icon else None
            footer_text = f"Cargo ID: {role.id}"

        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0xF04747))
            .author(name=author_name, icon_url=author_icon)
            .description(
                f"Deletou o cargo `{role.name}`\n"
                f"**Cor:** `{role.color}`"
            )
            .footer(footer_text)
            .timestamp()
            .build()
        )
        await self._send_log(role.guild, embed, LogCategory.ROLES)

    # ══════════════════════════════════════════════════════════
    #  BAN / UNBAN
    # ══════════════════════════════════════════════════════════

    async def log_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        actor = await self._find_recent_audit_actor(
            guild, discord.AuditLogAction.ban, user.id
        )

        if actor:
            author_name = f"{actor.display_name} (admin)"
            author_icon = actor.display_avatar.url
            footer_text = f"Admin ID: {actor.id} • Alvo ID: {user.id}"
        else:
            author_name = "Sistema"
            author_icon = guild.icon.url if guild.icon else None
            footer_text = f"Alvo ID: {user.id}"

        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0xFF4444))
            .author(name=author_name, icon_url=author_icon)
            .description(f"Baniu o usuário: {user.mention} (`{user}`)")
            .footer(footer_text)
            .timestamp()
            .build()
        )
        await self._send_log(guild, embed, LogCategory.MODERATION)

    async def log_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        actor = await self._find_recent_audit_actor(
            guild, discord.AuditLogAction.unban, user.id
        )

        if actor:
            author_name = f"{actor.display_name} (admin)"
            author_icon = actor.display_avatar.url
            footer_text = f"Admin ID: {actor.id} • Alvo ID: {user.id}"
        else:
            author_name = "Sistema"
            author_icon = guild.icon.url if guild.icon else None
            footer_text = f"Alvo ID: {user.id}"

        embed = (
            EmbedBuilder.default()
            .color(discord.Color(0x43B581))
            .author(name=author_name, icon_url=author_icon)
            .description(f"Desbaniu o usuário: {user.mention} (`{user}`)")
            .footer(footer_text)
            .timestamp()
            .build()
        )
        await self._send_log(guild, embed, LogCategory.MODERATION)
