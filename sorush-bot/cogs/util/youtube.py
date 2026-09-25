"""
YouTube Video Search System
Searches and displays detailed video information
"""
import logging
import discord
from discord.ext import commands
from discord.ui import View, Button
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime
from typing import Optional, Dict, Any, List
import os
import asyncio
from dotenv import load_dotenv
from async_lru import alru_cache

from config import Colors

logger = logging.getLogger(__name__)

load_dotenv()

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_COLOR = 0xFF0000
YOUTUBE_ICON = "https://www.youtube.com/favicon.ico"
YOUTUBE_LOGO = "https://www.youtube.com/s/desktop/7449ebf7/img/favicon_144x144.png"

def format_number(number: int) -> str:
    """Formats number with suffixes (M, K, B)"""
    try:
        if number >= 1_000_000_000:
            return f"{number/1_000_000_000:.1f}B"
        elif number >= 1_000_000:
            return f"{number/1_000_000:.1f}M"
        elif number >= 1_000:
            return f"{number/1_000:.1f}K"
        return f"{number:,}"
    except (TypeError, ValueError):
        return "0"

def format_duration(duration: str) -> str:
    """Converts ISO 8601 duration to HH:MM:SS"""
    try:
        duration = duration.replace('PT', '')
        hours = minutes = seconds = '0'
        
        if 'H' in duration:
            hours, duration = duration.split('H')
        if 'M' in duration:
            minutes, duration = duration.split('M')
        if 'S' in duration:
            seconds = duration.replace('S', '')
        
        if hours != '0':
            return f"{hours}:{minutes.zfill(2)}:{seconds.zfill(2)}"
        return f"{minutes}:{seconds.zfill(2)}"
    except Exception:
        return "00:00"

def format_date(date: datetime) -> str:
    """Formats publication date"""
    now = datetime.utcnow()
    delta = now - date
    
    if delta.days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            return "Há poucos minutos"
        return f"Há {hours}h"
    elif delta.days == 1:
        return "Ontem"
    elif delta.days < 7:
        return f"Há {delta.days} dias"
    elif delta.days < 30:
        weeks = delta.days // 7
        return f"Há {weeks} semana{'s' if weeks > 1 else ''}"
    elif delta.days < 365:
        months = delta.days // 30
        return f"Há {months} {'meses' if months > 1 else 'mês'}"
    else:
        years = delta.days // 365
        return f"Há {years} ano{'s' if years > 1 else ''}"

def truncate_text(text: str, limit: int = 200) -> str:
    """Truncates text keeping whole words"""
    if len(text) <= limit:
        return text
    return text[:limit-3].rsplit(' ', 1)[0] + "..."


class VideoView(View):
    """View with video action buttons"""
    
    def __init__(self, video_url: str, channel_url: str):
        super().__init__(timeout=300)
        
        # Watch button
        self.add_item(Button(
            label="▶️ Assistir",
            style=discord.ButtonStyle.link,
            url=video_url
        ))
        
        # Channel button
        self.add_item(Button(
            label="📺 Canal",
            style=discord.ButtonStyle.link,
            url=channel_url
        ))

# ======================== YOUTUBE COG ========================

class Youtube(commands.Cog):
    """🎬 Cog for searching YouTube videos"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not YOUTUBE_API_KEY:
            raise ValueError("❌ YouTube API key não encontrada em .env")
        self.youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

    @alru_cache(maxsize=32, ttl=300)
    async def _search_videos(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Searches for videos on YouTube (Cached)"""
        return await self.bot.loop.run_in_executor(
            None,
            lambda: self._search_videos_sync(query, max_results)
        )

    def _search_videos_sync(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Searches for videos on YouTube (Synchronous)"""
        try:
            search = self.youtube.search().list(
                part="snippet",
                q=query,
                type="video",
                maxResults=max_results,
                relevanceLanguage="pt"
            ).execute()

            if not search.get('items'):
                return []

            # Get video IDs
            video_ids = [item['id']['videoId'] for item in search['items']]
            
            # Fetch video details
            video_data = self.youtube.videos().list(
                part="snippet,contentDetails,statistics",
                id=','.join(video_ids)
            ).execute()

            videos = video_data.get('items', [])
            
            # Fetch channel information for photos
            if videos:
                channel_ids = list(set([v.get('snippet', {}).get('channelId', '') for v in videos]))
                channel_ids = [cid for cid in channel_ids if cid]  # Remove empty ones
                
                if channel_ids:
                    channel_data = self.youtube.channels().list(
                        part="snippet",
                        id=','.join(channel_ids)
                    ).execute()
                    
                    # Create channel_id -> thumbnail map
                    channel_thumbnails = {}
                    for ch in channel_data.get('items', []):
                        ch_id = ch.get('id', '')
                        ch_thumb = ch.get('snippet', {}).get('thumbnails', {})
                        channel_thumbnails[ch_id] = (
                            ch_thumb.get('high', {}).get('url') or
                            ch_thumb.get('medium', {}).get('url') or
                            ch_thumb.get('default', {}).get('url', '')
                        )
                    
                    # Add channel thumbnail to each video
                    for video in videos:
                        ch_id = video.get('snippet', {}).get('channelId', '')
                        video['_channel_thumbnail'] = channel_thumbnails.get(ch_id, '')
            
            return videos

        except HttpError as e:
            error_msg = e.error_details[0]['message'] if e.error_details else str(e)
            logger.error(f"YouTube API error: {error_msg}")
            raise Exception(f"Erro na API: {error_msg}")
        except Exception as e:
            logger.error(f"Error searching YouTube videos: {e}")
            raise

    def _build_video_embed(self, video: Dict[str, Any], index: int = 0, total: int = 1) -> discord.Embed:
        """Builds embed with complete video information"""
        snippet = video.get('snippet', {})
        statistics = video.get('statistics', {})
        content_details = video.get('contentDetails', {})
        video_id = video['id']
        
        # Extract data
        title = snippet.get('title', 'Sem título')
        channel = snippet.get('channelTitle', 'Canal desconhecido')
        channel_id = snippet.get('channelId', '')
        
        # Channel thumbnail (obtained in search)
        channel_thumbnail = video.get('_channel_thumbnail', '')
        
        # Video thumbnails - prefer maxres, then high, medium, default
        thumbnails = snippet.get('thumbnails', {})
        thumbnail = (
            thumbnails.get('maxres', {}).get('url') or
            thumbnails.get('high', {}).get('url') or
            thumbnails.get('medium', {}).get('url') or
            thumbnails.get('default', {}).get('url', '')
        )
        
        # Publication date
        try:
            published = datetime.strptime(
                snippet.get('publishedAt', datetime.utcnow().isoformat()),
                '%Y-%m-%dT%H:%M:%SZ'
            )
            published_str = format_date(published)
        except:
            published = datetime.utcnow()
            published_str = "Desconhecido"
        
        # Live or duration
        is_live = snippet.get('liveBroadcastContent') == 'live'
        duration_str = content_details.get('duration', 'PT0S')
        
        if is_live:
            duration = "🔴 AO VIVO"
        else:
            duration = format_duration(duration_str)
        
        # Statistics
        views = int(statistics.get('viewCount', 0))
        likes = int(statistics.get('likeCount', 0))
        comments = int(statistics.get('commentCount', 0))
        
        # Calculate engagement
        engagement = (likes / views * 100) if views > 0 else 0
        engagement_emoji = "🔥" if engagement > 5 else "👍" if engagement > 2 else "👀"
        
        # Create embed (without description)
        embed = discord.Embed(
            title=f"🎬 {title}",
            url=f"https://www.youtube.com/watch?v={video_id}",
            color=YOUTUBE_COLOR,
            timestamp=published
        )
        
        # Author with channel photo
        embed.set_author(
            name=channel,
            icon_url=channel_thumbnail or YOUTUBE_LOGO,
            url=f"https://www.youtube.com/channel/{channel_id}"
        )
        
        if thumbnail:
            embed.set_image(url=thumbnail)
        
        # Stats compact
        embed.add_field(
            name="Views",
            value=f"```{format_number(views)}```",
            inline=True
        )
        
        embed.add_field(
            name="Likes",
            value=f"```{format_number(likes)}```",
            inline=True
        )
        
        embed.add_field(
            name="Duração",
            value=f"```{duration}```",
            inline=True
        )
        
        # Footer with pagination
        if total > 1:
            embed.set_footer(
                text=f"Resultado {index + 1} de {total} • Powered by YouTube Data API",
                icon_url=YOUTUBE_LOGO
            )
        else:
            embed.set_footer(
                text="Powered by YouTube Data API",
                icon_url=YOUTUBE_LOGO
            )
        
        return embed

    def _create_error_embed(self, title: str, description: str, color: Optional[int] = None) -> discord.Embed:
        """Creates styled error embed"""
        embed = discord.Embed(
            title=title,
            description=description[:200],
            color=color or Colors.ERROR
        )
        return embed

    def _create_help_embed(self) -> discord.Embed:
        """Creates help embed"""
        embed = discord.Embed(
            title="🎥 YouTube Search",
            description="Busque vídeos diretamente no Discord",
            color=YOUTUBE_COLOR
        )
        embed.add_field(name="Uso", value="```/youtube <busca>```", inline=True)
        embed.add_field(name="Alias", value="```/yt <busca>```", inline=True)
        embed.add_field(
            name="Exemplos",
            value="```/youtube lofi hip hop\n/yt tutorial python```",
            inline=False
        )
        
        embed.add_field(
            name="Funcionalidades",
            value=(
                "• Estatísticas detalhadas\n"
                "• Thumbnail em alta qualidade\n"
                "• Links diretos para vídeo e canal\n"
                "• Tags do vídeo\n"
                "• Data de publicação"
            ),
            inline=False
        )
        
        embed.set_thumbnail(url=YOUTUBE_LOGO)
        embed.set_footer(text="Powered by YouTube Data API v3")
        
        return embed

    @commands.hybrid_command(
        name="yt", 
        aliases=["youtube"],
        description="🎬 Busca vídeos no YouTube"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def youtube_search(self, ctx: commands.Context, *, search_query: Optional[str] = None):
        """
        Searches and displays YouTube video information
        
        Examples:
        - /youtube lofi hip hop
        - /yt tutorial discord.py
        """
        
        if not search_query:
            embed = self._create_help_embed()
            return await ctx.send(embed=embed, ephemeral=True)

        # Loading message
        loading_embed = discord.Embed(
            title="🔍 Buscando...",
            description=f"```{search_query}```",
            color=Colors.INFO
        )
        msg = await ctx.send(embed=loading_embed)

        try:
            # Search videos
            videos = await self._search_videos(search_query, max_results=1)
            
            if not videos:
                error_embed = self._create_error_embed(
                    "Nenhum resultado",
                    f"Não encontrei vídeos para **\"{search_query}\"**\n\n"
                    "**💡 Dicas:**\n"
                    "• Tente termos mais simples\n"
                    "• Verifique a ortografia\n"
                    "• Use palavras-chave em inglês",
                    color=Colors.USER_ERROR
                )
                return await msg.edit(embed=error_embed)
            
            video = videos[0]
            video_id = video['id']
            channel_id = video.get('snippet', {}).get('channelId', '')
            
            embed = self._build_video_embed(video)
            view = VideoView(
                f"https://www.youtube.com/watch?v={video_id}",
                f"https://www.youtube.com/channel/{channel_id}"
            )
            
            await msg.edit(embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error in youtube search for query '{search_query}': {e}")
            error_embed = self._create_error_embed(
                "Erro na busca",
                f"Ocorreu um erro ao buscar: {str(e)[:100]}"
            )
            await msg.edit(embed=error_embed)

    @youtube_search.error
    async def youtube_error(self, ctx: commands.Context, error: Exception):
        """Handles command errors"""
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏳ Aguarde",
                description=f"Tente novamente em {error.retry_after:.1f}s",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            logger.error(f"Unhandled error in youtube command: {error}")
            embed = self._create_error_embed("Erro", str(error)[:200])
            await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Youtube(bot))
