"""
Voice Call Ranking Command
Mostra o ranking de tempo em chamadas de voz com apresentação limpa e sem excesso de informação.
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import discord
from discord.ext import commands

from config import Colors
from services.repositories import user_repo
from services.user_service import user_service
from services.embed_helpers import (
    format_time, stat_value, spacer_field,
    embed_cooldown, embed_internal_error
)

logger = logging.getLogger(__name__)


# Aliases for backward compat
_stat_value = stat_value
_spacer_field = spacer_field


class VoiceRank(commands.Cog):
    """Ranking de tempo em chamadas de voz"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_cache: Dict[int, Optional[discord.User]] = {}

    async def _get_user(self, user_id: int) -> Optional[discord.User]:
        """Get user from cache or fetch"""
        if user_id in self.user_cache:
            return self.user_cache[user_id]
        
        try:
            user = await self.bot.fetch_user(user_id)
            self.user_cache[user_id] = user
            return user
        except discord.HTTPException:
            self.user_cache[user_id] = None
            return None

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        """Detecta mudanças de estado em chamadas de voz"""
        try:
            if member.bot or not member.guild:
                return

            guild_id = member.guild.id
            user_id = member.id

            # Entrada em canal
            if before.channel is None and after.channel is not None:
                session_id = user_service.start_voice_session(guild_id, user_id, after.channel.id)
                if session_id is None:
                    logger.error(f"Erro ao iniciar sessão de voz para {user_id} em {guild_id}")
                else:
                    logger.debug(f"[voice] Sessão iniciada: {user_id} no canal {after.channel.id}")

            # Saída do canal
            elif before.channel is not None and after.channel is None:
                duration = user_service.end_voice_session(guild_id, user_id)
                if duration is None:
                    logger.error(f"Erro ao encerrar sessão de voz para {user_id} em {guild_id}")
                else:
                    logger.debug(f"[voice] Sessão encerrada: {user_id}")

            # Troca de canal
            elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
                end_result = user_service.end_voice_session(guild_id, user_id)
                start_result = user_service.start_voice_session(guild_id, user_id, after.channel.id)
                if end_result is None or start_result is None:
                    logger.error(f"Erro ao trocar canal de voz para {user_id} em {guild_id}")
                else:
                    logger.debug(f"[voice] Canal trocado: {user_id} de {before.channel.id} para {after.channel.id}")

        except Exception as e:
            logger.error(f"Erro não tratado em on_voice_state_update: {e}", exc_info=True)

    @commands.hybrid_command(
        name="call",
        description="🎤 Ranking de tempo em chamadas de voz"
    )
    @commands.guild_only()
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def voice_ranking(self, ctx: commands.Context, limit: int = 10) -> None:
        """Mostra os membros com mais tempo em chamadas de voz"""
        if not ctx.guild:
            await ctx.send("⚠️ Este comando só pode ser usado em servidores!")
            return

        limit = max(1, min(limit or 10, 50))
        guild_id = ctx.guild.id
        
        try:
            leaderboard = user_repo.get_leaderboard_values(guild_id, "voice_mins", limit=limit)

            if not leaderboard:
                embed = discord.Embed(
                    title="",
                    description=" ",
                    color=Colors.WARNING
                )
                embed.add_field(name="─────〔 Voz 〕─────", value="Nenhum dado ainda", inline=False)
                await ctx.send(embed=embed)
                return

            embed = discord.Embed(
                title="",
                description=" ",
                color=Colors.SUCCESS
            )
            embed.add_field(name="─────〔 Voz 〕─────", value="", inline=False)
            if ctx.guild and ctx.guild.icon:
                embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)

            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            lines = []

            for position, (user_id, minutes) in enumerate(leaderboard, start=1):
                user = await self._get_user(int(user_id))
                medal = medals.get(position, f"**{position}º**")
                mention = user.mention if user else f"`{user_id}`"
                lines.append(f"{medal} {mention} — {_stat_value(format_time(minutes))}")

            if lines:
                embed.add_field(name="Ranking", value="\n".join(lines), inline=False)

            # Mostrar posição do usuário
            author_stats = user_repo.get_or_create_user(guild_id, ctx.author.id)
            author_voice = author_stats.get("voice_mins", 0)
            
            if author_voice > 0:
                author_rank = user_repo.get_user_rank(guild_id, ctx.author.id, "voice_mins")
                if author_rank:
                    embed.add_field(name="─────〔 Extras 〕─────", value="", inline=False)
                    embed.add_field(
                        name="Sua posição",
                        value=f"#{author_rank} — {_stat_value(format_time(author_voice))}",
                        inline=False
                    )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Erro no comando voice_ranking: {e}", exc_info=True)
            await ctx.send(embed=embed_internal_error(), ephemeral=True)

    @voice_ranking.error
    async def voice_ranking_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=embed_cooldown(error.retry_after), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceRank(bot))
