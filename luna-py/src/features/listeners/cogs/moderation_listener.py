from __future__ import annotations

import datetime
import logging

import discord
from discord.ext import commands

from config.settings import BotEmojis
from core.bot import LunaBot
from core.events import BotEvent
from core.utils.embed_builder import EmbedBuilder

logger = logging.getLogger(__name__)


class ModerationListener(commands.Cog, name="ModerationListener"):
    """Ouvinte de eventos de moderação, como a escalação automática de advertências."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.bot.event_bus.subscribe(BotEvent.WARNING_ISSUED, self.on_warning_issued)

    def cog_unload(self) -> None:
        self.bot.event_bus.unsubscribe(BotEvent.WARNING_ISSUED, self.on_warning_issued)

    async def on_warning_issued(
        self, guild_id: int, event: BotEvent, data: dict
    ) -> None:
        """Chamado quando uma advertência é aplicada a um membro."""
        user_id = data.get("user_id")
        total_warns = data.get("total_warnings", 0)

        if not user_id:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        try:
            member = guild.get_member(user_id)
            if not member:
                member = await guild.fetch_member(user_id)
        except discord.NotFound:
            return
        except Exception:
            self.bot.logger.exception(
                "Falha ao buscar membro %s no guild %s para escalação",
                user_id,
                guild_id,
            )
            return

        # Busca canal de logs se configurado
        log_channel = None
        try:
            config = await self.bot.guild_service.get_config(guild_id)
            if config and config.get("log_channel"):
                log_channel = self.bot.get_channel(config["log_channel"])
                if not log_channel:
                    log_channel = await self.bot.fetch_channel(config["log_channel"])
        except Exception:
            logger.warning("Falha ao buscar canal de log para guild %s", guild_id)

        # Escalação automática: 3 advertências -> Timeout (Mute) de 1 hora
        if total_warns == 3:
            duration = datetime.timedelta(hours=1)
            reason = f"Escalação automática: {total_warns} advertências."
            try:
                await member.timeout(duration, reason=reason)

                embed = (
                    EmbedBuilder.default()
                    .title(f"{BotEmojis.COMMON_ADMIN} Escalação Automática: Castigo (Timeout)")
                    .description(
                        f"O membro {member.mention} foi castigado por **1 hora**.\n"
                        f"**Motivo:** Atingiu **3 advertências**."
                    )
                    .build()
                )

                if log_channel:
                    await log_channel.send(embed=embed)

                # Notifica o usuário na DM
                try:
                    await member.send(
                        f"Você foi castigado (timeout) por **1 hora** no servidor **{guild.name}** "
                        f"por ter atingido 3 advertências."
                    )
                except Exception:
                    pass
            except discord.Forbidden:
                self.bot.logger.warning(
                    "Sem permissão para aplicar timeout a %s no servidor %s",
                    member.id,
                    guild_id,
                )
            except Exception:
                self.bot.logger.exception("Erro ao aplicar timeout na escalação")

        # Escalação automática: 5+ advertências -> Banimento
        elif total_warns >= 5:
            reason = f"Escalação automática: {total_warns} advertências."
            try:
                await member.ban(reason=reason, delete_message_days=1)

                embed = (
                    EmbedBuilder.default()
                    .title(f"{BotEmojis.COMMON_ADMIN} Escalação Automática: Banimento")
                    .description(
                        f"O membro {member.mention} foi **banido** do servidor.\n"
                        f"**Motivo:** Atingiu **{total_warns} advertências**."
                    )
                    .build()
                )

                if log_channel:
                    await log_channel.send(embed=embed)

                # Tenta avisar o usuário na DM antes de banir
                try:
                    await member.send(
                        f"Você foi **banido** do servidor **{guild.name}** por ter atingido "
                        f"{total_warns} advertências."
                    )
                except Exception:
                    pass
            except discord.Forbidden:
                self.bot.logger.warning(
                    "Sem permissão para banir %s no servidor %s",
                    member.id,
                    guild_id,
                )
            except Exception:
                self.bot.logger.exception("Erro ao aplicar ban na escalação")


async def setup(bot: LunaBot) -> None:
    await bot.add_cog(ModerationListener(bot))
