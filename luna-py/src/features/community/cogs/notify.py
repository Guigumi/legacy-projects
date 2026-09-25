"""
Cog de Notificações — agendar lembretes com data/hora ou duração rápida.
Híbrido: funciona com /notify e !notify.
Fuso: America/Sao_Paulo (Brasília).
"""

from __future__ import annotations

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotEmojis, now_brt
from core.bot import LunaBot
from core.events import BotEvent
from core.utils.embed_builder import EmbedBuilder
from features.community.utils.notify_utils import (
    _unix,
    _parse_scheduled_iso,
    _build_notification_manage_embed,
    _build_notification_list_embed,
    _build_empty_notification_list_embed
)
from features.community.ui.notify_ui import (
    NotifyModal,
    NotifyManageView,
    NotifyListView,
    NotifyStartView,
    NotifyHubView
)


class NotifyCog(commands.Cog, name="Notify"):
    """Agendamento de notificações com data, hora e menções."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.bot.event_bus.subscribe(
            BotEvent.NOTIFICATION_DISPATCH, self.on_notification_dispatch
        )

    def build_manage_view(self, notif_id: int, owner_id: int) -> NotifyManageView:
        """Cria a view de gerenciamento para uma notificação."""
        return NotifyManageView(self, notif_id, owner_id)

    async def cog_load(self) -> None:
        """Inicia o loop de verificação quando a cog é carregada (inclui restart)."""
        self.bot.notification_service.start()

    async def on_notification_dispatch(
        self, guild_id: int, event: BotEvent, data: dict
    ) -> None:
        """Listener que realiza o envio físico das mensagens de notificação."""
        notif = data["notification"]
        notif_type = data["type"]
        channel = self.bot.get_channel(notif["channel_id"])

        if not channel:
            try:
                channel = await self.bot.fetch_channel(notif["channel_id"])
            except (discord.NotFound, discord.Forbidden):
                return

        mentions = await self.bot.notification_service.build_mentions(notif)
        ts = _unix(_parse_scheduled_iso(notif["scheduled_at"]))

        if notif_type == "reminder":
            minutes = data["minutes"]
            desc = f"{BotEmojis.COMMON_WATCH} Começa em **{minutes} minuto(s)**\n<t:{ts}:F>"
            if notif.get("description"):
                desc += f"\n\n{notif['description']}"
        else:
            desc = notif.get("description") or ""

        if mentions:
            desc += (
                f"\n\n{'─' * 30}\n{mentions}"
                if desc
                else f"{'─' * 30}\n{mentions}"
            )

        creator = self.bot.get_user(notif["creator_id"])
        creator_name = creator.display_name if creator else "Desconhecido"
        creator_avatar = creator.display_avatar.url if creator else None

        embed = (
            EmbedBuilder.default()
            .title(notif["title"])
            .description(desc)
            .author(creator_name, creator_avatar)
            .build()
        )

        try:
            await channel.send(content=mentions, embed=embed)
        except (discord.NotFound, discord.Forbidden):
            pass
        except Exception:
            self.bot.logger.exception("Erro ao despachar notificação #%s", notif["id"])

    async def cog_unload(self) -> None:
        """Para o loop quando a cog é descarregada."""
        self.bot.notification_service.stop()

    # ── Comando híbrido ───────────────────────────────────────

    @commands.hybrid_command(
        name="notify",
        description=" Agendar uma notificação com data, hora e menções.",
        aliases=["notificar", "lembrete"],
    )
    @app_commands.describe(acao="O que deseja fazer")
    @app_commands.choices(
        acao=[
            app_commands.Choice(name="Hub de notificações", value="hub"),
            app_commands.Choice(name="Criar nova notificação", value="criar"),
            app_commands.Choice(name="Listar minhas notificações", value="listar"),
        ]
    )
    async def notify_cmd(
        self,
        ctx: commands.Context,
        acao: str | None = None,
    ) -> None:
        if not ctx.guild:
            await ctx.send(
                embed=EmbedBuilder.error_user(
                    "Este comando só funciona em servidores."
                ).build(),
            )
            return

        if acao is None or acao == "criar":
            if ctx.interaction:
                await ctx.interaction.response.send_modal(
                    NotifyModal(self, ctx.channel.id)
                )
            else:
                embed = (
                    EmbedBuilder.default(
                        f"{BotEmojis.COMMON_NOTIFICATIONS} Nova Notificação",
                        "Clique no botão abaixo para preencher os dados da sua notificação.\n\n"
                        "**Formatos aceitos:**\n"
                        "• Duração rápida: `30m`, `1h`, `2h30m`\n"
                        "• Data + Hora (Brasília): `17/02/2026` + `14:30`",
                    )
                    .footer("Horário de Brasília (America/Sao_Paulo)")
                    .build()
                )
                view = NotifyStartView(self, ctx.channel.id, ctx.author.id)
                await ctx.send(embed=embed, view=view)

        elif acao == "hub":
            embed = (
                EmbedBuilder.default(
                    f"{BotEmojis.COMMON_NOTIFICATIONS} Hub de Notificações",
                    "Use os botões abaixo para criar, listar ou gerenciar suas notificações rapidamente.",
                )
                .footer("Apenas você verá este painel.")
                .build()
            )
            view = NotifyHubView(self, ctx.channel.id, ctx.author.id)
            await ctx.send(embed=embed, view=view)

        elif acao == "listar":
            svc = self.bot.notification_service
            notifs = await svc.get_by_creator(ctx.guild.id, ctx.author.id)
            if not notifs:
                await ctx.send(embed=_build_empty_notification_list_embed())
                return

            embed = _build_notification_list_embed(notifs)
            view = NotifyListView(self, notifs[:25], ctx.author.id)
            await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NotifyCog(bot))
