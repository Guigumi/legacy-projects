"""
Cog de ajuda — navegação por abas com botões interativos.

A aba "Owner" só aparece para o dono do bot (OWNER_ID em settings/config.py).
Usuários comuns nunca veem o botão nem o conteúdo.
"""

from __future__ import annotations

from collections.abc import Callable

import discord
from discord.ext import commands

from config.settings import OWNER_ID, BotEmojis
from core.utils.embed_builder import EmbedBuilder

# Tipo para as funções que constroem embeds de cada aba
_EmbedFactory = Callable[[str, commands.Bot], discord.Embed]


def _bot_avatar(bot: commands.Bot) -> str:
    """Retorna a URL do avatar do bot, seguro contra bot.user ser None."""
    if bot.user is not None:
        return bot.user.display_avatar.url
    return ""


# ── Embeds por aba ────────────────────────────────────────────


def _embed_bot(prefix: str, bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Bot", icon_url=_bot_avatar(bot))
        .description(
            f"**`{prefix}help`** — Este menu\n\n"
            f"**`{prefix}about`** — Sobre o Luna Bot\n\n"
            f"**`{prefix}tutorial`** — Guia interativo do bot\n\n"
            f"**`{prefix}health`** — Status de integridade e latência\n\n"
        )
        .footer(f"Prefixo: {prefix}")
        .build()
    )


def _embed_geral(prefix: str, bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Geral", icon_url=_bot_avatar(bot))
        .description(
            f"**`{prefix}download`** — Download de vídeos e áudio\n"
            f"`{prefix}download <url>`\n\n"
        )
        .footer(f"Prefixo: {prefix}")
        .build()
    )


def _embed_comunidade(prefix: str, bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Comunidade", icon_url=_bot_avatar(bot))
        .description(
            f"**`{prefix}profile`** — Perfil individual\n\n"
            f"**`{prefix}leaderboard`** — Ranking do servidor\n\n"
            f"**`{prefix}server`** — Informações do servidor\n\n"
            f"**`{prefix}xp`** — Progresso de nível\n\n"
            f"**`{prefix}giveaway`** — Cria e gerencia sorteios\n\n"
            f"**`{prefix}notify`** — Agenda lembretes e notificações\n\n"
        )
        .footer(f"Prefixo: {prefix}")
        .build()
    )


def _embed_fun(prefix: str, bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Diversão", icon_url=_bot_avatar(bot))
        .description(
            f"**`Dados`** — Digite direto no chat\n"
            f"`d20`, `4d6`, `2d8`\n\n"
            f"**`{prefix}choose`** — Escolhe entre opções\n"
            f"`{prefix}choose pizza ! sushi`\n\n"
            f"**`{prefix}osu`** — Perfil de jogador do osu!\n\n"
            f"**`{prefix}steam`** — Informações da Steam\n\n"
            f"**`{prefix}minecraft`** — Status do servidor Minecraft\n\n"
            f"**`/mc-vincular`** — Vincular conta Minecraft\n\n"
        )
        .footer(f"Prefixo: {prefix}")
        .build()
    )


def _embed_rp(prefix: str, bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Roleplay & Ações", icon_url=_bot_avatar(bot))
        .description(
            f"**`{prefix}ship @user1 @user2`** — Compatibilidade entre membros\n\n"
            f"**`{prefix}jail @user`** — Prende um membro com foto atrás das grades\n\n"
            f"**Comandos de Ações (GIFs):**\n"
            f"`{prefix}kiss`, `{prefix}hug`, `{prefix}slap`, `{prefix}pat`, `{prefix}bite`, `{prefix}cuddle`, `{prefix}poke`, `{prefix}bonk`, `{prefix}tickle`, `{prefix}highfive`, `{prefix}punch`, `{prefix}wave`\n"
        )
        .footer(f"Prefixo: {prefix}")
        .build()
    )


def _embed_admin(prefix: str, bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Admin", icon_url=_bot_avatar(bot))
        .description(
            f"**`{prefix}prefix`** — Alterar prefixo\n\n"
            f"**`/logs-setup`** — Configurar canal de logs\n\n"
            f"**`{prefix}autorole`** — Cargos automáticos\n\n"
            f"**`{prefix}clear`** — Limpar mensagens\n\n"
            f"**`{prefix}xpconfig`** — Configuração de XP\n\n"
            f"**`{prefix}config`** — Painel de controle\n"
        )
        .footer(f"Admin • Prefixo: {prefix}")
        .build()
    )


def _embed_owner(prefix: str, bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .color(discord.Color(0xFF4444))
        .author(name="Luna Bot — Owner", icon_url=_bot_avatar(bot))
        .description(
            "**Esses comandos são exclusivos do operador do bot.**\n"
            "Nenhum outro usuário pode vê-los ou executá-los.\n\n"
            "**Auto-Update & Admin**\n"
            f"**`/backup`** — Realiza o backup do banco de dados\n"
            f"**`{prefix}update`** — Status do repositório Git\n"
            f"**`{prefix}update check`** — Verificar commits novos\n"
            f"**`{prefix}update now`** — Git pull + instalar deps + restart\n"
            f"**`{prefix}update log`** — Últimos commits do repo\n"
            f"**`{prefix}update auto on`** — Ativar auto-update\n"
            f"**`{prefix}update auto off`** — Desativar auto-update\n"
            f"**`{prefix}update auto channel #c`** — Canal de notificações"
        )
        .footer(f"Prefixo: {prefix} • Visível apenas para o dono do bot")
        .build()
    )


# ── View ──────────────────────────────────────────────────────


class HelpView(discord.ui.View):
    """Abas de navegação para o help."""

    def __init__(
        self,
        bot: commands.Bot,
        prefix: str,
        author_id: int,
        *,
        is_owner: bool = False,
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.prefix = prefix
        self.author_id = author_id
        self.is_owner = is_owner
        self.current = "fun"

        # Aba Owner só aparece se for o owner E modo dev ativo
        dev_mode = getattr(bot, "_dev_mode", False)
        if not (self.is_owner and dev_mode):
            self.remove_item(self.tab_owner)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    def _get_embed(self) -> discord.Embed:
        builders: dict[str, _EmbedFactory] = {
            "bot": _embed_bot,
            "geral": _embed_geral,
            "comunidade": _embed_comunidade,
            "fun": _embed_fun,
            "rp": _embed_rp,
            "admin": _embed_admin,
            "owner": _embed_owner,
        }

        builder = builders.get(self.current)
        if builder is None:
            self.current = "fun"
            builder = builders["fun"]

        return builder(self.prefix, self.bot)

    def _update_styles(self) -> None:
        """Destaca o botão da aba atual."""
        mapping: dict[str, discord.ui.Button] = {
            "bot": self.tab_bot,
            "geral": self.tab_geral,
            "comunidade": self.tab_comunidade,
            "fun": self.tab_fun,
            "rp": self.tab_rp,
            "admin": self.tab_admin,
        }

        for key, btn in mapping.items():
            btn.style = (
                discord.ButtonStyle.primary
                if key == self.current
                else discord.ButtonStyle.secondary
            )

    async def _switch(self, interaction: discord.Interaction, tab: str) -> None:
        self.current = tab
        self._update_styles()
        await interaction.response.edit_message(embed=self._get_embed(), view=self)

    # ── Row 0 — Abas principais ──────────────────────────────

    @discord.ui.button(
        label="Fun", emoji=BotEmojis.COMMON_GAMES, style=discord.ButtonStyle.primary, row=0
    )
    async def tab_fun(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._switch(interaction, "fun")

    @discord.ui.button(
        label="Geral", emoji=BotEmojis.COMMON_GENERAL, style=discord.ButtonStyle.secondary, row=0
    )
    async def tab_geral(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._switch(interaction, "geral")

    @discord.ui.button(
        label="Comunidade",
        emoji=BotEmojis.COMMON_USERS,
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def tab_comunidade(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._switch(interaction, "comunidade")

    # ── Row 1 — Abas secundárias ─────────────────────────────

    @discord.ui.button(
        label="RP",
        emoji=BotEmojis.COMMON_HEART,
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def tab_rp(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._switch(interaction, "rp")

    @discord.ui.button(
        label="Admin",
        emoji=BotEmojis.COMMON_ADMIN,
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def tab_admin(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._switch(interaction, "admin")

    @discord.ui.button(
        label="Bot", emoji=BotEmojis.COMMON_BOT, style=discord.ButtonStyle.secondary, row=1
    )
    async def tab_bot(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._switch(interaction, "bot")

    # ── Row 2 — Owner only (removido da view se não for owner) ─

    @discord.ui.button(
        label="Owner", emoji=BotEmojis.COMMON_OWNER, style=discord.ButtonStyle.danger, row=2
    )
    async def tab_owner(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        # Proteção extra: verificar ID mesmo que o botão esteja visível
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "Você não tem permissão para acessar esta aba.",
                ephemeral=True,
            )
            return

        await self._switch(interaction, "owner")

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]


# ── Cog ───────────────────────────────────────────────────────


class HelpCog(commands.Cog):
    """Menu de ajuda do bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="help", description="Lista de comandos disponíveis")
    async def help_cmd(self, ctx: commands.Context) -> None:
        config = await self.bot.container.guild_service.get_config(ctx.guild.id) if ctx.guild else None
        prefix = config.get("prefix", "!") if config else "!"

        is_owner = await self.bot.is_owner(ctx.author)

        view = HelpView(self.bot, prefix, ctx.author.id, is_owner=is_owner)
        embed = view._get_embed()
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
