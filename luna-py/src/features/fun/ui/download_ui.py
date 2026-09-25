from __future__ import annotations
import logging
import os
import discord
from discord.ext import commands
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from config.settings import BotEmojis, Separators
from features.fun.integrations.download_service import DownloadService, DownloadError

logger = logging.getLogger(__name__)

_QUALITY_BAD_EMOJI = BotEmojis.QUALITY_BAD
_QUALITY_GOOD_EMOJI = BotEmojis.QUALITY_GOOD
_QUALITY_EXCELLENT_EMOJI = BotEmojis.QUALITY_EXCELLENT


def _quality_emoji_value(quality: str, media_type: str) -> str:
    normalized = quality.lower().strip()

    if media_type == "video":
        resolution = (
            int(normalized.removesuffix("p"))
            if normalized.endswith("p") and normalized[:-1].isdigit()
            else 0
        )
        if resolution <= 360:
            return _QUALITY_BAD_EMOJI
        if resolution <= 720:
            return _QUALITY_GOOD_EMOJI
        return _QUALITY_EXCELLENT_EMOJI

    bitrate = (
        int(normalized.removesuffix("kbps"))
        if normalized.endswith("kbps") and normalized[:-4].isdigit()
        else 0
    )
    if bitrate <= 96:
        return _QUALITY_BAD_EMOJI
    if bitrate <= 192:
        return _QUALITY_GOOD_EMOJI
    return _QUALITY_EXCELLENT_EMOJI


def _quality_emoji(quality: str, media_type: str) -> discord.PartialEmoji:
    return discord.PartialEmoji.from_str(_quality_emoji_value(quality, media_type))


class DownloadTypeSelect(discord.ui.Select):
    """Seleção do tipo de mídia: vídeo, áudio ou imagem."""

    def __init__(
        self, bot: LunaBot, url: str, *, has_images: bool = False, image_info: dict | None = None
    ) -> None:
        self.bot = bot
        self.url = url
        self.has_images = has_images
        self.image_info = image_info
        image_desc = (
            "Baixar imagem(ns) do post"
            if has_images
            else "Tentar baixar imagens do post (se houver)"
        )
        options = [
            discord.SelectOption(
                label="Vídeo",
                value="video",
                emoji=BotEmojis.CAM_ON,
                description="Baixar como vídeo (MP4)",
            ),
            discord.SelectOption(
                label="Áudio",
                value="audio",
                emoji=BotEmojis.AUDIO_ON,
                description="Baixar apenas o áudio (MP3)",
            ),
            discord.SelectOption(
                label="Imagem",
                value="image",
                emoji=BotEmojis.COMMON_IMAGE,
                description=image_desc,
            ),
        ]
        super().__init__(
            placeholder="Escolha o tipo de mídia…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]

        if selected == "image":
            # Processar download de imagem diretamente
            service = self.bot.container.download_service
            msg = interaction.message
            if not service:
                embed = EmbedBuilder.error_internal(
                    f"{BotEmojis.DEV} O serviço de download não está disponível."
                ).build()
                await interaction.response.edit_message(embed=embed, view=None)
                return

            embed = (
                EmbedBuilder.default(f"{BotEmojis.COMMON_IMAGE} Baixando imagem…")
                .description("Isso pode levar alguns segundos.")
                .build()
            )
            await interaction.response.edit_message(embed=embed, view=None)

            if msg is None:
                msg = await interaction.original_response()

            result = None
            try:
                if (
                    self.has_images
                    and self.image_info
                    and self.image_info.get("_image_urls")
                ):
                    image_urls = self.image_info["_image_urls"]
                    title = self.image_info.get("title") or "Sem título"
                    uploader = self.image_info.get("uploader") or "Desconhecido"
                    result = await service.download_images_from_urls(
                        image_urls, source_url=self.url
                    )
                    if result and result.filepaths:
                        await _send_image_result(
                            msg,
                            result,
                            service,
                            interaction.user.display_name,
                            title=f" {title}",
                            uploader=uploader,
                        )
                    else:
                        embed = EmbedBuilder.error_user(
                            "Não consegui baixar as imagens desse post.\n"
                            "Verifique se o link está acessível."
                        ).build()
                        await interaction.edit_original_response(embed=embed)
                else:
                    # Tentar extrair imagens via métodos genéricos
                    image_info = await service.extract_images_any_method(self.url)
                    if image_info and image_info.get("_image_urls"):
                        image_urls = image_info["_image_urls"]
                        title = image_info.get("title") or "Sem título"
                        uploader = image_info.get("uploader") or "Desconhecido"
                        result = await service.download_images_from_urls(
                            image_urls, source_url=self.url
                        )
                        if result and result.filepaths:
                            await _send_image_result(
                                msg,
                                result,
                                service,
                                interaction.user.display_name,
                                title=f" {title}",
                                uploader=uploader,
                            )
                        else:
                            embed = EmbedBuilder.error_user(
                                "Não consegui baixar as imagens desse post.\n"
                                "Verifique se o link está acessível."
                            ).build()
                            await interaction.edit_original_response(embed=embed)
                    else:
                        # Tentar como imagem direta
                        result = await service.download_image(self.url)
                        if result and result.filepaths:
                            await _send_image_result(
                                msg,
                                result,
                                service,
                                interaction.user.display_name,
                            )
                        else:
                            embed = EmbedBuilder.error_user(
                                "Não encontrei imagens nessa URL.\n"
                                "Verifique se o link contém imagens."
                            ).build()
                            await interaction.edit_original_response(embed=embed)
            except Exception as e:
                logger.exception("Erro durante download de imagem: %s", e)
                embed = EmbedBuilder.error_internal(
                    "Algo deu errado durante o download. Tente novamente mais tarde."
                ).build()
                try:
                    await interaction.edit_original_response(embed=embed, view=None)
                except Exception:
                    pass
            finally:
                if result and hasattr(result, "filepaths") and result.filepaths:
                    service.cleanup_files(result.filepaths)
            return

        # Substituir a view atual pela de qualidade
        if selected == "video":
            view = QualityView(
                self.bot,
                self.url,
                media_type="video",
                author_id=interaction.user.id,
                has_images=self.has_images,
                image_info=self.image_info,
            )
            embed = (
                EmbedBuilder.default(" Qualidade do Vídeo")
                .description(
                    "Selecione a resolução desejada.\n"
                    f"Se quiser voltar, use o botão {BotEmojis.ACTION_RETURN} Voltar."
                )
                .build()
            )
        else:
            view = QualityView(
                self.bot,
                self.url,
                media_type="audio",
                author_id=interaction.user.id,
                has_images=self.has_images,
                image_info=self.image_info,
            )
            embed = (
                EmbedBuilder.default(" Qualidade do Áudio")
                .description(
                    "Selecione o bitrate desejado.\n"
                    f"Se quiser voltar, use o botão {BotEmojis.ACTION_RETURN} Voltar."
                )
                .build()
            )

        await interaction.response.edit_message(embed=embed, view=view)
        view.message = interaction.message


class MediaTypeView(discord.ui.View):
    """View para selecionar tipo de mídia (vídeo/áudio/imagem)."""

    def __init__(
        self,
        bot: LunaBot,
        url: str,
        author_id: int,
        timeout: float = 60.0,
        *,
        has_images: bool = False,
        image_info: dict | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.url = url
        self.author_id = author_id
        self.has_images = has_images
        self.image_info = image_info
        self.add_item(
            DownloadTypeSelect(bot, url, has_images=has_images, image_info=image_info)
        )

    @discord.ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.TRASH_RED,
        row=1,
    )
    async def cancel_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = EmbedBuilder.alert(
            f"{BotEmojis.TRASH_RED} Download cancelado."
        ).build()
        await interaction.response.edit_message(embed=embed, view=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode selecionar."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class VideoQualitySelect(discord.ui.Select):
    """Seleção de qualidade de vídeo."""

    def __init__(self, bot: LunaBot, url: str) -> None:
        self.bot = bot
        self.url = url
        options = [
            discord.SelectOption(
                label="144p",
                value="144p",
                emoji=_quality_emoji("144p", "video"),
                description="Qualidade mínima — arquivo bem menor",
            ),
            discord.SelectOption(
                label="240p",
                value="240p",
                emoji=_quality_emoji("240p", "video"),
                description="Baixa qualidade — ideal para limite de tamanho",
            ),
            discord.SelectOption(
                label="360p",
                value="360p",
                emoji=_quality_emoji("360p", "video"),
                description="Qualidade baixa — arquivo menor",
            ),
            discord.SelectOption(
                label="480p", value="480p", emoji=_quality_emoji("480p", "video"), description="Qualidade média"
            ),
            discord.SelectOption(
                label="720p", value="720p", emoji=_quality_emoji("720p", "video"), description="HD — recomendado"
            ),
            discord.SelectOption(
                label="1080p",
                value="1080p",
                emoji=_quality_emoji("1080p", "video"),
                description="Full HD — arquivo maior",
            ),
            discord.SelectOption(
                label="1440p",
                value="1440p",
                emoji=_quality_emoji("1440p", "video"),
                description="2K — pode exceder o limite do Discord",
            ),
            discord.SelectOption(
                label="2160p",
                value="2160p",
                emoji=_quality_emoji("2160p", "video"),
                description="4K — pode exceder o limite do Discord",
            ),
        ]
        super().__init__(
            placeholder="Escolha a resolução…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        quality = self.values[0]
        await _process_download(interaction, self.bot, self.url, "video", quality)


class AudioQualitySelect(discord.ui.Select):
    """Seleção de qualidade de áudio."""

    def __init__(self, bot: LunaBot, url: str) -> None:
        self.bot = bot
        self.url = url
        options = [
            discord.SelectOption(
                label="64 kbps",
                value="64kbps",
                emoji=_quality_emoji("64kbps", "audio"),
                description="Qualidade mínima — arquivo bem menor",
            ),
            discord.SelectOption(
                label="96 kbps",
                value="96kbps",
                emoji=_quality_emoji("96kbps", "audio"),
                description="Qualidade baixa — arquivo menor",
            ),
            discord.SelectOption(
                label="128 kbps",
                value="128kbps",
                emoji=_quality_emoji("128kbps", "audio"),
                description="Qualidade padrão",
            ),
            discord.SelectOption(
                label="160 kbps",
                value="160kbps",
                emoji=_quality_emoji("160kbps", "audio"),
                description="Qualidade boa",
            ),
            discord.SelectOption(
                label="192 kbps",
                value="192kbps",
                emoji=_quality_emoji("192kbps", "audio"),
                description="Qualidade média — recomendado",
            ),
            discord.SelectOption(
                label="256 kbps",
                value="256kbps",
                emoji=_quality_emoji("256kbps", "audio"),
                description="Qualidade alta",
            ),
            discord.SelectOption(
                label="320 kbps",
                value="320kbps",
                emoji=_quality_emoji("320kbps", "audio"),
                description="Máxima qualidade",
            ),
        ]
        super().__init__(
            placeholder="Escolha o bitrate…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        bitrate = self.values[0]
        await _process_download(interaction, self.bot, self.url, "audio", bitrate)


class QualityView(discord.ui.View):
    """View para selecionar qualidade."""

    def __init__(
        self,
        bot: LunaBot,
        url: str,
        media_type: str,
        author_id: int,
        timeout: float = 60.0,
        *,
        has_images: bool = False,
        image_info: dict | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.url = url
        self.author_id = author_id
        self.media_type = media_type
        self.has_images = has_images
        self.image_info = image_info
        if media_type == "video":
            self.add_item(VideoQualitySelect(bot, url))
        else:
            self.add_item(AudioQualitySelect(bot, url))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode selecionar."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    @discord.ui.button(
        label="Voltar",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.ACTION_RETURN,
        row=1,
    )
    async def back_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        num_images = 0
        if self.image_info and self.image_info.get("_image_urls"):
            num_images = len(self.image_info.get("_image_urls", []))

        embed = (
            EmbedBuilder.default("Escolha o tipo de mídia")
            .description(
                "Selecione abaixo se deseja baixar como vídeo, áudio ou imagem."
                + (
                    f"\n\n{BotEmojis.CAM_ON if self.has_images else BotEmojis.CAM_OFF} "
                    f"Imagens disponíveis: `{num_images}`"
                    if self.image_info is not None
                    else ""
                )
            )
            .build()
        )
        view = MediaTypeView(
            self.bot,
            self.url,
            self.author_id,
            timeout=60.0,
            has_images=self.has_images,
            image_info=self.image_info,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.TRASH,
        row=2,
    )
    async def cancel_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = EmbedBuilder.alert(f"{BotEmojis.TRASH} Cancelado.").build()
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


async def _process_download(
    interaction: discord.Interaction,
    bot: LunaBot,
    url: str,
    media_type: str,
    quality: str,
) -> None:
    """Processa o download e envia o arquivo."""
    service = bot.download_service

    if not service:
        embed = EmbedBuilder.error_internal(
            f"{BotEmojis.DEV} O serviço de download não está disponível."
        ).build()
        await interaction.response.edit_message(embed=embed, view=None)
        return

    # Mostrar progresso
    type_label = "vídeo" if media_type == "video" else "áudio"
    embed = (
        EmbedBuilder.default(f"{BotEmojis.COMMON_WATCH} Baixando…")
        .description(
            f"Baixando {type_label} em **{quality}**…\nIsso pode levar alguns segundos."
        )
        .build()
    )
    await interaction.response.edit_message(embed=embed, view=None)

    # Realizar download
    result = None
    try:
        if media_type == "video":
            result = await service.download_video(url, quality)
        else:
            result = await service.download_audio(url, quality)

        if result is None:
            embed = EmbedBuilder.error_user(
                "Não consegui baixar essa mídia. Verifique se a URL é válida e tente novamente."
            ).build()
            await interaction.edit_original_response(embed=embed, view=None)
            return

        if not result.filepath:
            error_msg = getattr(result, "error_msg", "") or ""
            if "No video could be found in this tweet" in error_msg:
                embed = EmbedBuilder.error_user(
                    "Esse tweet não possui vídeo. Tente baixar imagens usando a opção de imagem, se disponível."
                ).build()
            else:
                embed = EmbedBuilder.error_user(
                    "Não consegui baixar essa mídia. Verifique se a URL é válida e tente novamente."
                ).build()
            await interaction.edit_original_response(embed=embed, view=None)
            return

        # Verificar tamanho
        if not result.within_limit:
            embed = EmbedBuilder.error_user(
                f"O arquivo é muito grande ({result.size_mb:.1f} MB).\n"
                f"O limite do Discord é **25 MB**.\n"
                f"Tente uma qualidade menor."
            ).build()
            await interaction.edit_original_response(embed=embed, view=None)
            return

        # Formatar duração
        duration_str = "?"
        if result.duration:
            mins, secs = divmod(int(result.duration), 60)
            hours, mins = divmod(mins, 60)
            if hours > 0:
                duration_str = f"{hours}:{mins:02d}:{secs:02d}"
            else:
                duration_str = f"{mins}:{secs:02d}"

        video_title = result.title or "Sem título"
        video_title_display = video_title[:254] + "…" if len(video_title) > 255 else video_title
        # Montar embed de sucesso
        embed = (
            EmbedBuilder.success("Download concluído!")
            .title(f" {video_title_display}")
            .field(
                f"{_quality_emoji_value(quality, media_type)} Qualidade",
                f"`{quality}`",
                inline=True,
            )
            .field("Tamanho", f"`{result.size_mb:.1f} MB`", inline=True)
            .field("Duração", f"`{duration_str}`", inline=True)
        )

        if result.uploader:
            embed.field("Autor", result.uploader, inline=True)

        if result.thumbnail:
            embed.thumbnail(result.thumbnail)

        embed.footer(
            f"Solicitado por {interaction.user.display_name} • Arquivo temporário será removido"
        )

        # Enviar arquivo
        file = discord.File(result.filepath, filename=result.filename)
        await interaction.followup.send(file=file)
        # Garantir que o embed de conclusão fique separado do arquivo
        await interaction.edit_original_response(
            embed=embed.build(),
            view=None,
            attachments=[],
        )

    except DownloadError as e:
        embed = EmbedBuilder.error_user(
            f"Não foi possível processar o download:\n`{str(e)}`"
        ).build()
        try:
            await interaction.edit_original_response(embed=embed, view=None)
        except Exception:
            pass
    except Exception as e:
        logger.exception("Erro durante download: %s", e)
        embed = EmbedBuilder.error_internal(
            "Algo deu errado durante o download. Tente novamente mais tarde."
        ).build()
        try:
            await interaction.edit_original_response(embed=embed, view=None)
        except Exception:
            pass
    finally:
        # ── Dupla checagem de limpeza ─────────────────────────
        if result and result.filepath:
            service.cleanup_file(result.filepath)


async def _send_image_result(
    msg: discord.Message,
    result: object,
    service: DownloadService,
    author_name: str,
    *,
    title: str | None = None,
    uploader: str | None = None,
) -> bool:
    """Valida e envia o resultado de um download de imagens.

    Retorna ``True`` se enviou com sucesso, ``False`` caso contrário.
    """
    from features.fun.integrations.download_service import ImageDownloadResult

    if not isinstance(result, ImageDownloadResult):
        return False

    if not result.filepaths:
        if result.total_size > 0:
            embed = EmbedBuilder.error_user(
                f"A imagem é muito grande ({result.total_size_mb:.1f} MB).\n"
                f"O limite do Discord é **25 MB**."
            ).build()
        else:
            embed = EmbedBuilder.error_user(
                "Não consegui baixar essa imagem.\n"
                "Verifique se a URL é válida e acessível."
            ).build()
        await msg.edit(embed=embed)
        return False

    if not result.within_limit:
        embed = EmbedBuilder.error_user(
            f"As imagens totalizam {result.total_size_mb:.1f} MB.\n"
            f"O limite do Discord é **25 MB**."
        ).build()
        await msg.edit(embed=embed)
        return False

    # Montar embed de sucesso
    label = title or f" {'Imagens' if result.count > 1 else 'Imagem'}"
    label_display = label[:254] + "…" if len(label) > 255 else label
    embed_builder = EmbedBuilder.success("Download concluído!").title(label_display)
    if uploader:
        embed_builder.field("Autor", uploader, inline=True)
    embed_builder.field("Quantidade", f"`{result.count}`", inline=True)
    embed_builder.field(
        "Tamanho total", f"`{result.total_size_mb:.1f} MB`", inline=True
    )
    embed_builder.footer(
        f"Solicitado por {author_name} • Arquivo temporário será removido"
    )

    files = [discord.File(fp, filename=os.path.basename(fp)) for fp in result.filepaths]

    try:
        await msg.edit(embed=embed_builder.build(), attachments=files)
    except Exception as e:
        logger.exception("Erro ao enviar imagens: %s", e)
        embed = EmbedBuilder.error_internal(
            "Algo deu errado ao enviar as imagens."
        ).build()
        await msg.edit(embed=embed)
        return False

    return True


async def _process_image_download(
    ctx: commands.Context,
    url: str,
    service: DownloadService,
) -> None:
    """Baixa imagem(ns) de uma URL e envia no chat."""
    embed = (
        EmbedBuilder.default(f"{BotEmojis.COMMON_IMAGE} Baixando imagem…")
        .description("Isso pode levar alguns segundos.")
        .build()
    )
    msg = await ctx.send(embed=embed)

    result = None
    try:
        result = await service.download_image(url)
        await _send_image_result(
            msg,
            result,
            service,
            ctx.author.display_name,
        )
    except Exception as e:
        logger.exception("Erro durante download de imagem: %s", e)
        embed = EmbedBuilder.error_internal(
            "Algo deu errado durante o download. Tente novamente mais tarde."
        ).build()
        try:
            await msg.edit(embed=embed)
        except Exception:
            pass
    finally:
        if result and result.filepaths:
            service.cleanup_files(result.filepaths)


async def _process_social_images(
    ctx: commands.Context,
    url: str,
    service: DownloadService,
    image_info: dict,
) -> None:
    """Baixa imagens extraídas de uma rede social e envia no chat."""
    image_urls: list[str] = image_info["_image_urls"]
    title = image_info.get("title") or "Sem título"
    uploader = image_info.get("uploader") or "Desconhecido"

    embed = (
        EmbedBuilder.default(f"{BotEmojis.COMMON_IMAGE} Baixando imagem…")
        .description(
            f"**{title}**\n"
            f"por {uploader}\n\n"
            f"Encontrei {len(image_urls)} imagem(ns). Baixando…"
        )
        .build()
    )
    msg = await ctx.send(embed=embed)

    result = None
    try:
        result = await service.download_images_from_urls(image_urls, source_url=url)
        if not result or not result.filepaths:
            embed = EmbedBuilder.error_user(
                "Não consegui baixar as imagens desse post.\n"
                "Verifique se o link está acessível."
            ).build()
            await msg.edit(embed=embed)
            return

        await _send_image_result(
            msg,
            result,
            service,
            ctx.author.display_name,
            title=f" {title}",
            uploader=uploader,
        )
    except Exception as e:
        logger.exception("Erro durante download de imagens: %s", e)
        embed = EmbedBuilder.error_internal(
            "Algo deu errado durante o download. Tente novamente mais tarde."
        ).build()
        try:
            await msg.edit(embed=embed)
        except Exception:
            pass
    finally:
        if result and result.filepaths:
            service.cleanup_files(result.filepaths)
