"""
osu! Statistics System - API v2
Fetches player information using the osu! API v2 (OAuth2)
"""
import os
import logging
import aiohttp
from aiohttp import ClientTimeout
import discord
from discord.ext import commands
from discord.ui import View, Select
from typing import Optional, Dict, List
from datetime import datetime
import asyncio

from config import Colors

logger = logging.getLogger(__name__)

OSU_CLIENT_ID = os.getenv("OSU_CLIENT_ID")
OSU_CLIENT_SECRET = os.getenv("OSU_CLIENT_SECRET")
OSU_API_BASE = "https://osu.ppy.sh/api/v2"
OSU_TOKEN_URL = "https://osu.ppy.sh/oauth/token"
API_TIMEOUT = ClientTimeout(total=15)
OSU_PINK = 0xFF66AA

MODES = {
    "osu": {"name": "osu!", "emoji": "🎯", "id": 0},
    "taiko": {"name": "Taiko", "emoji": "🥁", "id": 1},
    "fruits": {"name": "Catch", "emoji": "🍎", "id": 2},
    "mania": {"name": "Mania", "emoji": "🎹", "id": 3},
}

def fmt_num(n: float) -> str:
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return f"{n:,.0f}"

def fmt_time(seconds: int) -> str:
    h = seconds // 3600
    return f"{h // 24}d {h % 24}h" if h >= 24 else f"{h}h"

def level_bar(level: float) -> str:
    p = (level % 1) * 100
    return f"{'▰' * int(p/10)}{'▱' * (10 - int(p/10))} {p:.0f}%"

def rank_emoji(rank: str) -> str:
    return {"XH": "🏆", "X": "🥇", "SH": "🥈", "S": "🥈", "A": "🟢", "B": "🔵", "C": "🟣", "D": "🔴"}.get(rank, "❓")

class OsuAPIv2:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = None
        self.token_expires: float = 0
    
    async def _session(self) -> aiohttp.ClientSession:
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_token(self) -> Optional[str]:
        """Gets OAuth2 token (Client Credentials)"""
        if self.token and datetime.now().timestamp() < self.token_expires:
            return self.token
        
        session = await self._session()
        data = {
            "client_id": OSU_CLIENT_ID,
            "client_secret": OSU_CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "public"
        }
        
        try:
            async with session.post(OSU_TOKEN_URL, data=data, timeout=API_TIMEOUT) as r:
                if r.status == 200:
                    resp = await r.json()
                    self.token = resp.get("access_token")
                    self.token_expires = datetime.now().timestamp() + resp.get("expires_in", 3600) - 60
                    return self.token
        except aiohttp.ClientError as e:
            logger.error(f"Error getting osu! OAuth token: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting osu! token: {e}")
        return None
    
    async def _request(self, endpoint: str, params: Optional[dict] = None) -> Optional[Dict]:
        """Makes authenticated request to API v2"""
        token = await self.get_token()
        if not token:
            return None
        
        session = await self._session()
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            async with session.get(f"{OSU_API_BASE}/{endpoint}", headers=headers, params=params, timeout=API_TIMEOUT) as r:
                if r.status == 200:
                    return await r.json()
                elif r.status == 404:
                    logger.debug(f"osu! API endpoint not found: {endpoint}")
                else:
                    logger.warning(f"osu! API returned status {r.status} for {endpoint}")
        except aiohttp.ClientError as e:
            logger.error(f"osu! API request error for {endpoint}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in osu! API request: {e}")
        return None
    
    async def get_user(self, username: str, mode: str = "osu") -> Optional[Dict]:
        """Fetches user data"""
        return await self._request(f"users/{username}/{mode}", {"key": "username"})
    
    async def get_user_scores(self, user_id: int, mode: str = "osu", score_type: str = "best", limit: int = 5) -> List[Dict]:
        """Fetches user scores (best, firsts, recent)"""
        data = await self._request(f"users/{user_id}/scores/{score_type}", {"mode": mode, "limit": limit})
        return data if isinstance(data, list) else []
    
    async def get_all_modes(self, username: str) -> Dict[str, Optional[Dict]]:
        """Fetches data for all modes in parallel"""
        tasks = [self.get_user(username, mode) for mode in MODES.keys()]
        results = await asyncio.gather(*tasks)
        return dict(zip(MODES.keys(), results))

# ======================== VIEWS ========================

class ModeSelect(Select):
    def __init__(self, cog: "Osu", username: str, all_data: Dict, current: str):
        self.cog = cog
        self.username = username
        self.all_data = all_data
        
        options = []
        for mode, info in MODES.items():
            data = all_data.get(mode)
            if data and data.get('statistics', {}).get('pp'):
                pp = data['statistics']['pp']
                desc = f"{pp:,.0f}pp"
            else:
                desc = "Sem dados"
            options.append(discord.SelectOption(
                label=info["name"], value=mode, emoji=info["emoji"],
                description=desc, default=(mode == current)
            ))
        
        super().__init__(placeholder="Modo de jogo", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        mode = self.values[0]
        data = self.all_data.get(mode)
        
        if not data or not data.get('statistics', {}).get('pp'):
            return await interaction.response.send_message(
                f"❌ Sem dados em **{MODES[mode]['name']}**", ephemeral=True
            )
        
        best = await self.cog.api.get_user_scores(data['id'], mode, "best", 5)
        embed = self.cog.make_embed(data, mode, best)
        view = OsuView(self.cog, self.username, self.all_data, mode)
        await interaction.response.edit_message(embed=embed, view=view)


class OsuView(View):
    def __init__(self, cog: "Osu", username: str, all_data: Dict, current: str):
        super().__init__(timeout=120)
        self.add_item(ModeSelect(cog, username, all_data, current))
        
        data = all_data.get(current)
        if data:
            self.add_item(discord.ui.Button(
                label="Perfil", style=discord.ButtonStyle.link,
                url=f"https://osu.ppy.sh/users/{data['id']}", emoji="🔗"
            ))

# ======================== COG ========================

class Osu(commands.Cog):
    """🎮 Comandos do osu!"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = OsuAPIv2()
    
    async def cog_unload(self):
        await self.api.close()
    
    def best_mode(self, all_data: Dict) -> str:
        best, best_pp = "osu", 0.0
        for mode, data in all_data.items():
            if data and data.get('statistics', {}).get('pp'):
                pp = float(data['statistics']['pp'])
                if pp > best_pp:
                    best_pp, best = pp, mode
        return best
    
    def make_embed(self, data: Dict, mode: str, best: List[Dict]) -> discord.Embed:
        info = MODES[mode]
        name = data.get('username', '?')
        country = data.get('country_code', '??')
        stats = data.get('statistics', {})
        
        embed = discord.Embed(
            title=f"🎮 {name}",
            url=f"https://osu.ppy.sh/users/{data['id']}/{mode}",
            color=OSU_PINK
        )
        
        # Avatar
        avatar = data.get('avatar_url', '')
        if avatar:
            embed.set_thumbnail(url=avatar)
        
        # ━━━━ RANK ━━━━
        global_rank = stats.get('global_rank') or 0
        country_rank = stats.get('country_rank') or 0
        
        rank_text = f"Global: `#{fmt_num(global_rank)}`\n"
        rank_text += f"Regional: `#{fmt_num(country_rank)}` :flag_{country.lower()}:"
        embed.add_field(name="▸ Rank", value=rank_text, inline=True)
        
        # ━━━━ PP & ACC ━━━━
        pp = stats.get('pp', 0)
        acc = stats.get('hit_accuracy', 0)
        max_combo = stats.get('maximum_combo', 0)
        
        pp_text = f"PP: `{pp:,.0f}pp`\n"
        pp_text += f"Acc: `{acc:.2f}%`\n"
        pp_text += f"Combo: `{fmt_num(max_combo)}x`"
        embed.add_field(name="▸ Stats", value=pp_text, inline=True)
        
        # ━━━━ LEVEL ━━━━
        level_data = stats.get('level', {})
        level = level_data.get('current', 0)
        level_progress = level_data.get('progress', 0)
        play_count = stats.get('play_count', 0)
        play_time = stats.get('play_time', 0)
        
        level_text = f"Lv: `{level}` ({level_progress}%)\n"
        level_text += f"Plays: `{fmt_num(play_count)}`\n"
        level_text += f"Tempo: `{fmt_time(play_time)}`"
        embed.add_field(name="▸ Progresso", value=level_text, inline=True)
        
        # ━━━━ GRADES ━━━━
        grades = stats.get('grade_counts', {})
        ssh = grades.get('ssh', 0)
        ss = grades.get('ss', 0)
        sh = grades.get('sh', 0)
        s = grades.get('s', 0)
        a = grades.get('a', 0)
        
        grades_text = f"🏆 `{ssh + ss}` • 🥈 `{sh + s}` • 🟢 `{a}`"
        embed.add_field(name="▸ Ranks", value=grades_text, inline=False)
        
        # ━━━━ TOP PLAYS ━━━━
        if best:
            top_text = ""
            for i, score in enumerate(best[:3], 1):
                beatmap = score.get('beatmapset', {})
                title = beatmap.get('title', '?')[:20]
                score_pp = score.get('pp', 0)
                rank = score.get('rank', '?')
                top_text += f"`{i}.` {rank_emoji(rank)} **{score_pp:.0f}pp** - {title}\n"
            
            embed.add_field(name="▸ Top Plays", value=top_text, inline=False)
        
        # ━━━━ FOOTER ━━━━
        embed.set_footer(text=f"{info['emoji']} {info['name']} • osu!")
        
        return embed
    
    @commands.hybrid_command(name="osu", description="🎮 Ver perfil do osu!")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def osu_cmd(self, ctx: commands.Context, *, username: Optional[str] = None):
        if not OSU_CLIENT_ID or not OSU_CLIENT_SECRET:
            embed = discord.Embed(title="🎮 osu!", description="API não configurada", color=Colors.WARNING)
            return await ctx.send(embed=embed, ephemeral=True)
        
        if not username:
            embed = discord.Embed(title="🎮 osu!", color=OSU_PINK)
            embed.add_field(name="▸ Uso", value="```s!osu <username>```", inline=True)
            embed.add_field(name="▸ Exemplo", value="```s!osu mrekk```", inline=True)
            return await ctx.send(embed=embed, ephemeral=True)
        
        msg = await ctx.send(f"🔍 Buscando **{username}**...")
        
        try:
            all_data = await self.api.get_all_modes(username)
            
            if not any(all_data.values()):
                embed = discord.Embed(title="🎮 não achei", description=f"usuário **{username}** não encontrado", color=Colors.WARNING)
                return await msg.edit(content=None, embed=embed)
            
            mode = self.best_mode(all_data)
            data = all_data[mode]
            
            if not data:
                embed = discord.Embed(title="🎮 não achei", description=f"usuário **{username}** não encontrado", color=Colors.WARNING)
                return await msg.edit(content=None, embed=embed)
            
            best = await self.api.get_user_scores(data['id'], mode, "best", 5)
            embed = self.make_embed(data, mode, best)
            view = OsuView(self, username, all_data, mode)
            await msg.edit(content=None, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error in osu command for user {username}: {e}")
            embed = discord.Embed(title="😅 ops", description="algo deu errado, tenta de novo", color=Colors.ERROR)
            await msg.edit(content=None, embed=embed)
    
    @osu_cmd.error
    async def osu_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(title="⏳ calma", description=f"espera **{error.retry_after:.1f}s**", color=Colors.PRIMARY)
            await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Osu(bot))
