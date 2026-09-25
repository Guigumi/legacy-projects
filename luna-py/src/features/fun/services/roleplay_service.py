"""
Serviço de Roleplay (RP) — fornece GIFs de reação e processa imagem do jail.
"""

from __future__ import annotations

import asyncio
import io
import logging

import aiohttp

logger = logging.getLogger(__name__)

NEKOS_BEST_URL = "https://nekos.best/api/v2/{reaction}"
OTAKUGIFS_URL = "https://api.otakugifs.xyz/gif?reaction={reaction}"


class RoleplayService:
    """Serviço para gerenciar reações de Roleplay e processar imagens do jail."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def get_reaction_gif(self, reaction: str) -> str | None:
        """Busca um GIF de reação nas APIs públicas. Tenta nekos.best e depois OtakuGIFs."""
        session = await self._get_session()

        # 1. Tentar nekos.best
        try:
            url = NEKOS_BEST_URL.format(reaction=reaction)
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results")
                    if results and len(results) > 0:
                        return results[0].get("url")
                else:
                    logger.warning("nekos.best retornou status %s para %s", resp.status, reaction)
        except Exception as e:
            logger.warning("Erro ao acessar nekos.best para %s: %s", reaction, e)

        # 2. Fallback para OtakuGIFs
        try:
            url = OTAKUGIFS_URL.format(reaction=reaction)
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("url")
                else:
                    logger.warning("OtakuGIFs retornou status %s para %s", resp.status, reaction)
        except Exception as e:
            logger.warning("Erro ao acessar OtakuGIFs para %s: %s", reaction, e)

        return None

    async def get_jail_image(self, avatar_url: str) -> bytes | None:
        """Faz o download do avatar do usuário e gera a imagem com grades em executor."""
        session = await self._get_session()
        try:
            async with session.get(avatar_url, timeout=10) as resp:
                if resp.status != 200:
                    logger.warning("Falha ao baixar avatar para o jail: status %s", resp.status)
                    return None
                avatar_bytes = await resp.read()
        except Exception as e:
            logger.error("Erro de rede ao baixar avatar do usuário para o jail: %s", e)
            return None

        # Executa a renderização pesada (CPU-bound) em uma thread separada para não travar o loop do bot
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._draw_jail_bars, avatar_bytes)

    def _draw_jail_bars(self, avatar_bytes: bytes) -> bytes | None:
        """Aplica o filtro de grades metálicas 3D sobre o avatar do usuário de forma programática."""
        try:
            from PIL import Image, ImageDraw

            # Abrir avatar e converter para RGBA
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            width, height = avatar.size

            # Criar canvas de overlay transparente
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Desenhar 6 grades verticais
            bar_count = 6
            bar_width = max(width // 15, 6)

            if bar_count > 1:
                gap = (width - bar_width) / (bar_count - 1)
            else:
                gap = 0

            for i in range(bar_count):
                x = int(i * gap)
                # Corpo da barra metálica (chumbo semi-transparente)
                draw.rectangle([x, 0, x + bar_width, height], fill=(60, 60, 60, 210))
                # Luz esquerda (reflexo prateado)
                highlight_w = max(bar_width // 4, 1)
                draw.line([x, 0, x, height], fill=(130, 130, 130, 240), width=highlight_w)
                # Sombra direita (profundidade)
                draw.line([x + bar_width, 0, x + bar_width, height], fill=(20, 20, 20, 250), width=highlight_w)

            # Mesclar as duas camadas
            jailed_avatar = Image.alpha_composite(avatar, overlay)

            output = io.BytesIO()
            jailed_avatar.save(output, format="PNG")
            return output.getvalue()
        except Exception as e:
            logger.error("Falha ao desenhar grades do jail: %s", e)
            return None

    async def close(self) -> None:
        """Fecha a sessão de HTTP se ela estiver aberta."""
        if self._session and not self._session.closed:
            await self._session.close()
