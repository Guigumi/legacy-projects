"""
Cog de listeners do AutoRole — entrega automática de cargos.
Escuta: member_join (instant/timer), reaction_add/remove, interações de botão persistente.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from config.settings import BotEmojis
from core.enums import AutoRoleMode
from core.events import BotEvent
from features.admin.ui.autorole_ui import PersistentAutoRoleButton

logger = logging.getLogger(__name__)


class AutoRoleListenerCog(commands.Cog):
    """Listeners que entregam cargos automaticamente."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.event_bus.subscribe(
            BotEvent.AUTOROLE_DELAYED_GIVE, self.on_delayed_role
        )

    async def cog_load(self) -> None:
        """Registra views persistentes ao carregar a cog."""
        await self._register_persistent_views()

    async def _register_persistent_views(self) -> None:
        """Re-registra botões persistentes para todos os autoroles ativos."""
        # Isso roda antes de on_ready, então guilds pode ainda estar vazio
        # É chamado novamente via on_ready para cobrir todos os servers
        try:
            all_guilds = self.bot.guilds or []
            for guild in all_guilds:
                await self._register_guild_views(guild.id)
        except Exception:
            logger.debug("Views serão registradas no on_ready")

    async def _register_guild_views(self, guild_id: int) -> None:
        """Registra views persistentes para uma guild específica."""
        svc = self.bot.autorole_service
        autoroles = await svc.get_autoroles(guild_id)

        for ar in autoroles:
            if ar["mode"] == AutoRoleMode.BUTTON.value and ar.get("message_id"):
                view = PersistentAutoRoleButton(self.bot, ar["id"], ar["role_id"])
                self.bot.add_view(view, message_id=ar["message_id"])

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Re-registra todas as views persistentes quando o bot fica online."""
        for guild in self.bot.guilds:
            try:
                await self._register_guild_views(guild.id)
            except Exception:
                logger.exception("Erro ao registrar views para guild %s", guild.id)
        logger.debug(
            "AutoRole: views persistentes registradas para %s guild(s)",
            len(self.bot.guilds),
        )

    # ── Member Join (instant & timer) ─────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return

        svc = self.bot.autorole_service
        autoroles = await svc.get_autoroles(member.guild.id)

        for ar in autoroles:
            role = member.guild.get_role(ar["role_id"])
            if not role:
                continue

            mode = ar["mode"]

            if mode == AutoRoleMode.INSTANT.value:
                await self._apply_role(member, role, "AutoRole (instant)")

            elif mode == AutoRoleMode.TIMER.value:
                delay = ar.get("delay_seconds", 0)
                if delay > 0:
                    svc.schedule_delayed_role(
                        member.guild.id, member.id, role.id, delay
                    )
                else:
                    await self._apply_role(member, role, "AutoRole (timer 0s)")

    async def on_delayed_role(
        self, guild_id: int, event: BotEvent, data: dict
    ) -> None:
        """Listener para entrega de cargo após delay."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        member = guild.get_member(data["user_id"])
        role = guild.get_role(data["role_id"])

        if member and role:
            await self._apply_role(
                member, role, f"AutoRole (timer {data.get('delay')}s)"
            )

    async def _apply_role(
        self, member: discord.Member, role: discord.Role, reason: str
    ) -> None:
        """Helper para aplicar cargo e registrar no service."""
        try:
            if role not in member.roles:
                await member.add_roles(role, reason=reason)
                await self.bot.autorole_service.record_role_given(
                    member.guild.id, member.id, role.id
                )
        except discord.Forbidden:
            logger.warning(
                "Sem permissão para dar role %s a %s em %s",
                role.id,
                member.id,
                member.guild.id,
            )
        except Exception:
            logger.exception("Erro ao aplicar autorole")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Cancela timers pendentes quando um membro sai."""
        if member.bot:
            return
        self.bot.autorole_service.cancel_pending(member.guild.id, member.id)

    # ── Reaction Add/Remove ───────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if payload.member and payload.member.bot:
            return

        svc = self.bot.autorole_service
        ar = await svc.get_by_message(payload.message_id)
        if not ar or ar["mode"] != AutoRoleMode.REACTION.value:
            return

        # Verificar emoji
        expected = ar.get("emoji", BotEmojis.STATUS_ENABLED)
        reacted = str(payload.emoji)
        if reacted != expected and payload.emoji.name != expected:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id) or await guild.fetch_member(
            payload.user_id
        )
        role = guild.get_role(ar["role_id"])
        if not role or not member:
            return

        await self._apply_role(member, role, "AutoRole (reaction)")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        svc = self.bot.autorole_service
        ar = await svc.get_by_message(payload.message_id)
        if not ar or ar["mode"] != AutoRoleMode.REACTION.value:
            return

        expected = ar.get("emoji", BotEmojis.STATUS_ENABLED)
        reacted = str(payload.emoji)
        if reacted != expected and payload.emoji.name != expected:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.NotFound:
                return

        role = guild.get_role(ar["role_id"])
        if not role or not member:
            return

        try:
            if role in member.roles:
                await member.remove_roles(role, reason="AutoRole (reaction removida)")
        except discord.Forbidden:
            pass
        except Exception:
            logger.exception("Erro ao remover autorole")




async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoRoleListenerCog(bot))
