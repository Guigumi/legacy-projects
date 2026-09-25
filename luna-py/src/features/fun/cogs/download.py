"""
Cog Download — baixa vídeos/áudios/imagens de redes sociais.
Uso: !download <URL> ou detecção passiva de links suportados no chat.
"""

from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotEmojis
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from features.fun.integrations.download_service import (
    DownloadService,
    DownloadError,
    _is_instagram_url,
    _is_social_media_post,
    is_image_url,
    validate_url_safe,
)

logger = logging.getLogger(__name__)


class DownloadCog(commands.Cog):
    """Comando para baixar vídeos, áudios e imagens de redes sociais."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service = bot.container.download_service

    @commands.hybrid_command(
        name="download",
        aliases=["dl"],
        description="Baixa vídeos, áudios ou imagens de redes sociais diretamente no chat",
    )
    @app_commands.describe(
        url="URL do vídeo ou imagem (YouTube, Twitter/X, Instagram, TikTok, etc.)",
        somente_audio="Se definido como True, fará o download apenas do áudio em formato MP3",
    )
    async def download(
        self, ctx: commands.Context, *, url: str, somente_audio: bool = False
    ) -> None:
        service = self.service
        if not service:
            embed = EmbedBuilder.error_internal(
                f"{BotEmojis.DEV} O serviço de download não está disponível."
            ).build()
            await ctx.send(embed=embed)
            return

        # Validação básica da URL
        url = url.strip("<>")
        if not url.startswith(("http://", "https://")):
            embed = EmbedBuilder.error_user(
                "Forneça uma URL válida.\n"
                "Exemplo: `/download https://www.youtube.com/watch?v=...`"
            ).build()
            await ctx.send(embed=embed)
            return

        # Proteção SSRF
        url_safe, url_error = validate_url_safe(url)
        if not url_safe:
            embed = EmbedBuilder.error_user(f"URL bloqueada: {url_error}").build()
            await ctx.send(embed=embed)
            return

        # Rate limit por usuário
        media_hint = "audio" if somente_audio else ("image" if is_image_url(url) else "video")
        allowed, retry_after = service.check_rate_limit(ctx.author.id, media_hint)
        if not allowed:
            embed = EmbedBuilder.error_user(
                f"Você está fazendo downloads muito rápido.\n"
                f"Tente novamente em **{retry_after}s**."
            ).build()
            await ctx.send(embed=embed, delete_after=8)
            return

        # Defer para dar feedback visual de carregamento
        await ctx.defer()

        try:
            # ── FLUXO APENAS ÁUDIO ─────────────────────────────
            if somente_audio:
                result = await service.download_audio(url, "192kbps")
                if not result or not result.filepath:
                    embed = EmbedBuilder.error_user(
                        "Não consegui extrair o áudio desta URL."
                    ).build()
                    await ctx.send(embed=embed)
                    return

                if result.within_limit:
                    file = discord.File(result.filepath, filename=result.filename)
                    embed = (
                        EmbedBuilder.success("Download de áudio concluído!")
                        .title(result.title)
                        .field("Tamanho", f"`{result.size_mb:.1f} MB`", inline=True)
                        .footer(f"Solicitado por {ctx.author.display_name}")
                    )
                    await ctx.send(embed=embed.build(), file=file)
                else:
                    embed = EmbedBuilder.error_user(
                        f"O áudio gerado é muito grande ({result.size_mb:.1f} MB). O limite do Discord é 25 MB."
                    ).build()
                    await ctx.send(embed=embed)

                if result.filepath:
                    service.cleanup_file(result.filepath)
                return

            # ── FLUXO IMAGEM DIRETA ────────────────────────────
            if is_image_url(url):
                result = await service.download_image(url)
                if result and result.filepaths:
                    files = [
                        discord.File(fp, filename=os.path.basename(fp))
                        for fp in result.filepaths
                    ]
                    embed = (
                        EmbedBuilder.success("Imagem baixada com sucesso!")
                        .footer(f"Solicitado por {ctx.author.display_name}")
                        .build()
                    )
                    await ctx.send(embed=embed, files=files)
                    service.cleanup_files(result.filepaths)
                else:
                    embed = EmbedBuilder.error_user("Não encontrei imagem nesta URL.").build()
                    await ctx.send(embed=embed)
                return

            # ── FLUXO VÍDEO PADRÃO (Auto-Fit) ─ Tenta vídeo primeiro ──
            result = await service.download_video_auto_fit(url)
            if result and result.filepath:
                if result.within_limit:
                    file = discord.File(result.filepath, filename=result.filename)
                    video_title = result.title or "Sem título"
                    video_title_display = (
                        video_title[:254] + "…" if len(video_title) > 255 else video_title
                    )

                    duration_str = "?"
                    if result.duration:
                        mins, secs = divmod(int(result.duration), 60)
                        hours, mins = divmod(mins, 60)
                        duration_str = (
                            f"{hours}:{mins:02d}:{secs:02d}" if hours > 0 else f"{mins}:{secs:02d}"
                        )

                    embed = (
                        EmbedBuilder.success("Download concluído!")
                        .title(f" {video_title_display}")
                        .field("Tamanho", f"`{result.size_mb:.1f} MB`", inline=True)
                        .field("Duração", f"`{duration_str}`", inline=True)
                        .footer(f"Solicitado por {ctx.author.display_name}")
                    )
                    if result.thumbnail:
                        embed.thumbnail(result.thumbnail)

                    await ctx.send(embed=embed.build(), file=file)
                else:
                    # Fallback com botão se o arquivo ultrapassar 25MB (Streaming Fallback)
                    video_title = result.title or "Sem título"
                    video_title_display = (
                        video_title[:254] + "…" if len(video_title) > 255 else video_title
                    )
                    embed = (
                        EmbedBuilder.alert("Vídeo muito grande!")
                        .title(f" {video_title_display}")
                        .description(
                            f"O arquivo deste vídeo possui **{result.size_mb:.1f} MB**, superando o limite de 25 MB do Discord.\n"
                            "Você pode assistir ou baixá-lo diretamente pelo link abaixo."
                        )
                        .footer(f"Solicitado por {ctx.author.display_name}")
                    )
                    if result.thumbnail:
                        embed.thumbnail(result.thumbnail)

                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(label="Ver Original", url=url))
                    if result.url:
                        view.add_item(
                            discord.ui.Button(label="Assistir / Download Direto", url=result.url)
                        )

                    await ctx.send(embed=embed.build(), view=view)

                service.cleanup_file(result.filepath)
                return

            # ── FLUXO REDES SOCIAIS COM APENAS IMAGENS (Se não for vídeo) ──
            is_strict_video_url = False
            if _is_instagram_url(url) and any(x in url for x in ("/reel/", "/tv/")):
                is_strict_video_url = True

            if _is_social_media_post(url) and not is_strict_video_url:
                image_info = await service.extract_images_any_method(url)
                if image_info and image_info.get("_image_urls"):
                    image_urls = image_info["_image_urls"]
                    img_result = await service.download_images_from_urls(
                        image_urls, source_url=url
                    )
                    if img_result and img_result.filepaths:
                        files = [
                            discord.File(fp, filename=os.path.basename(fp))
                            for fp in img_result.filepaths
                        ]
                        title = image_info.get("title") or "Imagens"
                        title_display = title[:254] + "…" if len(title) > 255 else title
                        embed = (
                            EmbedBuilder.success("Imagens baixadas com sucesso!")
                            .title(f" {title_display}")
                            .footer(f"Solicitado por {ctx.author.display_name}")
                            .build()
                        )
                        await ctx.send(embed=embed, files=files)
                        service.cleanup_files(img_result.filepaths)
                        return

            # Se não conseguiu baixar como vídeo e nem encontrou imagens
            embed = EmbedBuilder.error_user(
                "Não consegui extrair mídias desta URL. Verifique o link e tente novamente."
            ).build()
            await ctx.send(embed=embed)

        except DownloadError as e:
            embed = EmbedBuilder.error_user(
                f"Não foi possível processar o download:\n`{str(e)}`"
            ).build()
            await ctx.send(embed=embed)
        except Exception as e:
            logger.exception("Erro no comando manual de download: %s", e)
            embed = EmbedBuilder.error_internal(
                "Ocorreu um erro inesperado ao processar o download."
            ).build()
            await ctx.send(embed=embed)




async def setup(bot: LunaBot) -> None:
    await bot.add_cog(DownloadCog(bot))
