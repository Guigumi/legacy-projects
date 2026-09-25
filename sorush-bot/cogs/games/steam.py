import discord
from discord.ext import commands
from discord.ui import View, Button
import aiohttp
import asyncio
import logging
from typing import Optional
from datetime import datetime

from config import Colors

logger = logging.getLogger(__name__)

STEAM_COLOR = 0x171A21  # Steam dark color
STEAM_ACCENT = 0x66C0F4  # Steam blue
STEAM_LOGO = "https://store.steampowered.com/favicon.ico"

class SteamGameView(View):
    """View with buttons for the game"""
    
    def __init__(self, app_id: int, game_name: str):
        super().__init__(timeout=300)
        
        # Botão para abrir na Steam
        self.add_item(Button(
            label="🛒 Ver na Steam",
            style=discord.ButtonStyle.link,
            url=f"https://store.steampowered.com/app/{app_id}"
        ))
        
        # Botão para SteamDB
        self.add_item(Button(
            label="📊 SteamDB",
            style=discord.ButtonStyle.link,
            url=f"https://steamdb.info/app/{app_id}"
        ))

        # Botão para ProtonDB
        self.add_item(Button(
            label="🐧 ProtonDB",
            style=discord.ButtonStyle.link,
            url=f"https://protondb.com/app/{app_id}"
        ))
class Steam(commands.Cog):
    """🎮 Commands to search for games on Steam"""
    
    STEAM_SEARCH_URL = "https://steamcommunity.com/actions/SearchApps"
    STEAM_API_URL = "https://store.steampowered.com/api/appdetails"
    STEAM_STORE_URL = "https://store.steampowered.com/app"
    PROTONDB_API = "https://protondb.com/api/v1/reports/latest/app"
    # Only ProtonDB is used for Linux compatibility info
    TIMEOUT = 8

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self) -> None:
        """Initializes the HTTP session"""
        self._session = aiohttp.ClientSession()

    async def cog_unload(self) -> None:
        """Closes the HTTP session"""
        if self._session:
            await self._session.close()

    async def _search_game(self, game_name: str) -> Optional[int]:
        """Searches for the game's App ID on Steam"""
        try:
            async with self._session.get(
                f"{self.STEAM_SEARCH_URL}/{game_name}",
                timeout=self.TIMEOUT
            ) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                return data[0]['appid'] if data else None
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout searching for game: {game_name}")
        except (aiohttp.ClientError, IndexError, KeyError) as e:
            logger.error(f"Error searching Steam game '{game_name}': {e}")
        return None

    async def _fetch_game_details(self, app_id: int) -> Optional[dict]:
        """Fetches game details using the App ID"""
        try:
            async with self._session.get(
                self.STEAM_API_URL,
                params={'appids': app_id, 'l': 'portuguese', 'cc': 'br'},
                timeout=self.TIMEOUT
            ) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                if str(app_id) not in data:
                    return None
                
                if not data[str(app_id)].get('success'):
                    return None
                
                return data[str(app_id)].get('data')
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching Steam game details for app_id: {app_id}")
        except (aiohttp.ClientError, KeyError) as e:
            logger.error(f"Error fetching Steam game details for app_id {app_id}: {e}")
        return None

    async def _fetch_protondb_info(self, app_id: int) -> Optional[dict]:
        """Fetches ProtonDB compatibility info for the game"""
        try:
            async with self._session.get(
                f"{self.PROTONDB_API}/{app_id}",
                timeout=self.TIMEOUT
            ) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                return data
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching ProtonDB info for app_id: {app_id}")
        except (aiohttp.ClientError, KeyError) as e:
            logger.error(f"Error fetching ProtonDB info for app_id {app_id}: {e}")
        return None

    # ======================== EMBED BUILDERS ========================

    def _format_price(self, game_data: dict) -> str:
        """Formats the game price"""
        if price_data := game_data.get('price_overview'):
            price = price_data.get('final_formatted', 'Grátis')
            discount = price_data.get('discount_percent', 0)
            if discount > 0:
                original = price_data.get('initial_formatted', price)
                return f"~~{original}~~ **{price}** `-{discount}%`"
            return f"**{price}**"
        
        if game_data.get('is_free'):
            return "**Grátis para Jogar** 🎉"
        return "Preço indisponível"

    def _get_score_display(self, score: int) -> str:
        """Returns visual display of the score"""
        if score >= 75:
            return f"🟢 **{score}**/100"
        elif score >= 50:
            return f"🟡 **{score}**/100"
        return f"🔴 **{score}**/100"

    def _format_protondb_status(self, protondb_data: Optional[dict]) -> str:
        """Formats ProtonDB compatibility status"""
        if not protondb_data:
            return "Não disponível"
        
        rating = protondb_data.get('rating', 'unknown')
        
        status_map = {
            'platinum': '🟣 **Platinum** - Roda perfeito',
            'gold': '🟡 **Gold** - Roda bem com pequenos ajustes',
            'silver': '🟠 **Silver** - Roda, mas com problemas',
            'bronze': '🔴 **Bronze** - Roda mas precisa de config',
            'borked': '⚫ **Borked** - Não roda'
        }
        
        return status_map.get(rating, 'Não identificado')
 
        
    def _create_game_embed(self, game_data: dict, app_id: int, protondb_data: Optional[dict] = None) -> discord.Embed:
        """Creates embed with game information"""
        
        title = game_data.get('name', 'Desconhecido')
        short_desc = game_data.get('short_description', '')
        
        # Limitar descrição
        if len(short_desc) > 150:
            short_desc = short_desc[:147] + "..."
        
        embed = discord.Embed(title=f"🎮 {title}", color=STEAM_ACCENT, url=f"{self.STEAM_STORE_URL}/{app_id}")
        
        if short_desc:
            embed.description = f"```{short_desc}```"

        # ━━━━ PRICE ━━━━
        price_text = self._format_price(game_data)
        embed.add_field(name="▸ Preço", value=price_text, inline=True)
        
        # ━━━━ RELEASE ━━━━
        release_date = game_data.get('release_date', {}).get('date', 'N/A')
        embed.add_field(name="▸ Lançamento", value=f"`{release_date}`", inline=True)

        # ━━━━ PLATFORMS ━━━━
        if platforms := game_data.get('platforms'):
            platform_icons = []
            if platforms.get('windows'):
                platform_icons.append("🪟 Windows")
            if platforms.get('mac'):
                platform_icons.append("🍎 Mac")
            if platforms.get('linux'):
                platform_icons.append("🐧 Linux")
            
            if platform_icons:
                embed.add_field(
                    name="▸ Plataformas",
                    value="\n".join(platform_icons),
                    inline=True
                )
            
            # (ProtonDB info will be shown in Detalhes)

        # ━━━━ DETAILS ━━━━
        extras = []
        
        if achievements := game_data.get('achievements'):
            total = achievements.get('total', 0)
            if total > 0:
                extras.append(f"🏆 {total} conquistas")
        
        if developers := game_data.get('developers'):
            extras.append(f"👨‍💻 {developers[0]}")
        
        # Adicionar ProtonDB aos detalhes quando disponível
        if protondb_data:
            summary = protondb_data.get('summary') or protondb_data.get('compatibility') or ''
            rating = self._format_protondb_status(protondb_data)
            extras.append(f"🐧 ProtonDB: {rating}")
            if summary:
                # limitar tamanho do resumo para não estourar o embed
                short = summary if len(summary) <= 200 else summary[:197] + '...'
                extras.append(f"▸ {short}")

        if extras:
            embed.add_field(
                name="▸ Detalhes",
                value="\n".join(extras),
                inline=True
            )

        # ━━━━ IMAGE ━━━━
        if header_image := game_data.get('header_image'):
            embed.set_image(url=header_image)

        embed.set_footer(
            text="Steam",
            icon_url=STEAM_LOGO
        )
        
        return embed

    # ======================== COMMANDS ========================

    @commands.hybrid_command(name="steam", description="Busca um jogo na Steam")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def steam_game(self, ctx: commands.Context, *, game_name: Optional[str] = None):
        """
        Searches for game information on Steam
        Usage: s!steam <game name>
        Example: s!steam Portal 2
        """
        
        if not game_name:
            embed = discord.Embed(title="🎮 Steam", color=STEAM_ACCENT)
            embed.add_field(name="▸ Uso", value="```s!steam <jogo>```", inline=True)
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Validar comprimento do nome
        if len(game_name) < 2:
            embed = discord.Embed(title="❌ Erro", description="O nome do jogo deve ter pelo menos 2 caracteres", color=Colors.ERROR)
            return await ctx.send(embed=embed, ephemeral=True)

        # Loading embed
        loading_embed = discord.Embed(title="🔍 Buscando...", description=f"Procurando **{game_name}** na Steam", color=STEAM_COLOR)
        loading = await ctx.send(embed=loading_embed)

        try:
            # Search App ID
            app_id = await self._search_game(game_name)
            if not app_id:
                error_embed = discord.Embed(
                    title="🎮 não achei",
                    description=f"não encontrei **{game_name}** na Steam\ntenta escrever de outro jeito",
                    color=Colors.WARNING
                )
                return await loading.edit(embed=error_embed)

            # Fetch details
            game_data = await self._fetch_game_details(app_id)
            if not game_data:
                error_embed = discord.Embed(
                    title="🎮 ops",
                    description="não consegui carregar os detalhes\ntenta de novo",
                    color=Colors.WARNING
                )
                return await loading.edit(embed=error_embed)

            # Create embed and view
            # Fetch ProtonDB info (if Linux is supported)
            protondb_data = None
            platforms = game_data.get('platforms', {})
            if platforms.get('linux'):
                protondb_data = await self._fetch_protondb_info(app_id)

            # Create embed and view (ProtonDB shown in Detalhes)
            embed = self._create_game_embed(game_data, app_id, protondb_data)
            view = SteamGameView(app_id, game_data.get('name', game_name))
            
            await loading.edit(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error in steam command for game '{game_name}': {e}")
            error_embed = discord.Embed(
                title="😅 ops",
                description="algo deu errado, tenta de novo",
                color=Colors.ERROR
            )
            await loading.edit(embed=error_embed)

    @steam_game.error
    async def steam_game_error(self, ctx: commands.Context, error: Exception):
        """Handles command errors"""
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏳ calma",
                description=f"espera **{error.retry_after:.1f}s**",
                color=Colors.PRIMARY
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            logger.error(f"Unhandled error in steam command: {error}")
            embed = discord.Embed(
                title="😅 ops",
                description="algo deu errado",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)

# ======================== SETUP ========================

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Steam(bot))
