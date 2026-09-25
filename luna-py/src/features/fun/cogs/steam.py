"""
Cog Steam — busca informações de jogos na Steam.
Uso: !steam <nome do jogo>
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from config.settings import BotEmojis


class SteamView(discord.ui.View):
    """View interativa para navegação de informações de um jogo Steam."""

    def __init__(
        self,
        bot: LunaBot,
        info: dict,
        author_id: int,
        screenshots: list[str] | None = None,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.info = info
        self.author_id = author_id
        self.screenshots = screenshots or []
        self.current_ss = -1  # -1 significa mostrar o header_image original

        # Adicionar botão de link direto
        self.add_item(discord.ui.Button(label="Abrir na Steam", url=info["url"], row=0))

        # Se não houver screenshots, desativar o botão
        if not self.screenshots:
            self.ss_btn.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Apenas quem usou o comando pode interagir.", ephemeral=True
            )
            return False
        return True

    def _build_embed(self) -> discord.Embed:
        info = self.info
        
        # Cor baseada em promoção
        color = discord.Color(0x4c6b22) if info["discount"] > 0 else discord.Color(0x1B2838)
        
        # Título com badge de desconto
        title = info["name"]
        if info["discount"] > 0:
            title = f"[{info['discount']}% OFF] {title}"
        title = f"{BotEmojis.STEAM_LOGO} {title}"

        # Preço
        if info["discount"] > 0:
            price_str = f"~~{info['original_price']}~~ **{info['price']}**"
        else:
            price_str = f"**{info['price']}**"

        # Embed base
        embed = (
            EmbedBuilder.default()
            .color(color)
            .title(title)
            .description(f"{info['synopsis'] or '*Sem descrição disponível.*'}")
            .field(f"{BotEmojis.COMMON_MONEY} Preço", price_str, inline=True)
            .field(f"{BotEmojis.COMMON_STAR} Avaliação", info["review"], inline=True)
            .field(f"{BotEmojis.COMMON_TROPHY} Conquistas", f"**{info['achievements']}**" if info["achievements"] > 0 else "—", inline=True)
            .field(f"{BotEmojis.COMMON_USERS} Jogando agora", f"**{info['player_count']:,}**".replace(",", "."), inline=True)
            .field(f"{BotEmojis.COMMON_LIST} Gêneros", ", ".join(info["genres"]) if info["genres"] else "—", inline=True)
            .field(f"{BotEmojis.COMMON_TOOLS} Desenvolvedora", info["developers"], inline=True)
            .footer(f"Steam • {info['name']}")
            .timestamp()
        )

        # Imagem (header ou screenshot atual)
        if self.current_ss == -1:
            embed.image(info["header_image"])
        else:
            embed.image(self.screenshots[self.current_ss])
            embed.footer(f"Screenshot {self.current_ss + 1}/{len(self.screenshots)} • {info['name']}")

        return embed.build()

    @discord.ui.button(label="Próxima Screenshot", emoji=BotEmojis.COMMON_CAMERA, style=discord.ButtonStyle.secondary)
    async def ss_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_ss = (self.current_ss + 1) % len(self.screenshots)
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


class SteamCog(commands.Cog):
    """Comando para buscar jogos na Steam."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service = bot.container.steam_service

    @commands.hybrid_command(
        name="steam",
        description="Busca informações de um jogo na Steam",
    )
    @app_commands.describe(game="Nome do jogo para buscar")
    async def steam(self, ctx: commands.Context, *, game: str) -> None:
        if not hasattr(self.bot.container, "steam_service") or self.bot.container.steam_service is None:
            embed = EmbedBuilder.error_internal(
                "A integração com a Steam não está configurada."
            ).build()
            await ctx.send(embed=embed)
            return

        await ctx.defer()

        info = await self.service.get_full_game_info(game)
        if not info:
            embed = EmbedBuilder.error_user(f"Não encontrei `{game}` na Steam.").build()
            await ctx.send(embed=embed)
            return

        # Buscar screenshots
        screenshots = await self.service.get_screenshots(info["appid"])

        view = SteamView(self.bot, info, ctx.author.id, screenshots)
        embed = view._build_embed()
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SteamCog(bot))
