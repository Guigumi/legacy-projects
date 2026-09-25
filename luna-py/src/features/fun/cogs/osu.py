"""
Cog osu! — mostra perfil e top scores de jogadores do osu!
Uso: !osu <username> [modo]
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunaBot

from core.utils.embed_builder import EmbedBuilder
from features.fun.integrations.osu_service import MODE_DISPLAY
from config.settings import BotEmojis

# Emojis por modo definidos dinamicamente por BotEmojis
MODE_EMOJI = {
    "osu": BotEmojis.OSU_STANDARD,
    "taiko": BotEmojis.OSU_TAIKO,
    "fruits": BotEmojis.OSU_CATCH,
    "mania": BotEmojis.OSU_MANIA,
}

# ── Bandeiras ─────────────────────────────────────────────────


def country_flag(code: str) -> str:
    """Converte código de país (BR, US) em emoji de bandeira."""
    if not code or len(code) != 2:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())


# ── Formatadores ──────────────────────────────────────────────


def fmt_number(n: int | float) -> str:
    """Formata número com separadores de milhar."""
    if isinstance(n, float):
        return f"{n:,.2f}".replace(",", ".")
    return f"{n:,}".replace(",", ".")


def fmt_playtime(seconds: int) -> str:
    """Converte segundos em formato legível."""
    hours = seconds // 3600
    if hours >= 24:
        days = hours // 24
        hours = hours % 24
        return f"{days}d {hours}h"
    mins = (seconds % 3600) // 60
    return f"{hours}h {mins}m"


def fmt_pp(pp: float) -> str:
    return f"{pp:,.0f}pp".replace(",", ".")


def truncate(text: str, length: int = 40) -> str:
    return text[: length - 1] + "…" if len(text) > length else text


# ── View com botões de modo ──────────────────────────────────


class OsuView(discord.ui.View):
    """Botões para trocar de modo de jogo."""

    def __init__(
        self,
        bot: commands.Bot,
        username: str,
        user_data: dict,
        author_id: int,
        current_mode: str,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.username = username
        self.user_data = user_data
        self.author_id = author_id
        self.current_mode = current_mode
        self._cache: dict[str, tuple[dict | None, list[dict]]] = {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    async def _fetch_mode(self, mode: str) -> tuple[dict | None, list[dict]]:
        """Busca dados do modo e cacheia."""
        if mode not in self._cache:
            osu_svc = self.bot.container.osu_service
            user = await osu_svc.get_user(self.username, mode)
            best = []
            if user:
                best = await osu_svc.get_user_best(user["id"], mode, limit=5)
            self._cache[mode] = (user, best)
        return self._cache[mode]

    async def build_embed(self) -> discord.Embed:
        user_data, best_scores = await self._fetch_mode(self.current_mode)

        if not user_data:
            return EmbedBuilder.error_user(
                f"Não encontrei dados de **{MODE_DISPLAY.get(self.current_mode, self.current_mode)}** "
                f"para `{self.username}`."
            ).build()

        return _build_profile_embed(user_data, best_scores, self.current_mode)

    def _update_styles(self) -> None:
        mapping = {
            "osu": self.btn_osu,
            "taiko": self.btn_taiko,
            "fruits": self.btn_fruits,
            "mania": self.btn_mania,
        }
        for mode, btn in mapping.items():
            btn.style = (
                discord.ButtonStyle.primary
                if mode == self.current_mode
                else discord.ButtonStyle.secondary
            )

    async def _switch(self, interaction: discord.Interaction, mode: str) -> None:
        self.current_mode = mode
        self._update_styles()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="Standard", emoji=MODE_EMOJI["osu"], style=discord.ButtonStyle.secondary, row=0
    )
    async def btn_osu(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch(interaction, "osu")

    @discord.ui.button(
        label="Taiko", emoji=MODE_EMOJI["taiko"], style=discord.ButtonStyle.secondary, row=0
    )
    async def btn_taiko(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch(interaction, "taiko")

    @discord.ui.button(
        label="Catch", emoji=MODE_EMOJI["fruits"], style=discord.ButtonStyle.secondary, row=0
    )
    async def btn_fruits(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch(interaction, "fruits")

    @discord.ui.button(
        label="Mania", emoji=MODE_EMOJI["mania"], style=discord.ButtonStyle.secondary, row=0
    )
    async def btn_mania(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch(interaction, "mania")

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# ── Builder do embed ──────────────────────────────────────────


def _build_profile_embed(
    user: dict, best_scores: list[dict], mode: str
) -> discord.Embed:
    """Constrói o embed de perfil do osu!"""
    stats = user.get("statistics") or {}
    country_code = user.get("country_code", "")
    flag = country_flag(country_code)
    mode_name = MODE_DISPLAY.get(mode, mode)
    mode_icon = MODE_EMOJI.get(mode, "")

    global_rank = stats.get("global_rank") or 0
    country_rank = stats.get("country_rank") or 0
    pp = stats.get("pp") or 0
    accuracy = stats.get("hit_accuracy") or 0
    play_count = stats.get("play_count") or 0
    play_time = stats.get("play_time") or 0

    # Ranking formatado
    rank_str = f"#{fmt_number(global_rank)}" if global_rank else "Sem rank"
    country_str = f"#{fmt_number(country_rank)}" if country_rank else "—"

    # Avatar
    avatar_url = user.get("avatar_url", "")

    description = f"### {flag} {user.get('username', '?')}"

    embed = (
        EmbedBuilder.default()
        .color(discord.Color(0xFF66AA))
        .description(description)
        .thumbnail(avatar_url)
        .field(f"{BotEmojis.COMMON_TROPHY} Rank Global", f"**{rank_str}**", inline=True)
        .field(f"{flag} Rank {country_code}", f"**{country_str}**", inline=True)
        .field(f"{BotEmojis.COMMON_SPARKLES} PP", f"**{fmt_pp(pp)}**", inline=True)
        .field(f"{BotEmojis.FILTER} Precisão", f"**{accuracy:.2f}%**", inline=True)
        .field(f"{BotEmojis.COMMON_GAMES} Plays", f"**{fmt_number(play_count)}**", inline=True)
        .field(f"{BotEmojis.COMMON_WATCH} Tempo", f"**{fmt_playtime(play_time)}**", inline=True)
    )

    # Top PP scores
    if best_scores:
        lines: list[str] = []
        for i, score in enumerate(best_scores, 1):
            beatmapset = score.get("beatmapset") or {}
            beatmap = score.get("beatmap") or {}
            title = truncate(beatmapset.get("title", "?"), 35)
            stars = beatmap.get("difficulty_rating") or 0
            score_pp = score.get("pp") or 0
            rank = score.get("rank", "?")
            raw_mods = score.get("mods") or []
            mod_acronyms = [
                m["acronym"] if isinstance(m, dict) else m for m in raw_mods
            ]
            mods_str = f" +{''.join(mod_acronyms)}" if mod_acronyms else ""

            lines.append(
                f"**{i}.** `{title}`  {stars:.2f}{mods_str} ~ **{fmt_pp(score_pp)}** ({rank})"
            )

        embed.field(" Top Scores (PP)", "\n".join(lines), inline=False)

    embed.footer(f"osu! • {mode_name}")
    embed.timestamp()

    return embed.build()


# ── Cog ───────────────────────────────────────────────────────


class OsuCog(commands.Cog):
    """Comando de perfil do osu!"""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service = bot.container.osu_service

    @commands.hybrid_command(
        name="osu",
        description="Veja o perfil de um jogador do osu!",
    )
    @app_commands.describe(
        username="Nome de usuário no osu!",
        mode="Modo de jogo (osu, taiko, catch, mania)",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Standard", value="osu"),
            app_commands.Choice(name="Taiko", value="taiko"),
            app_commands.Choice(name="Catch", value="fruits"),
            app_commands.Choice(name="Mania", value="mania"),
        ]
    )
    async def osu(
        self,
        ctx: commands.Context,
        username: str,
        mode: str | None = None,
    ) -> None:
        if not hasattr(self.bot.container, "osu_service") or self.bot.container.osu_service is None:
            embed = EmbedBuilder.error_internal(
                "A integração com o osu! não está configurada."
            ).build()
            await ctx.send(embed=embed)
            return

        await ctx.defer()

        osu_svc = self.service

        # Resolver modo solicitado
        resolved_mode = osu_svc.resolve_mode(mode) if mode else None

        # Buscar usuário (sem modo para pegar o playmode padrão)
        user_data = await osu_svc.get_user(username)
        if not user_data:
            embed = EmbedBuilder.error_user(
                f"Jogador `{username}` não encontrado no osu!"
            ).build()
            await ctx.send(embed=embed)
            return

        # Se nenhum modo especificado, usar o favorito do player
        if not resolved_mode:
            resolved_mode = user_data.get("playmode", "osu")

        # Buscar com o modo correto
        user_mode_data = await osu_svc.get_user(username, resolved_mode)
        best_scores = await osu_svc.get_user_best(
            user_data["id"], resolved_mode, limit=5
        )

        if not user_mode_data:
            user_mode_data = user_data

        # Montar view
        view = OsuView(
            self.bot,
            username,
            user_mode_data,
            ctx.author.id,
            resolved_mode,
        )
        # Cachear os dados já buscados
        view._cache[resolved_mode] = (user_mode_data, best_scores)
        view._update_styles()

        embed = _build_profile_embed(user_mode_data, best_scores, resolved_mode)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OsuCog(bot))
