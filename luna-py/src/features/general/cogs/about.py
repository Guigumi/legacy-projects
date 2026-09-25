"""
Cog informativo — sobre o Luna Bot.
Responde ao comando !about e também quando o bot é mencionado.
"""

from __future__ import annotations

import datetime

import discord
from discord.ext import commands

from config.settings import VERSION, BotEmojis, Defaults, now_brt
from core.utils.embed_builder import EmbedBuilder


def _fmt_uptime(delta: datetime.timedelta) -> str:
    """Formata timedelta em string legível."""
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
    return " ".join(parts)


def _build_about_embed(bot: commands.Bot) -> discord.Embed:
    """Constrói o embed de apresentação."""
    # Uptime
    if bot.start_time:
        delta = now_brt() - bot.start_time
        uptime = _fmt_uptime(delta)
    else:
        uptime = "..."

    # Ping
    latency = round(bot.latency * 1000)

    # Stats
    guild_count = len(bot.guilds)
    member_count = sum(g.member_count or 0 for g in bot.guilds)

    return (
        EmbedBuilder.default()
        .author(name="Luna Bot", icon_url=bot.user.display_avatar.url)
        .thumbnail(bot.user.display_avatar.url)
        .description(
            "Olá! Sou a **Luna** \n\n"
            "Sou um bot multifuncional criada para tornar seu servidor "
            "mais dinâmico e organizado. Posso rolar dados, buscar jogos na Steam, "
            "ver perfis do osu!, rastrear atividade, gerenciar um servidor de Minecraft e muito mais!\n\n"
            "Use **`/help`** para ver tudo que posso fazer."
        )
        .field(f"{BotEmojis.COMMON_TIME} Uptime", f"`{uptime}`", inline=True)
        .field(f"{BotEmojis.COMMON_WIFI_GOOD} Ping", f"`{latency}ms`", inline=True)
        .field(f"{BotEmojis.COMMON_GENERAL} Servidores", f"`{guild_count}`", inline=True)
        .field(f"{BotEmojis.COMMON_USERS} Membros", f"`{member_count}`", inline=True)
        .footer(f"Luna Bot v{VERSION} • Feito com discord.py")
        .timestamp()
        .build()
    )


class AboutView(discord.ui.View):
    """Botões de ação rápida exibidos no /about."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

        # Botão de convite — só aparece se a URL estiver configurada
        if Defaults.INVITE_URL:
            self.add_item(
                discord.ui.Button(
                    label="Me Adicione",
                    emoji=BotEmojis.ACTION_CREATE,
                    style=discord.ButtonStyle.link,
                    url=Defaults.INVITE_URL,
                    row=0,
                )
            )

        # Botão de suporte — só aparece se a URL estiver configurada
        if Defaults.SUPPORT_URL:
            self.add_item(
                discord.ui.Button(
                    label="Servidor de Suporte",
                    emoji=BotEmojis.COMMON_GENERAL,
                    style=discord.ButtonStyle.link,
                    url=Defaults.SUPPORT_URL,
                    row=0,
                )
            )


class AboutCog(commands.Cog):
    """Informações sobre o bot — responde a !about e menções."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="about", description="Sobre o Luna Bot")
    async def about(self, ctx: commands.Context) -> None:
        embed = _build_about_embed(self.bot)
        view = AboutView()
        await ctx.send(embed=embed, view=view if view.children else None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        # Verificar se o bot foi mencionado (e a mensagem é só a menção)
        if self.bot.user not in message.mentions:
            return

        # Ignorar se a mensagem tem conteúdo além da menção (provavelmente um comando)
        clean = (
            message.content.replace(f"<@{self.bot.user.id}>", "")
            .replace(f"<@!{self.bot.user.id}>", "")
            .strip()
        )
        if clean:
            return

        embed = _build_about_embed(self.bot)
        view = AboutView()
        await message.reply(
            embed=embed,
            view=view if view.children else None,
            mention_author=False,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AboutCog(bot))
