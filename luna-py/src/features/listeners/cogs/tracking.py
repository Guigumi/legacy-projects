"""
Cog de tracking — registra mensagens e tempo em voz dos membros.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from config.settings import TrackingConfig
from core.enums import Feature

if TYPE_CHECKING:
    from core.bot import LunaBot

logger = logging.getLogger(__name__)


class TrackingCog(commands.Cog):
    """Listeners de tracking de mensagens e voz."""

    bot: LunaBot

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self._voice_sessions: set[tuple[int, int]] = set()
        self._voice_checkpoints: dict[tuple[int, int], float] = {}
        self._voice_locks: dict[tuple[int, int], asyncio.Lock] = {}

        # Escutar level-up para dar cargos automaticamente
        from core.events import BotEvent

        self.bot.event_bus.subscribe(BotEvent.USER_LEVELED_UP, self._on_level_up)

        # Cooldowns para proteção estrita contra SPAM (permite interação normal)
        self._msg_cooldown = commands.CooldownMapping.from_cooldown(5, 5.0, commands.BucketType.member)
        self._reaction_cooldowns: dict[tuple[int, int], float] = {}

        self._voice_checkpoint_loop.start()

    async def cog_unload(self) -> None:
        if self._voice_checkpoint_loop.is_running():
            self._voice_checkpoint_loop.cancel()

    async def _on_level_up(self, guild_id: int, event_type, data: dict) -> None:
        """Concede cargos configurados quando um usuário sobe de nível."""
        if not hasattr(self.bot, "xp_config_service"):
            return

        user_id = data.get("user_id")
        new_level = data.get("new_level")
        if not user_id or not new_level:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        member = guild.get_member(user_id)
        if not member:
            return

        try:
            config = await self.bot.xp_config_service.get_config(guild_id)
            role_policy = config.get("role_policy", "stack")

            # Buscar todos os cargos até o nível atual
            level_roles = await self.bot.xp_config_service.get_all_roles_up_to_level(
                guild_id, new_level
            )

            if role_policy == "replace":
                highest_lr = level_roles[-1] if level_roles else None
                all_configured_level_roles = await self.bot.xp_config_service.get_level_roles(guild_id)

                if highest_lr:
                    highest_role = guild.get_role(highest_lr["role_id"])
                    if highest_role and highest_role not in member.roles:
                        await member.add_roles(
                            highest_role, reason=f"Luna XP: atingiu nível {highest_lr['level']}"
                        )
                        logger.info(
                            "Role %s (highest) given to %s for reaching level %s in guild %s",
                            highest_role.name,
                            member.id,
                            highest_lr["level"],
                            guild_id,
                        )

                    # Remover outros cargos por nível anteriores
                    roles_to_remove = []
                    for lr in all_configured_level_roles:
                        if lr["role_id"] != highest_lr["role_id"]:
                            role = guild.get_role(lr["role_id"])
                            if role and role in member.roles:
                                roles_to_remove.append(role)

                    if roles_to_remove:
                        await member.remove_roles(
                            *roles_to_remove,
                            reason="Luna XP: substituição de cargo por nível (policy=replace)"
                        )
                        logger.info(
                            "Roles %s removed from %s in guild %s due to replace policy",
                            [r.name for r in roles_to_remove],
                            member.id,
                            guild_id,
                        )
            else:  # stack
                for lr in level_roles:
                    role = guild.get_role(lr["role_id"])
                    if role and role not in member.roles:
                        await member.add_roles(
                            role, reason=f"Luna XP: atingiu nível {lr['level']}"
                        )
                        logger.info(
                            "Role %s given to %s for reaching level %s in guild %s",
                            role.name,
                            member.id,
                            lr["level"],
                            guild_id,
                        )
        except Exception:
            logger.exception(
                "Falha ao dar cargo de nível para %s em guild %s", user_id, guild_id
            )


    # ── Message Tracking ──────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        # message.author in a guild context is always a Member
        member = message.author
        if not isinstance(member, discord.Member):
            return

        # Proteção contra farm: ignorar se em cooldown
        bucket = self._msg_cooldown.get_bucket(message)
        if bucket and bucket.update_rate_limit():
            return

        guild_svc = self.bot.guild_service
        if not await guild_svc.is_feature_enabled(message.guild.id, Feature.TRACKING):
            return

        tracking_svc = self.bot.tracking_service
        await tracking_svc.track_message(
            message.guild.id,
            member.id,
            len(message.content),
            channel_id=message.channel.id,
            member_role_ids=[r.id for r in member.roles],
        )

    # ── Reaction Tracking ─────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if not payload.guild_id or payload.member is None or payload.member.bot:
            return

        # Proteção contra farm de reação: spam protection (2s)
        now = time.monotonic()
        key = (payload.guild_id, payload.member.id)
        last_time = self._reaction_cooldowns.get(key, 0.0)
        if now - last_time < 2.0:
            return
        self._reaction_cooldowns[key] = now
        
        # Limpar cache de vez em quando
        if len(self._reaction_cooldowns) > 5000:
            threshold = now - 15.0
            self._reaction_cooldowns = {k: v for k, v in self._reaction_cooldowns.items() if v > threshold}

        guild_svc = self.bot.guild_service
        if not await guild_svc.is_feature_enabled(payload.guild_id, Feature.TRACKING):
            return

        tracking_svc = self.bot.tracking_service
        await tracking_svc.track_reaction(
            payload.guild_id,
            payload.member.id,
            channel_id=payload.channel_id,
            member_role_ids=[r.id for r in payload.member.roles],
        )

    # ── Voice Tracking ────────────────────────────────────────

    async def _flush_voice_session(
        self, key: tuple[int, int], channel_id: int | None = None
    ) -> None:
        """Persiste parte da sessão de voz para evitar perda em sessões longas."""
        if key not in self._voice_sessions:
            return

        lock = self._voice_locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key not in self._voice_sessions:
                return

            guild_id, user_id = key
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            member = guild.get_member(user_id)
            if not member:
                return

            if channel_id is None and member.voice and member.voice.channel:
                channel_id = member.voice.channel.id

            tracking_svc = self.bot.tracking_service
            await tracking_svc.flush_voice_checkpoint(
                guild_id,
                user_id,
                min_seconds=TrackingConfig.VOICE_MIN_SECONDS,
                channel_id=channel_id,
                member_role_ids=[r.id for r in member.roles],
            )
            # Atualiza checkpoint em memória
            self._voice_checkpoints[key] = time.time()

    @tasks.loop(seconds=TrackingConfig.VOICE_FLUSH_INTERVAL_SECONDS)
    async def _voice_checkpoint_loop(self) -> None:
        """Checkpoint periódico para sessões longas em call."""
        if not self._voice_sessions:
            return

        now = time.time()
        keys = list(self._voice_sessions)
        for key in keys:
            # Usa o checkpoint em memória em vez de consultar o banco de dados
            last_checkpoint = self._voice_checkpoints.get(key, now)
            
            if now - last_checkpoint >= TrackingConfig.VOICE_CHECKPOINT_SECONDS:
                try:
                    await self._flush_voice_session(key)
                except Exception:
                    logger.exception(
                        "Falha ao persistir checkpoint de voz para %s", key
                    )

    @_voice_checkpoint_loop.before_loop
    async def _before_voice_checkpoint_loop(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Inicializa sessões para membros já conectados quando o bot liga.

        Fluxo:
        1. Para cada guild com tracking ativo, coleta IDs de quem está em call.
        2. Sessões no DB de quem NÃO está mais em call → flush + remove (OrphanCleanup).
        3. Sessões no DB de quem AINDA está em call → flush acumulado + reset checkpoint.
        4. Quem está em call mas SEM sessão no DB → cria nova.
        """
        now = time.time()
        guild_svc = self.bot.guild_service
        tracking_svc = self.bot.tracking_service
        tracking_repo = tracking_svc.repo

        # Teto de delta para evitar inflação de sessões muito antigas (24h)
        MAX_DELTA_SECONDS = 86400

        for guild in self.bot.guilds:
            if not await guild_svc.is_feature_enabled(guild.id, Feature.TRACKING):
                continue

            # Coletar quem está em call agora
            active_in_voice: dict[int, int] = {}  # user_id → channel_id
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        active_in_voice[member.id] = channel.id

            # Buscar todas as sessões DB desta guild
            try:
                db_sessions = await tracking_repo.get_all_voice_sessions(guild.id)
            except AttributeError:
                # Método não existe ainda — fallback seguro
                db_sessions = []

            db_user_ids = {s["user_id"] for s in db_sessions}

            # ── Orphan cleanup: sessões no DB de quem saiu enquanto bot estava offline
            for session in db_sessions:
                user_id = session["user_id"]
                key = (guild.id, user_id)

                if user_id not in active_in_voice:
                    # Usuário não está mais em call — flush o que dá e remove
                    last_cp = float(session["last_checkpoint_ts"])
                    delta = min(int(now - last_cp), MAX_DELTA_SECONDS)

                    if delta >= TrackingConfig.VOICE_MIN_SECONDS:
                        member = guild.get_member(user_id)
                        role_ids = [r.id for r in member.roles] if member else None

                        try:
                            await tracking_svc.flush_voice_checkpoint(
                                guild.id,
                                user_id,
                                min_seconds=TrackingConfig.VOICE_MIN_SECONDS,
                                channel_id=session.get("channel_id"),
                                member_role_ids=role_ids,
                            )
                        except Exception:
                            logger.exception(
                                "Falha ao flush sessão órfã %s/%s", guild.id, user_id
                            )

                    await tracking_repo.remove_voice_session(guild.id, user_id)
                    self._voice_sessions.discard(key)
                    self._voice_locks.pop(key, None)
                    logger.debug("Sessão órfã limpa: %s em guild %s", user_id, guild.id)
                    continue

                # Usuário ainda está em call — flush acumulado e resetar checkpoint
                last_cp = float(session["last_checkpoint_ts"])
                delta = int(now - last_cp)

                if delta >= TrackingConfig.VOICE_MIN_SECONDS and delta <= MAX_DELTA_SECONDS:
                    member = guild.get_member(user_id)
                    role_ids = [r.id for r in member.roles] if member else None
                    try:
                        await tracking_svc.flush_voice_checkpoint(
                            guild.id,
                            user_id,
                            min_seconds=TrackingConfig.VOICE_MIN_SECONDS,
                            channel_id=active_in_voice[user_id],
                            member_role_ids=role_ids,
                        )
                    except Exception:
                        logger.exception(
                            "Falha ao flush sessão existente %s/%s", guild.id, user_id
                        )
                elif delta > MAX_DELTA_SECONDS:
                    # Sessão muito antiga — resetar sem creditar (provavelmente lixo)
                    await tracking_repo.upsert_voice_session(
                        guild.id, user_id, active_in_voice[user_id], now
                    )
                    logger.warning(
                        "Sessão de voz com delta > 24h resetada: %s/%s (delta=%ds)",
                        guild.id, user_id, delta,
                    )

                self._voice_sessions.add(key)
                self._voice_checkpoints[key] = last_cp

            # ── Novos: quem está em call mas não tem sessão no DB
            for user_id, channel_id in active_in_voice.items():
                if user_id in db_user_ids:
                    continue  # já processado acima
                key = (guild.id, user_id)
                self._voice_sessions.add(key)
                self._voice_checkpoints[key] = now
                await tracking_repo.upsert_voice_session(
                    guild.id, user_id, channel_id, now
                )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        guild_svc = self.bot.guild_service
        if not await guild_svc.is_feature_enabled(member.guild.id, Feature.TRACKING):
            return

        key = (member.guild.id, member.id)

        # Entrou em canal de voz
        if before.channel is None and after.channel is not None:
            self._voice_sessions.add(key)
            self._voice_checkpoints[key] = time.time()
            await self.bot.tracking_service.start_voice_session(
                member.guild.id,
                member.id,
                after.channel.id,
            )
            logger.debug(
                "Voice session started: %s in guild %s", member.id, member.guild.id
            )

        # Saiu de canal de voz
        elif before.channel is not None and after.channel is None:
            await self._flush_voice_session(key, channel_id=before.channel.id)
            self._voice_sessions.discard(key)
            self._voice_checkpoints.pop(key, None)
            self._voice_locks.pop(key, None)
            await self.bot.tracking_service.end_voice_session(
                member.guild.id, member.id
            )
            logger.debug(
                "Voice session ended: %s in guild %s",
                member.id,
                member.guild.id,
            )

        # Moveu de um canal de voz para outro
        elif (
            before.channel is not None
            and after.channel is not None
            and before.channel.id != after.channel.id
        ):
            await self._flush_voice_session(key, channel_id=before.channel.id)
            await self.bot.tracking_service.start_voice_session(
                member.guild.id,
                member.id,
                after.channel.id,
            )


async def setup(bot: LunaBot) -> None:
    await bot.add_cog(TrackingCog(bot))
