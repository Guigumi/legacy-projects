from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
import discord
from config.settings import BotEmojis, now_brt
from core.utils.embed_builder import EmbedBuilder
from core.events import BotEvent
from core.enums import LogCategory

if TYPE_CHECKING:
    from core.database import Database
    from features.listeners.services.logging_service import LoggingService

logger = logging.getLogger(__name__)

class WeeklyLogService:
    """Gera um resumo semanal de atividades do servidor."""

    def __init__(self, db: Database, logging_service: LoggingService) -> None:
        self.db = db
        self.logging_service = logging_service
        self.bot: discord.Client | None = None
        self._task: asyncio.Task | None = None

    def set_bot(self, bot: discord.Client) -> None:
        self.bot = bot

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.debug("WeeklyLogService: loop iniciado")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self) -> None:
        """Loop que verifica se é hora de enviar o log semanal (Segunda 00:00)."""
        while True:
            try:
                now = now_brt()
                # Verificar se é Segunda-feira (weekday == 0) e hora entre 00:00 e 00:15
                if now.weekday() == 0 and now.hour == 0 and now.minute < 15:
                    if self.bot:
                        await self.send_all_weekly_logs()
                    # Dormir por 1 hora para não repetir no mesmo dia
                    await asyncio.sleep(3600)
                else:
                    # Verificar a cada 10 minutos
                    await asyncio.sleep(600)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Erro no loop de log semanal")
                await asyncio.sleep(60)

    async def send_all_weekly_logs(self) -> None:
        if not self.bot:
            return
        logger.info("Iniciando envio de logs semanais...")
        for guild in self.bot.guilds:
            try:
                await self.send_weekly_log(guild)
            except Exception:
                logger.exception("Erro ao enviar log semanal para guild %s", guild.id)

    async def send_weekly_log(self, guild: discord.Guild) -> None:
        # Verificar se a categoria WEEKLY_SUMMARY está habilitada
        enabled = await self.logging_service.guild_service.is_log_category_enabled(
            guild.id, LogCategory.WEEKLY_SUMMARY.value
        )
        if not enabled:
            return

        log_channel = await self.logging_service._get_log_channel(guild)
        if not log_channel:
            return

        # Coletar dados dos últimos 7 dias
        seven_days_ago = (now_brt() - timedelta(days=7)).isoformat()
        
        joins = await self._count_events(guild.id, BotEvent.MEMBER_JOINED, seven_days_ago)
        leaves = await self._count_events(guild.id, BotEvent.MEMBER_LEFT, seven_days_ago)
        level_ups = await self._count_events(guild.id, BotEvent.USER_LEVELED_UP, seven_days_ago)
        cmds = await self._count_events(guild.id, BotEvent.COMMAND_EXECUTED, seven_days_ago)

        async with self.db.execute(
            "SELECT SUM(messages_sent), SUM(voice_seconds) FROM user_data WHERE guild_id = ?",
            (guild.id,)
        ) as cursor:
            row = await cursor.fetchone()
            total_msgs = row[0] or 0
            total_voice_s = row[1] or 0
            total_voice_h = total_voice_s / 3600

        embed = (
            EmbedBuilder.default()
            .title(f"{BotEmojis.COMMON_LIST} Resumo Semanal — {guild.name}")
            .description(
                f"Aqui está o que aconteceu nos últimos 7 dias no servidor.\n\n"
                f"**{BotEmojis.COMMON_USERS} Comunidade**\n"
                f"▸ Novos membros: `{joins}`\n"
                f"▸ Saídas: `{leaves}`\n"
                f"▸ Saldo: `{joins - leaves:+}`\n\n"
                f"**{BotEmojis.COMMON_LVL_UP} Atividade**\n"
                f"▸ Level ups: `{level_ups}`\n"
                f"▸ Comandos usados: `{cmds}`\n\n"
                f"**{BotEmojis.ACTION_SETTINGS} Total Acumulado**\n"
                f"▸ Mensagens: `{total_msgs:,}`\n"
                f"▸ Tempo em Call: `{total_voice_h:.1f}h`"
            )
            .footer("Relatório gerado automaticamente • Luna Bot")
            .timestamp()
            .build()
        )

        await log_channel.send(embed=embed)

    async def _count_events(self, guild_id: int, event: BotEvent, since_iso: str) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM event_log WHERE guild_id = ? AND event_type = ? AND created_at >= ?",
            (guild_id, event.value, since_iso)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
