"""
Serviço de tracking: mensagens, reações e tempo em call.
Orquestra UserRepository + UserService para conceder XP.

Fluxo de voz:
- start_voice_session() → flush_voice_checkpoint() (periódico) → end_voice_session()
- XP é calculado por _grant_voice_xp() (minutos completos).

Quando Feature.LEVELING está desativado no servidor, o tracking ainda registra
atividade (mensagens, voz), mas nenhum XP é calculado ou concedido.
"""

from __future__ import annotations

import logging
import time

from core.enums import Feature
from core.events import BotEvent, EventBus
from features.community.repositories import UserRepository
from .user_service import UserService

logger = logging.getLogger(__name__)

# Defaults (usados se XPConfigService não estiver disponível)
XP_PER_MESSAGE = 5
XP_PER_VOICE_MINUTE = 3


class TrackingService:
    """Registra atividade de usuários e concede XP."""

    def __init__(
        self,
        user_repo: UserRepository,
        user_service: UserService,
        event_bus: EventBus,
        xp_config_service=None,
        guild_service=None,
    ) -> None:
        self.repo = user_repo
        self.user_svc = user_service
        self.bus = event_bus
        self.xp_config_svc = xp_config_service
        self.guild_svc = guild_service

    # ── Helpers privados ──────────────────────────────────────

    async def _is_leveling_enabled(self, guild_id: int) -> bool:
        """Retorna True se o sistema de XP/niveis estiver ativo no servidor."""
        if self.guild_svc is None:
            return True
        return await self.guild_svc.is_feature_enabled(guild_id, Feature.LEVELING)

    async def _calculate_action_xp(
        self,
        guild_id: int,
        action: str,
        *,
        base_override: int | None = None,
        channel_id: int | None = None,
        member_role_ids: list[int] | None = None,
    ) -> int:
        """Calcula XP final para uma ação, considerando config do servidor,
        boost de canal e boost de cargo.

        Se xp_config_svc não estiver disponível, usa defaults hardcoded.

        Args:
            guild_id: ID do servidor.
            action: Tipo de ação ("message", "voice", "reaction").
            base_override: Se fornecido, usa esse valor como XP base em vez
                           de buscar da config (útil para voz com multiplicador por minuto).
            channel_id: Canal onde a ação ocorreu (para boost/bloqueio).
            member_role_ids: IDs dos cargos do membro (para boost de cargo).

        Returns:
            XP final calculado (pode ser 0 se canal bloqueado).
        """
        if not self.xp_config_svc:
            defaults = {
                "message": XP_PER_MESSAGE,
                "voice": XP_PER_VOICE_MINUTE,
                "reaction": 2,
            }
            return (
                base_override if base_override is not None else defaults.get(action, 0)
            )

        if base_override is not None:
            base_xp = base_override
        else:
            base_xp = await self.xp_config_svc.get_xp_for_action(guild_id, action)

        return await self.xp_config_svc.calculate_xp(
            guild_id,
            base_xp,
            action,
            channel_id=channel_id,
            member_role_ids=member_role_ids,
        )

    async def _grant_voice_xp(
        self,
        guild_id: int,
        user_id: int,
        seconds: int,
        *,
        channel_id: int | None = None,
        member_role_ids: list[int] | None = None,
    ) -> int:
        """Calcula e concede XP de voz baseado nos segundos acumulados.

        Apenas minutos completos geram XP (segundos residuais são ignorados).

        Args:
            guild_id: ID do servidor.
            user_id: ID do usuário.
            seconds: Segundos de voz acumulados.
            channel_id: Canal de voz (para boost/bloqueio).
            member_role_ids: IDs dos cargos do membro (para boost de cargo).

        Returns:
            Quantidade de XP concedido (0 se menos de 1 minuto).
        """
        minutes = seconds // 60
        if minutes <= 0:
            return 0

        if self.xp_config_svc:
            base_xp = await self.xp_config_svc.get_xp_for_action(guild_id, "voice")
            xp = await self._calculate_action_xp(
                guild_id,
                "voice",
                base_override=base_xp * minutes,
                channel_id=channel_id,
                member_role_ids=member_role_ids,
            )
        else:
            xp = XP_PER_VOICE_MINUTE * minutes

        if xp > 0:
            await self.user_svc.grant_xp(guild_id, user_id, xp, channel_id=channel_id)

        return xp

    # ── Tracking de Mensagem ──────────────────────────────────

    async def track_message(
        self,
        guild_id: int,
        user_id: int,
        msg_length: int,
        channel_id: int | None = None,
        member_role_ids: list[int] | None = None,
    ) -> None:
        """Registra uma mensagem enviada e concede XP correspondente."""
        await self.repo.increment_messages(guild_id, user_id, msg_length)

        # Pular cálculo de XP se o sistema de niveis estiver desativado
        if not await self._is_leveling_enabled(guild_id):
            await self.bus.emit(
                guild_id,
                BotEvent.MESSAGE_TRACKED,
                {"user_id": user_id, "msg_length": msg_length, "xp_granted": 0},
            )
            return

        xp = await self._calculate_action_xp(
            guild_id,
            "message",
            channel_id=channel_id,
            member_role_ids=member_role_ids,
        )

        if xp > 0:
            await self.user_svc.grant_xp(guild_id, user_id, xp, channel_id=channel_id)

        await self.bus.emit(
            guild_id,
            BotEvent.MESSAGE_TRACKED,
            {"user_id": user_id, "msg_length": msg_length, "xp_granted": xp},
        )

    # ── Sessões de Voz Persistentes ───────────────────────────

    async def start_voice_session(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int | None,
    ) -> None:
        """Inicializa checkpoint persistente da sessão de voz."""
        now_ts = time.time()
        await self.repo.upsert_voice_session(guild_id, user_id, channel_id, now_ts)

    async def flush_voice_checkpoint(
        self,
        guild_id: int,
        user_id: int,
        min_seconds: int,
        channel_id: int | None = None,
        member_role_ids: list[int] | None = None,
    ) -> int:
        """Faz flush atômico de sessão de voz e concede XP correspondente.

        Credita os segundos acumulados desde o último checkpoint no banco,
        atualiza o checkpoint e concede XP proporcional aos minutos completos.

        Returns:
            Segundos creditados (0 se nada acumulado ou abaixo de min_seconds).
        """
        now_ts = time.time()
        seconds = await self.repo.accrue_voice_session_seconds(
            guild_id,
            user_id,
            now_ts,
            min_seconds=min_seconds,
            channel_id=channel_id,
        )

        if seconds <= 0:
            return 0

        # Pular concessão de XP se o sistema de niveis estiver desativado
        if await self._is_leveling_enabled(guild_id):
            await self._grant_voice_xp(
                guild_id,
                user_id,
                seconds,
                channel_id=channel_id,
                member_role_ids=member_role_ids,
            )

        await self.bus.emit(
            guild_id,
            BotEvent.VOICE_TRACKED,
            {"user_id": user_id, "seconds": seconds},
        )
        return seconds

    async def end_voice_session(self, guild_id: int, user_id: int) -> None:
        """Finaliza sessão de voz persistida."""
        await self.repo.remove_voice_session(guild_id, user_id)

    # ── Tracking de Reação ────────────────────────────────────

    async def track_reaction(
        self,
        guild_id: int,
        user_id: int,
        channel_id: int | None = None,
        member_role_ids: list[int] | None = None,
    ) -> None:
        """Registra uma reação adicionada e concede XP."""
        # Pular cálculo de XP se o sistema de niveis estiver desativado
        if not await self._is_leveling_enabled(guild_id):
            return

        xp = await self._calculate_action_xp(
            guild_id,
            "reaction",
            channel_id=channel_id,
            member_role_ids=member_role_ids,
        )

        if xp > 0:
            await self.user_svc.grant_xp(guild_id, user_id, xp, channel_id=channel_id)
