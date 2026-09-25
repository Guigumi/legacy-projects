"""
Video/Audio Download System
Supports YouTube, Twitter/X, TikTok, Instagram, Reddit and more...
"""
import logging
import discord
from discord.ext import commands
from discord import ui
import yt_dlp
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Any
import re

from config import TEMP_DIR, Colors

logger = logging.getLogger(__name__)

DISCORD_FILE_LIMIT = 25 * 1024 * 1024  # 25MB (Discord limit without Nitro)
DISCORD_NITRO_LIMIT = 100 * 1024 * 1024  # 100MB (with boost)

# Opções de qualidade para vídeo
VIDEO_QUALITY_OPTIONS = {
    "best": {
        "label": "🏆 Máxima", 
        "description": "Melhor qualidade disponível (1080p+)", 
        "emoji": "🏆",
        "short": "Máxima"
    },
    "high": {
        "label": "📺 Alta", 
        "description": "Qualidade HD (720p)", 
        "emoji": "📺",
        "short": "720p HD"
    },
    "medium": {
        "label": "📱 Média", 
        "description": "Qualidade boa (480p)", 
        "emoji": "📱",
        "short": "480p"
    },
    "low": {
        "label": "💾 Baixa", 
        "description": "Arquivo menor (360p)", 
        "emoji": "💾",
        "short": "360p"
    },
}

# Audio quality options
AUDIO_QUALITY_OPTIONS = {
    "best": {
        "label": "🎧 Máxima", 
        "description": "Melhor qualidade (320kbps)", 
        "emoji": "🎧",
        "short": "320kbps",
        "bitrate": "320"
    },
    "high": {
        "label": "🎵 Alta", 
        "description": "Qualidade ótima (256kbps)", 
        "emoji": "🎵",
        "short": "256kbps",
        "bitrate": "256"
    },
    "medium": {
        "label": "🎶 Média", 
        "description": "Qualidade boa (192kbps)", 
        "emoji": "🎶",
        "short": "192kbps",
        "bitrate": "192"
    },
    "low": {
        "label": "📻 Baixa", 
        "description": "Arquivo menor (128kbps)", 
        "emoji": "📻",
        "short": "128kbps",
        "bitrate": "128"
    },
}

FORMAT_OPTIONS = {
    "video": {
        "label": "🎬 Vídeo", 
        "description": "Baixar vídeo completo (MP4)", 
        "emoji": "🎬",
        "ext": "mp4"
    },
    "audio": {
        "label": "🎵 Áudio", 
        "description": "Apenas áudio (MP3)", 
        "emoji": "🎵",
        "ext": "mp3"
    },
}

# Supported sites with URL patterns
SUPPORTED_SITES = {
    "youtube": r"(youtube\.com|youtu\.be)",
    "twitter": r"(twitter\.com|x\.com)",
    "tiktok": r"(tiktok\.com|vm\.tiktok\.com)",
    "instagram": r"(instagram\.com|instagr\.am)",
    "reddit": r"(reddit\.com|redd\.it)",
    "twitch": r"(twitch\.tv|clips\.twitch\.tv)",
    "facebook": r"(facebook\.com|fb\.watch)",
    "vimeo": r"vimeo\.com",
    "dailymotion": r"dailymotion\.com",
    "soundcloud": r"soundcloud\.com",
    "spotify": r"spotify\.com",  # Metadata only
    "bilibili": r"bilibili\.com",
    "pinterest": r"pinterest\.com",
}

# ======================== HELPERS ========================

def detect_platform(url: str) -> str:
    """Detects platform based on URL"""
    for platform, pattern in SUPPORTED_SITES.items():
        if re.search(pattern, url, re.IGNORECASE):
            return platform
    return "unknown"

def get_platform_emoji(platform: str) -> str:
    """Returns platform emoji"""
    emojis = {
        "youtube": "🎬",
        "twitter": "🐦",
        "tiktok": "🎵",
        "instagram": "📸",
        "reddit": "🤖",
        "twitch": "🎮",
        "facebook": "📘",
        "vimeo": "🎥",
        "soundcloud": "🎧",
        "spotify": "🎶",
        "unknown": "🔗"
    }
    return emojis.get(platform, "🔗")

def truncate_title(title: str, limit: int = 50) -> str:
    """Truncates title if too long"""
    if not title:
        return "Sem título"
    return title if len(title) <= limit else title[:limit-3] + "..."

def format_duration(seconds: Optional[int | float]) -> str:
    """Formats duration in HH:MM:SS or MM:SS"""
    if not seconds:
        return "00:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

def format_filesize(bytes_size: Optional[int]) -> str:
    """Formats file size"""
    if not bytes_size:
        return "~"
    
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.2f} MB"
    return f"{bytes_size / (1024 * 1024 * 1024):.2f} GB"

def sanitize_filename(filename: str) -> str:
    """Removes invalid characters from filename"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    return filename[:100]  # Limit size

# ======================== INTERACTIVE VIEWS ========================

class DownloadOptionsView(ui.View):
    """Interactive view to choose download options"""
    
    def __init__(self, cog: 'Download', ctx: commands.Context, url: str, info: dict):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.url = url
        self.info = info
        self.format_type = "video"  # video or audio
        self.quality = "best"
        self.message: Optional[discord.Message] = None
        
        # Add components
        self.add_item(FormatSelect(self))
        self.add_item(QualitySelect(self))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Checks if it's the original author"""
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "❌ Apenas quem solicitou pode usar esses controles!", 
                ephemeral=True
            )
            return False
        return True
    
    async def on_timeout(self) -> None:
        """When time expires"""
        if self.message:
            try:
                for item in self.children:
                    if hasattr(item, 'disabled'):
                        item.disabled = True
                
                embed = self.message.embeds[0] if self.message.embeds else None
                if embed:
                    embed.color = Colors.ERROR
                    embed.set_footer(text="⏰ Tempo expirado - Use o comando novamente")
                
                await self.message.edit(embed=embed, view=self)
            except:
                pass
    
    def get_options_embed(self) -> discord.Embed:
        """Creates embed with current options - Enhanced visual"""
        platform = detect_platform(self.url)
        emoji = get_platform_emoji(platform)
        title = self.info.get('title', 'Sem título')
        duration = self.info.get('duration')
        thumbnail = self.info.get('thumbnail')
        uploader = self.info.get('uploader', 'Desconhecido')
        view_count = self.info.get('view_count')
        
        # Colors based on format
        color = 0x5865F2 if self.format_type == "video" else 0x1DB954
        
        embed = discord.Embed(
            title=f"{emoji} {truncate_title(title, 55)}",
            color=color
        )
        
        # Header with instructions
        embed.description = (
            "```\n"
            "╔══════════════════════════════════════╗\n"
            "║   📥  CONFIGURAR DOWNLOAD  📥        ║\n"
            "╚══════════════════════════════════════╝\n"
            "```\n"
            "Use os menus abaixo para personalizar seu download."
        )
        
        # Media information
        info_lines = []
        if uploader and uploader != 'Desconhecido':
            info_lines.append(f"👤 **Canal:** {truncate_title(uploader, 25)}")
        if duration:
            info_lines.append(f"⏱️ **Duração:** `{format_duration(duration)}`")
        info_lines.append(f"🌐 **Fonte:** {platform.capitalize()}")
        if view_count:
            views_formatted = f"{view_count:,}".replace(',', '.')
            info_lines.append(f"👁️ **Views:** {views_formatted}")
        
        embed.add_field(
            name="📋 Informações da Mídia",
            value="\n".join(info_lines) if info_lines else "Informações não disponíveis",
            inline=True
        )
        
        # Selected settings
        format_info = FORMAT_OPTIONS[self.format_type]
        
        # Select quality options based on format
        if self.format_type == "audio":
            quality_opts = AUDIO_QUALITY_OPTIONS
        else:
            quality_opts = VIDEO_QUALITY_OPTIONS
        
        quality_info = quality_opts[self.quality]
        
        config_lines = [
            f"{format_info['emoji']} **Formato:** {format_info['label'].split(' ', 1)[1]}",
            f"{quality_info['emoji']} **Qualidade:** {quality_info['short']}"
        ]
        
        # Visual type indicator
        if self.format_type == "video":
            config_lines.append("\n📦 **Saída:** `arquivo.mp4`")
        else:
            config_lines.append("\n📦 **Saída:** `arquivo.mp3`")
        
        embed.add_field(
            name="⚙️ Suas Configurações",
            value="\n".join(config_lines),
            inline=True
        )
        
        # Visual separator and tip
        tip_text = (
            "💡 **Dica:** "
        )
        embed.add_field(
            name="\u200b",  # Invisible field for spacing
            value=f"───────────────────────\n{tip_text}",
            inline=False
        )
        
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        # Styled footer
        embed.set_footer(
            text=f"📍 {self.ctx.author.display_name} • Timeout em 2 min",
            icon_url=self.ctx.author.display_avatar.url
        )
        embed.timestamp = datetime.now()
        
        return embed
    
    @ui.button(label="⬇️ Baixar", style=discord.ButtonStyle.success, row=2)
    async def download_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to start download"""
        await interaction.response.defer()
        
        # Disable all controls
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True
        
        await self.message.edit(view=self)
        
        # Start download
        await self.cog._process_download(
            self.ctx, 
            self.url, 
            self.info,
            self.message,
            self.quality,
            self.format_type == "audio"
        )
        self.stop()
    
    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to cancel"""
        embed = discord.Embed(
            title="❌ Cancelado",
            description="Download cancelado",
            color=Colors.ERROR
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class FormatSelect(ui.Select):
    """Menu to select format (video/audio)"""
    
    def __init__(self, parent_view: DownloadOptionsView):
        self.parent_view = parent_view
        
        options = [
            discord.SelectOption(
                label=info["label"],
                description=info["description"],
                value=key,
                emoji=info["emoji"],
                default=(key == parent_view.format_type)
            )
            for key, info in FORMAT_OPTIONS.items()
        ]
        
        super().__init__(
            placeholder="🎬 Escolha o formato...",
            options=options,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        old_format = self.parent_view.format_type
        self.parent_view.format_type = self.values[0]
        
        # Update default options
        for option in self.options:
            option.default = (option.value == self.values[0])
        
        # If format changed, update quality options
        if old_format != self.values[0]:
            # Find and update QualitySelect
            for item in self.parent_view.children:
                if isinstance(item, QualitySelect):
                    item.update_options()
                    break
        
        # Update embed
        embed = self.parent_view.get_options_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class QualitySelect(ui.Select):
    """Menu to select quality - Adapts based on format"""
    
    def __init__(self, parent_view: DownloadOptionsView):
        self.parent_view = parent_view
        self._build_options()
        
        super().__init__(
            placeholder="📊 Escolha a qualidade...",
            options=self.options_list,
            row=1
        )
    
    def _build_options(self) -> None:
        """Builds options based on current format"""
        # Select options based on format
        if self.parent_view.format_type == "audio":
            quality_opts = AUDIO_QUALITY_OPTIONS
        else:
            quality_opts = VIDEO_QUALITY_OPTIONS
        
        self.options_list = [
            discord.SelectOption(
                label=info["label"],
                description=info["description"],
                value=key,
                emoji=info["emoji"],
                default=(key == self.parent_view.quality)
            )
            for key, info in quality_opts.items()
        ]
    
    def update_options(self) -> None:
        """Updates options when format changes"""
        self._build_options()
        self.options = self.options_list
    
    async def callback(self, interaction: discord.Interaction):
        self.parent_view.quality = self.values[0]
        
        # Update default options
        for option in self.options:
            option.default = (option.value == self.values[0])
        
        # Update embed
        embed = self.parent_view.get_options_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

# ======================== DOWNLOAD COG ========================

class Download(commands.Cog):
    """Cog for downloading videos and audios from various platforms"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.temp_dir = TEMP_DIR
        self.temp_dir.mkdir(exist_ok=True)
        self.active_downloads: dict[int, bool] = {}  # user_id -> is_downloading
    
    def _get_base_opts(self) -> dict:
        """Base options for yt-dlp"""
        return {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'no_color': True,
            'geo_bypass': True,
            'socket_timeout': 30,
            'retries': 3,
            'fragment_retries': 3,
            'extractor_retries': 3,
            # Cookies for sites that need it
            'cookiefile': 'cookies.txt' if Path('cookies.txt').exists() else None,
            # Headers to avoid blocks
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
        }
    
    def _get_video_opts(self, max_size: int, quality: str = "best", is_audio: bool = False, audio_bitrate: str = "192") -> dict:
        """Options for video or audio download"""
        opts = self._get_base_opts()
        
        # Configuration for audio
        if is_audio:
            opts['format'] = 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': audio_bitrate,
            }]
            opts['prefer_ffmpeg'] = True
            opts['keepvideo'] = False
            opts['postprocessor_args'] = {
                'ffmpeg': ['-y', '-loglevel', 'error']
            }
            return opts
        
        # Configuration for video based on quality
        if quality == "low":
            # 360p or lower
            opts['format'] = (
                f'bestvideo[height<=360][filesize<{max_size}]+bestaudio/'
                f'best[height<=360][filesize<{max_size}]/'
                f'best[filesize<{max_size}]/best'
            )
        elif quality == "medium":
            # 480p or lower
            opts['format'] = (
                f'bestvideo[height<=480][filesize<{max_size}]+bestaudio/'
                f'best[height<=480][filesize<{max_size}]/'
                f'best[filesize<{max_size}]/best'
            )
        elif quality == "high":
            # 720p or lower
            opts['format'] = (
                f'bestvideo[height<=720][filesize<{max_size}]+bestaudio/'
                f'best[height<=720][filesize<{max_size}]/'
                f'best[filesize<{max_size}]/best'
            )
        else:
            # Best quality possible within limit
            opts['format'] = (
                f'bestvideo[filesize<{max_size}]+bestaudio/'
                f'best[filesize<{max_size}]/best'
            )
        
        opts['merge_output_format'] = 'mp4'
        opts['postprocessor_args'] = ['-c:v', 'libx264', '-c:a', 'aac']
        
        return opts
    
    def _create_embed(
        self, 
        title: str, 
        status: str, 
        color: int,
        platform: str = "unknown",
        duration: str = "",
        quality: str = "",
        filesize: str = "",
        thumbnail: Optional[str] = None,
        url: Optional[str] = None,
        progress: Optional[float] = None,
        author: Optional[Union[discord.Member, discord.User]] = None
    ) -> discord.Embed:
        """Creates status embed with enhanced visual"""
        emoji = get_platform_emoji(platform)
        platform_name = platform.capitalize() if platform != "unknown" else "Vídeo"
        
        embed = discord.Embed(
            title=f"{emoji} {truncate_title(title)}",
            color=color
        )
        
        # Description with styled status
        status_icons = {
            "⏳": "🔄",
            "⬇️": "📥",
            "📤": "☁️",
            "✅": "🎉",
            "🎵": "🎶"
        }
        
        # Replace icon if there's a match
        for old_icon, new_icon in status_icons.items():
            if old_icon in status:
                status = status.replace(old_icon, new_icon)
                break
        
        embed.description = f"**{status}**"
        
        # Visual progress bar (if applicable)
        if progress is not None:
            progress_filled = int(progress * 10)
            progress_empty = 10 - progress_filled
            progress_bar = "█" * progress_filled + "░" * progress_empty
            embed.description += f"\n`[{progress_bar}]` {int(progress * 100)}%"
        
        # Information in a single organized field
        if duration or quality or filesize:
            info_lines = []
            if duration:
                info_lines.append(f"⏱️ **Duração:** {duration}")
            if quality:
                info_lines.append(f"📺 **Qualidade:** {quality}")
            if filesize:
                info_lines.append(f"💾 **Tamanho:** {filesize}")
            
            embed.add_field(
                name="📋 Informações",
                value="\n".join(info_lines),
                inline=True
            )
        
        # Platform
        embed.add_field(
            name="🌐 Plataforma",
            value=f"{emoji} **{platform_name}**",
            inline=True
        )
        
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        if url:
            # More compact link
            embed.add_field(
                name="🔗 Original",
                value=f"[Clique para abrir]({url})",
                inline=False
            )
        
        # Footer with timestamp
        if author:
            embed.set_footer(
                text=f"Solicitado por {author.display_name}",
                icon_url=author.display_avatar.url
            )
        
        embed.timestamp = datetime.now()
        
        return embed
    
    async def _extract_info(self, url: str) -> dict[str, Any]:
        """Extracts video information asynchronously"""
        opts = self._get_base_opts()
        opts['skip_download'] = True
        
        loop = asyncio.get_event_loop()
        
        def extract() -> dict[str, Any]:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:  # type: ignore
                    return ydl.extract_info(url, download=False)  # type: ignore
            except Exception as e:
                logger.error(f"Error extracting info from {url}: {e}")
                raise
        
        return await loop.run_in_executor(None, extract)
    
    async def _download_media(
        self, 
        url: str, 
        user_id: int, 
        max_size: int,
        quality: str = "best",
        is_audio: bool = False,
        audio_bitrate: str = "192"
    ) -> tuple[str, dict[str, Any]]:
        """Downloads media and returns (path, info)"""
        ext = "mp3" if is_audio else "mp4"
        
        output_template = str(self.temp_dir / f"dl_{user_id}_%(id)s.%(ext)s")
        
        opts = self._get_video_opts(max_size, quality, is_audio, audio_bitrate)
        opts['outtmpl'] = output_template
        
        loop = asyncio.get_event_loop()
        
        def download() -> tuple[str, dict[str, Any]]:
            with yt_dlp.YoutubeDL(opts) as ydl:  # type: ignore
                info = ydl.extract_info(url, download=True)
                # Find downloaded file
                video_id = info.get('id', str(user_id))
                
                # Search file in temp folder (prefer mp3 for audio)
                found_file = None
                for file in self.temp_dir.iterdir():
                    if f"dl_{user_id}_{video_id}" in file.name:
                        # Prefer .mp3 if audio
                        if is_audio and file.suffix == '.mp3':
                            return str(file), info  # type: ignore
                        found_file = str(file)
                
                if found_file:
                    return found_file, info  # type: ignore
                
                # Fallback: build path
                downloaded_ext = 'mp3' if is_audio else info.get('ext', ext)
                filepath = str(self.temp_dir / f"dl_{user_id}_{video_id}.{downloaded_ext}")
                return filepath, info  # type: ignore
        
        return await loop.run_in_executor(None, download)
    
    async def _cleanup(self, user_id: int) -> None:
        """Cleans up user's temporary files"""
        try:
            for file in self.temp_dir.iterdir():
                if f"dl_{user_id}_" in file.name:
                    file.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Error cleaning up temp files for user {user_id}: {e}")
    
    def _estimate_quality(self, filesize: Optional[int], duration: Optional[int]) -> str:
        """Estimates quality based on size and duration"""
        if not filesize or not duration:
            return "Auto"
        
        # Approximate bitrate in kbps
        bitrate = (filesize * 8) / (duration * 1000) if duration > 0 else 0
        
        if bitrate > 5000:
            return "1080p+"
        elif bitrate > 2500:
            return "720p"
        elif bitrate > 1000:
            return "480p"
        elif bitrate > 500:
            return "360p"
        return "240p"
    
    async def _process_download(
        self,
        ctx: commands.Context,
        url: str,
        info: dict,
        msg: discord.Message,
        quality: str = "best",
        is_audio: bool = False
    ) -> None:
        """Processes download after option selection"""
        platform = detect_platform(url)
        
        try:
            # Determine size limit
            max_size = DISCORD_FILE_LIMIT
            if ctx.guild and ctx.guild.premium_tier >= 2:
                max_size = DISCORD_NITRO_LIMIT
            
            title = info.get('title', 'Sem título')
            duration = info.get('duration')
            filesize = info.get('filesize') or info.get('filesize_approx')
            thumbnail = info.get('thumbnail')
            
            # Check duration
            max_duration = 900 if is_audio else 600  # 15 min audio, 10 min video
            if duration and duration > max_duration:
                raise Exception(f"{'Áudio' if is_audio else 'Vídeo'} muito longo! Máximo: {max_duration // 60} minutos")
            
            # Get quality info based on format
            if is_audio:
                quality_opts = AUDIO_QUALITY_OPTIONS
                audio_bitrate = quality_opts[quality]["bitrate"]
                quality_str = quality_opts[quality]["short"]
            else:
                quality_opts = VIDEO_QUALITY_OPTIONS
                quality_str = quality_opts[quality]["short"]
                audio_bitrate = "192"  # Default for video
            
            # Status: Downloading
            format_label = f"🎵 Convertendo para MP3 ({quality_str})..." if is_audio else f"⬇️ Baixando vídeo ({quality_str})..."
            
            downloading_embed = self._create_embed(
                title,
                format_label,
                Colors.WARNING,
                platform,
                format_duration(duration),
                quality_str,
                format_filesize(filesize),
                thumbnail,
                url,
                progress=0.3,
                author=ctx.author
            )
            await msg.edit(embed=downloading_embed, view=None)
            
            # Download
            try:
                filepath, final_info = await asyncio.wait_for(
                    self._download_media(url, ctx.author.id, max_size, quality, is_audio, audio_bitrate),
                    timeout=120
                )
            except asyncio.TimeoutError:
                raise Exception("Timeout ao baixar. Tente novamente.")
            
            # Check file
            if not os.path.exists(filepath):
                raise Exception("Arquivo não foi baixado corretamente")
            
            actual_size = os.path.getsize(filepath)
            
            if actual_size > max_size:
                raise Exception(f"Arquivo muito grande ({format_filesize(actual_size)})! Tente qualidade menor.")
            
            if actual_size == 0:
                raise Exception("Arquivo baixado está vazio")
            
            # Status: Sending
            uploading_embed = self._create_embed(
                title,
                "📤 Enviando para o Discord...",
                Colors.INFO,
                platform,
                format_duration(duration),
                quality_str,
                format_filesize(actual_size),
                thumbnail,
                progress=0.8,
                author=ctx.author
            )
            await msg.edit(embed=uploading_embed)
            
            # Send file
            ext = "mp3" if is_audio else filepath.split('.')[-1]
            filename = sanitize_filename(f"{title[:40]}.{ext}")
            await ctx.send(file=discord.File(filepath, filename=filename))
            
            # Status: Completed
            format_text = "Áudio extraído" if is_audio else "Download concluído"
            success_embed = self._create_embed(
                title,
                f"✅ {format_text} com sucesso!",
                Colors.SUCCESS,
                platform,
                format_duration(duration),
                quality_str,
                format_filesize(actual_size),
                thumbnail,
                progress=1.0,
                author=ctx.author
            )
            await msg.edit(embed=success_embed)
            
        except Exception as e:
            error_msg = str(e)[:200]
            
            # Friendlier error messages
            if "Video unavailable" in error_msg or "not available" in error_msg.lower():
                error_msg = "Vídeo não disponível ou privado"
            elif "Sign in" in error_msg:
                error_msg = "Este vídeo requer login (não suportado)"
            elif "age" in error_msg.lower():
                error_msg = "Vídeo com restrição de idade (não suportado)"
            elif "copyright" in error_msg.lower():
                error_msg = "Vídeo bloqueado por direitos autorais"
            elif "audio conversion failed" in error_msg.lower() or "conversion failed" in error_msg.lower():
                error_msg = "Falha na conversão de áudio. O formato original não é compatível."
            elif "ffmpeg" in error_msg.lower():
                error_msg = "Erro no processamento. Tente outro vídeo."
            
            error_embed = discord.Embed(
                title="❌ Erro",
                description=error_msg,
                color=Colors.ERROR
            )
            await msg.edit(embed=error_embed)
        
        finally:
            self.active_downloads[ctx.author.id] = False
            await self._cleanup(ctx.author.id)
    
    @commands.hybrid_command(
        name="baixar",
        aliases=["download", "dl", "mp3", "audio"],
        description="Baixa vídeo ou áudio de YouTube, Twitter, TikTok, Instagram e mais"
    )
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def download(self, ctx: commands.Context, url: str):
        """
        Downloads video or audio from various platforms
        
        Supported platforms:
        YouTube, Twitter/X, TikTok, Instagram, Reddit, Twitch, Facebook, Vimeo
        
        Use the interactive menu to choose:
        • Format: Video (MP4) or Audio (MP3)
        • Quality: Best, High (720p), Medium (480p), Low (360p)
        """
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return await ctx.send("❌ URL inválida! Use uma URL completa (https://...)", ephemeral=True)
        
        # Check if already downloading
        if self.active_downloads.get(ctx.author.id):
            return await ctx.send("⏳ Você já tem um download em andamento!", ephemeral=True)
        
        self.active_downloads[ctx.author.id] = True
        platform = detect_platform(url)
        
        try:
            # Status: Loading
            loading_embed = discord.Embed(
                title="⏳ Carregando...",
                description="Obtendo informações...",
                color=Colors.INFO
            )
            loading_embed.set_author(
                name=ctx.author.display_name,
                icon_url=ctx.author.display_avatar.url
            )
            msg = await ctx.send(embed=loading_embed)
            
            # Extract information
            try:
                info = await asyncio.wait_for(
                    self._extract_info(url),
                    timeout=30
                )
            except asyncio.TimeoutError:
                raise Exception("Timeout ao obter informações do vídeo")
            
            if not info:
                raise Exception("Não foi possível obter informações do vídeo")
            
            # Create interactive view
            view = DownloadOptionsView(self, ctx, url, info)
            view.message = msg
            
            # Show options
            options_embed = view.get_options_embed()
            await msg.edit(embed=options_embed, view=view)
            
        except Exception as e:
            self.active_downloads[ctx.author.id] = False
            
            error_msg = str(e)[:200]
            
            if "Video unavailable" in error_msg or "not available" in error_msg.lower():
                error_msg = "Vídeo não disponível ou privado"
            elif "Sign in" in error_msg:
                error_msg = "Este vídeo requer login (não suportado)"
            
            error_embed = discord.Embed(
                title="❌ Erro",
                description=error_msg,
                color=Colors.ERROR
            )
            
            try:
                await msg.edit(embed=error_embed, view=None)
            except:
                await ctx.send(embed=error_embed)
    
    @download.error
    async def download_error(self, ctx: commands.Context, error: Exception):
        """Handles command errors"""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Aguarde {error.retry_after:.1f}s para baixar novamente", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Forneça uma URL! Exemplo: `s!download https://youtube.com/...`", ephemeral=True)
        else:
            await ctx.send(f"❌ Erro: {str(error)[:100]}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Download(bot))
