from __future__ import annotations

import os
import time

import discord
import psutil
from discord.ext import commands

from config.settings import VERSION, BotEmojis, now_brt
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder

class HealthCog(commands.Cog):
    """Cog de monitoramento de saúde do bot (métricas do sistema e do banco)."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="health", description="Mostra o status de saúde e desempenho do bot")
    async def health(self, ctx: commands.Context) -> None:
        await ctx.defer()
        
        # 1. Database Latency
        start_db = time.perf_counter()
        try:
            await self.bot.db.fetchone("SELECT 1")
            db_lat = (time.perf_counter() - start_db) * 1000
            db_status = f"{BotEmojis.STATUS_ENABLED} Online (`{db_lat:.1f}ms`)"
        except Exception as e:
            db_status = f"{BotEmojis.STATUS_DISABLED} Offline ({str(e)})"

        # 2. System Resource Usage
        process = psutil.Process(os.getpid())
        ram_bytes = process.memory_info().rss
        ram_mb = ram_bytes / (1024 * 1024)
        
        cpu_pct = process.cpu_percent(interval=0.1)

        # 3. Gateway / Discord Latency
        gw_lat = round(self.bot.latency * 1000)

        # 4. Uptime
        uptime_str = "..."
        if self.bot.start_time:
            delta = now_brt() - self.bot.start_time
            total = int(delta.total_seconds())
            days, rem = divmod(total, 86400)
            hours, rem = divmod(rem, 3600)
            mins, secs = divmod(rem, 60)
            parts = []
            if days:
                parts.append(f"{days}d")
            if hours:
                parts.append(f"{hours}h")
            if mins:
                parts.append(f"{mins}m")
            parts.append(f"{secs}s")
            uptime_str = " ".join(parts)

        # 5. Guilds and Members
        guilds = len(self.bot.guilds)
        members = sum(g.member_count or 0 for g in self.bot.guilds)

        embed = (
            EmbedBuilder.default()
            .title(f"{BotEmojis.COMMON_TOOLS} Painel de Monitoramento de Saúde")
            .field(f"{BotEmojis.COMMON_WIFI_GOOD} Gateway Latency", f"`{gw_lat}ms`", inline=True)
            .field(f"{BotEmojis.COMMON_DIAMOND} DB Connection", db_status, inline=True)
            .field(f"{BotEmojis.COMMON_TIME} Bot Uptime", f"`{uptime_str}`", inline=True)
            .field(f"{BotEmojis.COMMON_CHART} RAM Usage", f"`{ram_mb:.2f} MB`", inline=True)
            .field(f"{BotEmojis.COMMON_RAY} CPU Usage", f"`{cpu_pct:.1f}%`", inline=True)
            .field(f"{BotEmojis.COMMON_GENERAL} Conexões", f"`{guilds}` guilds | `{members}` members", inline=True)
            .footer(f"Luna Bot v{VERSION}")
            .timestamp()
            .build()
        )
        
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HealthCog(bot))
