"""
Cog de leaderboard — ranking dos top 10 usuários por voice, mensagens e XP.
Usa View com botões para navegar entre as abas.
"""

from __future__ import annotations

import math
from typing import Any
import discord
from discord.ext import commands

from core.utils.embed_builder import EmbedBuilder
from core.utils.formatters import fmt_voice
from core.utils.dev_edit import is_dev_mode, DevEditModal
from core.enums import Feature
from config.settings import BotEmojis, OWNER_ID


# ── Mapeamento das abas ────────────────────────────────────────

TAB_VOICE = "voice_seconds"
TAB_MESSAGES = "messages_sent"
TAB_XP = "xp"

TAB_CONFIG = {
    TAB_VOICE: {
        "title": f"{BotEmojis.COMMON_VOICE} Leaderboard — Tempo em Call",
        "header": "Tempo",
        "formatter": fmt_voice,
    },
    TAB_MESSAGES: {
        "title": f"{BotEmojis.COMMON_MESSAGE} Leaderboard — Mensagens Enviadas",
        "header": "Mensagens",
        "formatter": lambda v: f"{v:,}".replace(",", "."),
    },
    TAB_XP: {
        "title": f"{BotEmojis.COMMON_STAR} Leaderboard — XP / Nível",
        "header": "XP (Nível)",
        "formatter": lambda v: str(v),  # placeholder, tratado especialmente
    },
}


class LeaderboardView(discord.ui.View):
    """View interativa com 3 abas de ranking e paginação."""

    def __init__(
        self,
        bot: commands.Bot,
        guild: discord.Guild,
        author_id: int,
        *,
        show_xp: bool = True,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.guild = guild
        self.author_id = author_id
        self.show_xp = show_xp
        self.current_tab: str = TAB_VOICE
        self.current_page: int = 1
        self.limit_per_page: int = 10
        self._cache: dict[str, list[Any]] = {}
        self._total_counts: dict[str, int] = {}
        self.message: discord.Message | None = None

        # Se XP desativado, remover o botão
        if not show_xp:
            self.remove_item(self.xp_btn)

    # ── Helpers ───────────────────────────────────────────────

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    async def _fetch(self, order_by: str, page: int) -> list[Any]:
        """Busca e cacheia o ranking para a página especificada."""
        cache_key = f"{order_by}:{page}"
        if cache_key not in self._cache:
            offset = (page - 1) * self.limit_per_page
            self._cache[cache_key] = await self.bot.user_service.get_leaderboard(
                self.guild.id,
                order_by=order_by,
                limit=self.limit_per_page,
                offset=offset,
            )
        return self._cache[cache_key]

    async def _get_total_count(self, order_by: str) -> int:
        """Busca e cacheia a contagem total de usuários no ranking."""
        if order_by not in self._total_counts:
            self._total_counts[order_by] = await self.bot.user_service.get_leaderboard_count(
                self.guild.id,
                order_by=order_by,
            )
        return self._total_counts[order_by]

    def _medal(self, pos: int) -> str:
        return {
            0: BotEmojis.LB_FIRST,
            1: BotEmojis.LB_SECOND,
            2: BotEmojis.LB_THIRD,
        }.get(pos, f"`{pos + 1}.`")

    async def build_embed(self) -> discord.Embed:
        """Constrói o embed da aba atual com paginação."""
        cfg = TAB_CONFIG[self.current_tab]
        data = await self._fetch(self.current_tab, self.current_page)
        total_count = await self._get_total_count(self.current_tab)
        total_pages = math.ceil(total_count / self.limit_per_page) or 1

        if not data:
            return (
                EmbedBuilder.default(cfg["title"], "Nenhum dado registrado ainda.")
                .footer(f"Página {self.current_page} de {total_pages} • {self.guild.name}")
                .build()
            )

        lines: list[str] = []
        for i, row in enumerate(data):
            user_id = row["user_id"]
            pos = (self.current_page - 1) * self.limit_per_page + i
            medal = self._medal(pos)

            if self.current_tab == TAB_XP:
                xp = row.get("xp", 0)
                level = row.get("level", 1)
                value_str = f"**{xp:,}** XP (Nv. {level})".replace(",", ".")
            elif self.current_tab == TAB_VOICE:
                value_str = f"**{cfg['formatter'](row.get('voice_seconds', 0))}**"
            else:
                value_str = f"**{cfg['formatter'](row.get('messages_sent', 0))}**"

            lines.append(f"{medal} <@{user_id}> — {value_str}")

        description = "\n".join(lines)

        builder = (
            EmbedBuilder.default()
            .title(cfg["title"])
            .description(description)
            .footer(f"Página {self.current_page} de {total_pages} • Total: {total_count} • {self.guild.name}")
            .timestamp()
        )

        return builder.build()

    async def _update_styles(self) -> None:
        """Atualiza os estilos dos botões de abas e estados dos botões de paginação."""
        self.voice_btn.style = (
            discord.ButtonStyle.primary
            if self.current_tab == TAB_VOICE
            else discord.ButtonStyle.secondary
        )
        self.messages_btn.style = (
            discord.ButtonStyle.primary
            if self.current_tab == TAB_MESSAGES
            else discord.ButtonStyle.secondary
        )
        if self.show_xp:
            self.xp_btn.style = (
                discord.ButtonStyle.primary
                if self.current_tab == TAB_XP
                else discord.ButtonStyle.secondary
            )

        # Atualiza botões de navegação
        total_count = await self._get_total_count(self.current_tab)
        total_pages = math.ceil(total_count / self.limit_per_page) or 1

        self.prev_btn.disabled = (self.current_page <= 1)
        self.next_btn.disabled = (self.current_page >= total_pages)

    async def _update_and_respond(self, interaction: discord.Interaction) -> None:
        """Auxiliar para atualizar estilos, gerar embed e responder à interação."""
        await self._update_styles()
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    # ── Botões de Abas ────────────────────────────────────────

    @discord.ui.button(
        label="Voice", style=discord.ButtonStyle.primary, emoji=BotEmojis.COMMON_VOICE, row=0
    )
    async def voice_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.current_tab = TAB_VOICE
        self.current_page = 1
        await self._update_and_respond(interaction)

    @discord.ui.button(
        label="Mensagens",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.COMMON_MESSAGE,
        row=0,
    )
    async def messages_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.current_tab = TAB_MESSAGES
        self.current_page = 1
        await self._update_and_respond(interaction)

    @discord.ui.button(
        label="XP / Nível",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.COMMON_STAR,
        row=0,
    )
    async def xp_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_tab = TAB_XP
        self.current_page = 1
        await self._update_and_respond(interaction)

    # ── Botões de Paginação ───────────────────────────────────

    @discord.ui.button(
        label="Anterior",
        style=discord.ButtonStyle.secondary,
        emoji="◀️",
        row=1,
    )
    async def prev_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            await self._update_and_respond(interaction)

    @discord.ui.button(
        label="Próximo",
        style=discord.ButtonStyle.secondary,
        emoji="▶️",
        row=1,
    )
    async def next_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        total_count = await self._get_total_count(self.current_tab)
        total_pages = math.ceil(total_count / self.limit_per_page) or 1
        if self.current_page < total_pages:
            self.current_page += 1
            await self._update_and_respond(interaction)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class DevUserSelect(discord.ui.UserSelect):
    """Select para escolher o user do ranking a editar."""

    def __init__(self, bot, guild):
        super().__init__(
            placeholder="[DEV] Selecione um user para editar...",
            row=3,
        )
        self.bot = bot
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return

        target = self.values[0]
        data = await self.bot.user_service.get_profile(
            self.guild.id, target.id
        )
        if not data:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("User sem dados.").build(),
                ephemeral=True,
            )
            return

        modal = DevEditModal(
            title=f"Editar {target.display_name}",
            table="user_data",
            pk_values={"guild_id": self.guild.id, "user_id": target.id},
            fields=[
                {"name": "messages_sent", "label": "Mensagens", "value": data["messages_sent"]},
                {"name": "voice_seconds", "label": "Voice (segundos)", "value": data["voice_seconds"]},
                {"name": "xp", "label": "XP", "value": data["xp"]},
                {"name": "level", "label": "Nível", "value": data["level"]},
            ],
            bot=self.bot,
        )
        await interaction.response.send_modal(modal)


class LeaderboardCog(commands.Cog):
    """Comando de leaderboard do servidor com paginação dinâmica."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="leaderboard",
        aliases=["lb", "top", "rank"],
        description="Veja o ranking dos membros do servidor",
    )
    async def leaderboard(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            embed = EmbedBuilder.error_user(
                "Este comando só pode ser usado em servidores."
            ).build()
            await ctx.send(embed=embed)
            return

        # Verificar se leveling está ativado para exibir aba de XP
        show_xp = await self.bot.guild_service.is_feature_enabled(
            ctx.guild.id,
            Feature.LEVELING,
        )

        view = LeaderboardView(
            self.bot,
            ctx.guild,
            ctx.author.id,
            show_xp=show_xp,
        )

        await view._update_styles()  # Configura estado inicial dos botões (incluindo desabilitação de paginação)
        embed = await view.build_embed()

        if is_dev_mode(self.bot):
            view.add_item(DevUserSelect(self.bot, ctx.guild))

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LeaderboardCog(bot))
