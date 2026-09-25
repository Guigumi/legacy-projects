"""
Cog de tutorial — guia interativo de uso do bot.

Expõe o comando /tutorial (e !tutorial) com abas de navegação.
Também responde automaticamente quando o bot é mencionado.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from config.settings import BotEmojis, Separators
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder


# ── Helpers de avatar ─────────────────────────────────────────

def _bot_avatar(bot: commands.Bot) -> str:
    if bot.user is not None:
        return bot.user.display_avatar.url
    return ""


# ── Embeds por aba ────────────────────────────────────────────

def _embed_inicio(bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Guia de Início", icon_url=_bot_avatar(bot))
        .description(
            f"Olá! Eu sou a **Luna**, um bot de comunidade para Discord.\n\n"
            f"{Separators.title('O que eu faço?')}\n"
            f"Gerenço **perfis**, **XP**, **eventos** e muito mais "
            f"no seu servidor.\n\n"
            f"**Use os botões abaixo** para navegar pelas categorias e descobrir "
            f"tudo que você pode fazer comigo.\n\n"
            f"{Separators.title('Comandos Essenciais')}\n"
            f"`/tutorial` — Este guia\n"
            f"`/help` — Lista completa de comandos\n"
            f"`/about` — Sobre o Luna Bot\n"
            f"`/config` — Painel de configuração do servidor\n"
        )
        .footer("Navegue pelas abas para ver cada categoria")
        .build()
    )


def _embed_configuracao(bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Configuração", icon_url=_bot_avatar(bot))
        .description(
            f"{Separators.title('Primeiros Passos')}\n"
            f"Antes de tudo, um admin deve abrir o painel de controle:\n\n"
            f"**`/config`** — Abre o painel com todos os módulos\n"
            f"{BotEmojis.COMMON_TOOLS} Ative/desative funcionalidades por aqui.\n\n"
            f"{Separators.title('Boas-Vindas e Despedida')}\n"
            f"**`/welcome`** — Configura mensagens de entrada e saída\n"
            f"{BotEmojis.COMMON_JOIN} Escolha o canal, customize o texto, imagens e cor.\n\n"
            f"{Separators.title('Cargos Automáticos')}\n"
            f"**`/autorole`** — Configura cargos automáticos para novos membros\n"
            f"Suporta: Imediato, Timer, Botão ou Reação.\n\n"
            f"{Separators.title('Prefixo')}\n"
            f"**`/prefix`** ou **`!prefix <novo>`** — Altera o prefixo de texto do bot\n"
            f"Padrão: `!`\n"
        )
        .footer("Configure esses itens para uma experiência completa")
        .build()
    )


def _embed_perfil_xp(bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Perfil & XP", icon_url=_bot_avatar(bot))
        .description(
            f"{Separators.title('Perfil')}\n"
            f"**`/profile`** ou **`!profile`** — Veja seu perfil ou o de outro usuário\n"
            f"`!profile @usuário` — Perfil de outro membro\n\n"
            f"{Separators.title('XP e Níveis')}\n"
            f"**`/xp`** — Veja seu progresso de XP e nível atual\n"
            f"XP é ganho automaticamente ao enviar mensagens e entrar em canais de voz.\n\n"
            f"{Separators.title('Ranking')}\n"
            f"**`/leaderboard`** — Ranking do servidor\n"
            f"Abas: Mensagens, Voz e XP/Nível. Navegação por páginas.\n\n"
            f"{Separators.title('Configurar XP (Admin)')}\n"
            f"**`/xpconfig`** — Painel completo de configuração de XP\n"
            f"Defina multiplicadores, canais ignorados, cargos por nível e mais.\n"
        )
        .footer("Ganhe XP participando ativamente no servidor")
        .build()
    )


def _embed_diversao(bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Diversão", icon_url=_bot_avatar(bot))
        .description(
            f"{Separators.title('Dados no Chat')}\n"
            f"Digite diretamente: `d20`, `4d6`, `2d8+5`\n"
            f"Sem prefixo, só escreva a notação de dados!\n\n"
            f"{Separators.title('osu!')}\n"
            f"**`/osu`** ou **`!osu <usuário>`** — Perfil de jogador do osu!\n"
            f"Suporta: Standard, Taiko, Catch e Mania.\n\n"
            f"{Separators.title('Steam')}\n"
            f"**`!steam <usuário>`** — Informações de perfil da Steam\n\n"
            f"{Separators.title('Minecraft')}\n"
            f"**`/minecraft`** — Status do servidor Minecraft vinculado\n"
            f"**`/mc-vincular`** — Vincular sua conta Minecraft\n\n"
            f"{Separators.title('Outros')}\n"
            f"**`!choose <op1> ! <op2>`** — Escolhe entre opções aleatoriamente\n"
            f"**`!download <url>`** — Download de vídeo ou áudio\n"
        )
        .footer("Divirta-se com os comandos de entretenimento")
        .build()
    )


def _embed_admin(bot: commands.Bot) -> discord.Embed:
    return (
        EmbedBuilder.default()
        .author(name="Luna Bot — Admin", icon_url=_bot_avatar(bot))
        .description(
            f"{Separators.title('Moderação')}\n"
            f"**`!clear <n>`** — Apaga as últimas N mensagens do canal\n\n"
            f"{Separators.title('Logs')}\n"
            f"**`/logs-setup`** — Configura o canal onde os logs do servidor são enviados\n"
            f"Eventos registrados: entradas, saídas, banimentos, edições e exclusões.\n\n"
            f"{Separators.title('Sorteios')}\n"
            f"**`/giveaway`** — Cria e gerencia sorteios\n"
            f"Suporte a reroll, cancelamento e duração personalizada.\n\n"
            f"{Separators.title('Notificações')}\n"
            f"**`/notify`** — Configura alertas de transmissões ao vivo\n\n"
            f"{Separators.title('Servidor')}\n"
            f"**`/server`** — Informações detalhadas do servidor\n"
        )
        .footer("Comandos de admin requerem permissões de administrador")
        .build()
    )


# ── View ──────────────────────────────────────────────────────

_TAB_LABELS: dict[str, str] = {
    "inicio": "Início",
    "config": "Configuração",
    "perfil": "Perfil & XP",
    "diversao": "Diversão",
    "admin": "Admin",
}


class TutorialView(discord.ui.View):
    """Abas de navegação do tutorial."""

    def __init__(self, bot: commands.Bot, author_id: int) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.author_id = author_id
        self.current = "inicio"
        self._update_styles()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem iniciou o comando pode navegar no tutorial."
            ).build()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    def _get_embed(self) -> discord.Embed:
        factories = {
            "inicio": _embed_inicio,
            "config": _embed_configuracao,
            "perfil": _embed_perfil_xp,
            "diversao": _embed_diversao,
            "admin": _embed_admin,
        }
        factory = factories.get(self.current, _embed_inicio)
        return factory(self.bot)

    def _update_styles(self) -> None:
        buttons: dict[str, discord.ui.Button] = {
            "inicio": self.tab_inicio,
            "config": self.tab_config,
            "perfil": self.tab_perfil,
            "diversao": self.tab_diversao,
            "admin": self.tab_admin,
        }
        for key, btn in buttons.items():
            btn.style = (
                discord.ButtonStyle.primary
                if key == self.current
                else discord.ButtonStyle.secondary
            )

    async def _switch(self, interaction: discord.Interaction, tab: str) -> None:
        self.current = tab
        self._update_styles()
        await interaction.response.edit_message(embed=self._get_embed(), view=self)

    # ── Row 0 ────────────────────────────────────────────────

    @discord.ui.button(label="Início", emoji=BotEmojis.COMMON_SPARKLES, style=discord.ButtonStyle.primary, row=0)
    async def tab_inicio(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._switch(interaction, "inicio")

    @discord.ui.button(label="Configuração", emoji=BotEmojis.COMMON_TOOLS, style=discord.ButtonStyle.secondary, row=0)
    async def tab_config(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._switch(interaction, "config")

    @discord.ui.button(label="Perfil & XP", emoji=BotEmojis.COMMON_PROFILE, style=discord.ButtonStyle.secondary, row=0)
    async def tab_perfil(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._switch(interaction, "perfil")

    # ── Row 1 ────────────────────────────────────────────────

    @discord.ui.button(label="Diversão", emoji=BotEmojis.COMMON_GAMES, style=discord.ButtonStyle.secondary, row=1)
    async def tab_diversao(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._switch(interaction, "diversao")

    @discord.ui.button(label="Admin", emoji=BotEmojis.COMMON_ADMIN, style=discord.ButtonStyle.secondary, row=1)
    async def tab_admin(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._switch(interaction, "admin")

    @discord.ui.button(label="Fechar", emoji=BotEmojis.STATUS_DISABLED, style=discord.ButtonStyle.danger, row=1)
    async def btn_close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]


# ── Cog ───────────────────────────────────────────────────────

class TutorialCog(commands.Cog):
    """Tutorial interativo do bot — ativado por comando ou menção."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="tutorial", description="Guia interativo de como usar o Luna Bot")
    async def tutorial_cmd(self, ctx: commands.Context) -> None:
        view = TutorialView(self.bot, ctx.author.id)
        embed = view._get_embed()
        await ctx.send(embed=embed, view=view)




async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TutorialCog(bot))
