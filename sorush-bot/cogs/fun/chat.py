"""
Message Chat Ranking Command
Mostra o ranking de mensagens com apresentação limpa e sem excesso de informação.
"""
import logging
from typing import Dict, Optional

import discord
from discord.ext import commands

from config import Colors
from services.repositories import user_repo
from services.user_service import user_service
from services.embed_helpers import (
    format_number, stat_value, spacer_field,
    embed_cooldown, embed_internal_error
)

logger = logging.getLogger(__name__)


# Aliases for backward compat
_stat_value = stat_value
_spacer_field = spacer_field


class MessageRank(commands.Cog):
	"""Ranking de mensagens"""

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
	async def on_message(self, message: discord.Message) -> None:
		"""Registra métricas de mensagens"""
		if message.author.bot:
			return
		if not message.guild:
			return
		if message.type not in (discord.MessageType.default, discord.MessageType.reply):
			return

		try:
			content = message.content or ""
			attachments = len(message.attachments) if getattr(message, "attachments", None) else 0
			replies = bool(message.reference)
			mentions = len(message.mentions) if getattr(message, "mentions", None) else 0

			result = user_service.record_message_activity(
				message.guild.id,
				message.author.id,
				content,
				attachments_count=attachments,
				has_reply=replies,
				mentions_count=mentions,
				user_name=message.author.display_name,
			)

			if not result.get("success"):
				logger.error(f"Failed to save message stats for user {message.author.id}")
		except Exception as e:
			logger.error(f"Erro ao registrar mensagem: {e}", exc_info=True)

	@commands.hybrid_command(
		name="chat",
		description="💬 Ranking de mensagens do servidor"
	)
	@commands.guild_only()
	@commands.cooldown(1, 8, commands.BucketType.user)
	async def message_ranking(self, ctx: commands.Context, limit: int = 10) -> None:
		"""Mostra os membros com mais mensagens"""
		if not ctx.guild:
			await ctx.send("⚠️ Este comando só pode ser usado em servidores!")
			return

		limit = max(1, min(limit or 10, 50))
		guild_id = ctx.guild.id
        
		try:
			leaderboard = user_repo.get_leaderboard_values(guild_id, "messages", limit=limit)

			if not leaderboard:
				embed = discord.Embed(
					title="",
					description=" ",
					color=Colors.WARNING
				)
				embed.add_field(name="─────〔 Chat 〕─────", value="Nenhum dado ainda", inline=False)
				await ctx.send(embed=embed)
				return

			embed = discord.Embed(
				title="",
				description=" ",
				color=Colors.PRIMARY
			)
			embed.add_field(name="─────〔 Chat 〕─────", value="", inline=False)
			if ctx.guild and ctx.guild.icon:
				embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)

			medals = {1: "🥇", 2: "🥈", 3: "🥉"}
			lines = []

			for position, (user_id, messages) in enumerate(leaderboard, start=1):
				user = await self._get_user(int(user_id))
				medal = medals.get(position, f"**{position}º**")
				mention = user.mention if user else f"`{user_id}`"
				lines.append(f"{medal} {mention} — {_stat_value(format_number(messages))}")

			if lines:
				embed.add_field(name="Ranking", value="\n".join(lines), inline=False)

			# Mostrar posição do usuário
			author_stats = user_repo.get_or_create_user(guild_id, ctx.author.id)
			author_messages = author_stats.get("messages", 0)
            
			if author_messages > 0:
				author_rank = user_repo.get_user_rank(guild_id, ctx.author.id, "messages")
				if author_rank:
					embed.add_field(name="─────〔 Extras 〕─────", value="", inline=False)
					embed.add_field(
						name="Sua posição",
						value=f"#{author_rank} — {_stat_value(format_number(author_messages))}",
						inline=False
					)

			await ctx.send(embed=embed)

		except Exception as e:
			logger.error(f"Erro no comando message_ranking: {e}", exc_info=True)
			await ctx.send(embed=embed_internal_error(), ephemeral=True)

	@message_ranking.error
	async def message_ranking_error(self, ctx: commands.Context, error: Exception) -> None:
		if isinstance(error, commands.CommandOnCooldown):
			await ctx.send(embed=embed_cooldown(error.retry_after), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
	await bot.add_cog(MessageRank(bot))