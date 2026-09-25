from __future__ import annotations

import datetime
import re
import discord
from discord import app_commands
from discord.ext import commands

from config.settings import Colors, BotEmojis, now_brt
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder


def parse_duration(duration_str: str) -> datetime.timedelta | None:
    """Faz parse de uma string de duração (ex: 30m, 2h45m, 1d) e retorna timedelta."""
    regex = re.compile(
        r"(?:(?P<days>\d+)\s*(?:d|dia|dias))?"
        r"(?:(?P<hours>\d+)\s*(?:h|hora|horas))?"
        r"(?:(?P<minutes>\d+)\s*(?:m|min|minutos))?"
        r"(?:(?P<seconds>\d+)\s*(?:s|seg|segundos))?",
        re.VERBOSE | re.IGNORECASE,
    )
    clean_str = duration_str.strip().lower()
    
    # Se for apenas número puro, assume minutos
    if clean_str.isdigit():
        return datetime.timedelta(minutes=int(clean_str))

    match = regex.fullmatch(clean_str)
    if not match or not any(match.groups()):
        return None

    gd = match.groupdict()
    days = int(gd.get("days") or 0)
    hours = int(gd.get("hours") or 0)
    minutes = int(gd.get("minutes") or 0)
    seconds = int(gd.get("seconds") or 0)

    delta = datetime.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    return delta if delta.total_seconds() > 0 else None


class ReminderCog(commands.Cog, name="Lembretes"):
    """Comandos para agendamento de lembretes pessoais."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service = bot.container.reminder_service
        self.service.on_reminder_dispatch = self.dispatch_reminder

    async def cog_load(self) -> None:
        self.service.start()

    async def cog_unload(self) -> None:
        self.service.stop()

    @app_commands.command(
        name="reminder",
        description="Agenda um lembrete para você (ex: /reminder tempo:30m mensagem:Beber água).",
    )
    @app_commands.describe(
        tempo="Tempo de espera (ex: 30m, 2h, 1d, 15s ou número puro para minutos)",
        mensagem="Mensagem do lembrete",
    )
    async def reminder_cmd(
        self,
        interaction: discord.Interaction,
        tempo: str,
        mensagem: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        delta = parse_duration(tempo)
        if not delta:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "Formato de tempo inválido! Use formatos como `30m`, `2h`, `1d` ou `45` (minutos)."
                ).build()
            )
            return

        # Limite máximo de lembrete: 30 dias
        if delta.days > 30:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "O tempo máximo de lembrete permitido é de 30 dias."
                ).build()
            )
            return

        now = now_brt()
        remind_at = now + delta

        # Registra no banco
        await self.service.create_reminder(
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            message=mensagem,
            remind_at=remind_at,
        )

        ts = int(remind_at.timestamp())
        embed = (
            EmbedBuilder.success("Lembrete agendado!")
            .description(
                f"{BotEmojis.COMMON_WATCH} Vou te lembrar disso em <t:{ts}:R> (<t:{ts}:F>).\n\n"
                f"**Anotado:** {mensagem}"
            )
            .build()
        )
        await interaction.followup.send(embed=embed)

    async def dispatch_reminder(self, reminder: dict) -> None:
        """Callback invocado pelo ReminderService para enviar o lembrete via DM."""
        user_id = reminder["user_id"]
        channel_id = reminder["channel_id"]
        msg_text = reminder["message"]

        # Tenta obter o usuário
        user = self.bot.get_user(user_id)
        if not user:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return

        # Constrói o embed
        embed = (
            EmbedBuilder.default(f"{BotEmojis.COMMON_WATCH} Lembrete!")
            .description(msg_text)
            .build()
        )

        # Tenta enviar na DM primeiro
        sent = False
        try:
            await user.send(embed=embed)
            sent = True
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Fallback: envia no canal original com menção se a DM estiver bloqueada
        if not sent:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    channel = None

            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(
                        content=f"{user.mention} *(não foi possível enviar via DM)*",
                        embed=embed,
                    )
                except discord.Forbidden:
                    pass


async def setup(bot: LunaBot) -> None:
    await bot.add_cog(ReminderCog(bot))
