"""
Download Service — baixa vídeos/áudios/imagens de redes sociais via yt-dlp.
Garante limpeza dos arquivos temporários após o envio.
"""

from __future__ import annotations

import atexit
import asyncio
import html as html_mod
import ipaddress
import json
import logging
import mimetypes
import os
import re
import shutil
import socket
import tempfile
import time as _time
import uuid
from collections import deque
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
from yarl import URL

logger = logging.getLogger(__name__)


def _find_ffmpeg() -> str | None:
    """Localiza o ffmpeg no sistema (PATH, locais comuns)."""
    # 1. Tenta via PATH
    path = shutil.which("ffmpeg")
    if path:
        return os.path.dirname(path)

    # 2. Locais comuns em Linux/macOS
    for candidate in (
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/snap/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
    ):
        if os.path.isfile(candidate):
            return os.path.dirname(candidate)

    return None


# Caminho do arquivo de cookies (Netscape format) para autenticação em sites
COOKIES_FILE = str(Path(__file__).parents[4] / "cookies.txt")

# Instagram GraphQL doc_id para buscar dados de posts
_IG_GQL_DOC_ID = "8845758582119845"
_IG_APP_ID = "936619743392459"

# Nomes de cookies reservados pelo http.cookies que não podem ser setados
_RESERVED_COOKIE_NAMES = frozenset(
    {
        "domain",
        "path",
        "expires",
        "max-age",
        "secure",
        "httponly",
        "samesite",
        "version",
        "comment",
    }
)

# Extensões de imagem reconhecidas
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".svg",
    ".ico",
    ".avif",
}

# Content-types de imagem reconhecidos
IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "image/svg+xml",
    "image/x-icon",
    "image/avif",
}

# Tamanho máximo de upload no Discord (25 MB para servidores sem boost)
DISCORD_FILE_LIMIT = 25 * 1024 * 1024  # 25 MB

# Formatos de vídeo por resolução (merge via ffmpeg)
VIDEO_FORMATS: dict[str, str] = {
    "144p": "bestvideo[height<=144]+bestaudio/best[height<=144]/worst",
    "240p": "bestvideo[height<=240]+bestaudio/best[height<=240]/worst",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]/worst",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
    "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
}

# Formatos de áudio por bitrate
AUDIO_FORMATS: dict[str, str] = {
    "64kbps": "64",
    "96kbps": "96",
    "128kbps": "128",
    "160kbps": "160",
    "192kbps": "192",
    "256kbps": "256",
    "320kbps": "320",
}

# ── Padrões de CDN de imagem (precompilados) ────────────────────
_IMAGE_CDN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"pbs\.twimg\.com"),
    re.compile(r"i\.imgur\.com"),
    re.compile(r"cdn\.discordapp\.com"),
    re.compile(r"media\.discordapp\.net"),
    re.compile(r"i\.redd\.it"),
    re.compile(r"preview\.redd\.it"),
    re.compile(r"i\.pinimg\.com"),
    re.compile(r".*\.fbcdn\.net"),
    re.compile(r".*\.twimg\.com"),
    re.compile(r"images\.unsplash\.com"),
]

# ── Esquemas e IPs bloqueados (proteção SSRF) ───────────────────
_BLOCKED_SCHEMES = frozenset({"file", "ftp", "data", "javascript", "gopher"})
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]
_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "metadata.google.internal", "169.254.169.254",
})

# ── Rate limiting por usuário ────────────────────────────────────
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    # tipo → (max_requests, window_seconds)
    "video": (2, 60),
    "audio": (4, 60),
    "image": (8, 60),
}


def validate_url_safe(url: str) -> tuple[bool, str]:
    """Valida se a URL é segura contra SSRF.

    Retorna (is_safe, error_msg).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL inválida."

    # Bloquear esquemas perigosos
    scheme = (parsed.scheme or "").lower()
    if scheme in _BLOCKED_SCHEMES:
        return False, f"Esquema `{scheme}://` não é permitido."

    if scheme not in ("http", "https"):
        return False, "Apenas URLs http/https são aceitas."

    hostname = parsed.hostname or ""
    if not hostname:
        return False, "URL sem hostname."

    # Bloquear hostnames conhecidos
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return False, "Esse endereço não é permitido."

    # Resolver hostname e checar IPs privados
    try:
        for info in socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM):
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if any(ip in net for net in _PRIVATE_NETWORKS):
                return False, "Endereços de rede interna não são permitidos."
    except (socket.gaierror, ValueError):
        # Não conseguiu resolver — permitir (deixa yt-dlp lidar)
        pass

    return True, ""


class DownloadError(Exception):
    """Erro ao realizar o download (ex.: link inválido, vídeo privado/deletado, etc.)."""
    pass


class DownloadResult:
    """Resultado de um download."""

    def __init__(
        self,
        filepath: str,
        title: str,
        duration: int | None = None,
        filesize: int = 0,
        thumbnail: str | None = None,
        uploader: str | None = None,
        url: str | None = None,
    ) -> None:
        self.filepath = filepath
        self.title = title
        self.duration = duration
        self.filesize = filesize
        self.thumbnail = thumbnail
        self.uploader = uploader
        self.url = url

    @property
    def filename(self) -> str:
        return os.path.basename(self.filepath)

    @property
    def size_mb(self) -> float:
        return self.filesize / (1024 * 1024)

    @property
    def within_limit(self) -> bool:
        return self.filesize <= DISCORD_FILE_LIMIT


def _pick_best_thumbnails(thumbnails: list[dict[str, Any]]) -> list[str]:
    """Dado uma lista de thumbnails do yt-dlp, retorna a URL de maior
    resolução para cada ``id`` distinto (ou a maior se não houver id)."""
    if not thumbnails:
        return []

    # Agrupar por id (yt-dlp dá ids como "0", "1", etc. para carrossel)
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in thumbnails:
        tid = str(t.get("id", "default"))
        groups.setdefault(tid, []).append(t)

    best_urls: list[str] = []
    for _tid, items in groups.items():
        # Ordenar por resolução (width * height), pegar a maior
        def _res(item: dict[str, Any]) -> int:
            w = item.get("width") or 0
            h = item.get("height") or 0
            return w * h

        items.sort(key=_res, reverse=True)
        url = items[0].get("url")
        if url and url not in best_urls:
            best_urls.append(url)

    return best_urls


def is_image_url(url: str) -> bool:
    """Verifica se a URL aponta para uma imagem (pela extensão ou padrão conhecido)."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Checar extensão direta
    _, ext = os.path.splitext(path)
    if ext in IMAGE_EXTENSIONS:
        return True

    # Padrões conhecidos de CDNs de imagem (precompilados)
    hostname = parsed.hostname or ""
    for pattern in _IMAGE_CDN_PATTERNS:
        if pattern.match(hostname):
            return True

    # Checar query params comuns que indicam imagem (ex: ?format=jpg)
    query = parsed.query.lower()
    if any(f"format={fmt}" in query for fmt in ("jpg", "jpeg", "png", "gif", "webp")):
        return True

    return False


class ImageDownloadResult:
    """Resultado do download de uma ou mais imagens."""

    def __init__(
        self,
        filepaths: list[str],
        source_url: str,
        total_size: int = 0,
    ) -> None:
        self.filepaths = filepaths
        self.source_url = source_url
        self.total_size = total_size

    @property
    def filenames(self) -> list[str]:
        return [os.path.basename(fp) for fp in self.filepaths]

    @property
    def total_size_mb(self) -> float:
        return self.total_size / (1024 * 1024)

    @property
    def within_limit(self) -> bool:
        return self.total_size <= DISCORD_FILE_LIMIT

    @property
    def count(self) -> int:
        return len(self.filepaths)


def _is_instagram_url(url: str) -> bool:
    """Verifica se a URL é de um post do Instagram."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    path = parsed.path
    return (
        hostname in ("www.instagram.com", "instagram.com", "instagr.am")
        and any(x in path for x in ("/p/", "/reel/", "/tv/"))
    )


def _is_twitter_url(url: str) -> bool:
    """Verifica se a URL é de um tweet/post do Twitter/X."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return (
        hostname
        in (
            "twitter.com",
            "www.twitter.com",
            "x.com",
            "www.x.com",
        )
        and "/status/" in parsed.path
    )


def _is_social_media_post(url: str) -> bool:
    """Verifica se a URL é de uma rede social que pode conter apenas imagens."""
    return _is_instagram_url(url) or _is_twitter_url(url)


def _extract_instagram_shortcode(url: str) -> str | None:
    """Extrai o shortcode de uma URL do Instagram (ex: /p/DVd6oColn-U/)."""
    m = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def _twitter_to_vxtwitter(url: str) -> str | None:
    """Converte URL do Twitter/X para vxtwitter (proxy gratuito de embed).

    ``https://x.com/user/status/123`` → ``https://vxtwitter.com/user/status/123``
    """
    parsed = urlparse(url)
    path = parsed.path
    if "/status/" not in path:
        return None
    return f"https://vxtwitter.com{path}"


def _parse_vxtwitter_images(twitter_image_url: str) -> list[str]:
    """Extrai URLs individuais de imagens do ``twitter:image`` do vxtwitter.

    O vxtwitter retorna uma URL combinada quando há múltiplas imagens::

        https://vxtwitter.com/rendercombined.jpg?imgs=URL1,URL2,URL3

    Ou uma URL direta do ``pbs.twimg.com`` para imagem única.
    Adiciona ``?name=orig`` para resolução máxima.
    """
    parsed = urlparse(twitter_image_url)
    image_urls: list[str] = []

    if "rendercombined" in parsed.path:
        # Múltiplas imagens concatenadas no param ?imgs=
        from urllib.parse import parse_qs

        qs = parse_qs(parsed.query)
        imgs_raw = qs.get("imgs", [""])[0]
        if imgs_raw:
            # Separar por vírgula seguida de https://
            individual = re.split(r",(?=https?://)", imgs_raw)
            for u in individual:
                u = u.strip()
                if u:
                    image_urls.append(_twimg_orig(u))
    elif "pbs.twimg.com" in (parsed.hostname or ""):
        # Imagem única direta
        image_urls.append(_twimg_orig(twitter_image_url))
    else:
        # URL desconhecida, usar como está
        image_urls.append(twitter_image_url)

    return image_urls


def _twimg_orig(url: str) -> str:
    """Garante que a URL do pbs.twimg.com use ``?name=orig`` para resolução máxima."""
    parsed = urlparse(url)
    # Remover qualquer ?name= existente e colocar name=orig
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return f"{base}?name=orig"


def _load_cookies_to_jar(
    cookie_jar: aiohttp.CookieJar, domain_filter: str | None = None
) -> None:
    """Carrega cookies do arquivo Netscape no CookieJar do aiohttp."""
    if not os.path.isfile(COOKIES_FILE):
        return
    try:
        moz_jar = MozillaCookieJar(COOKIES_FILE)
        moz_jar.load(ignore_discard=True, ignore_expires=True)
        for cookie in moz_jar:
            if cookie.name.lower() in _RESERVED_COOKIE_NAMES:
                continue
            if domain_filter and domain_filter not in (cookie.domain or ""):
                continue
            cookie_jar.update_cookies(
                {cookie.name: cookie.value or ""},
                response_url=URL(f"https://{cookie.domain.lstrip('.')}/"),
            )
    except Exception as e:
        logger.debug("Falha ao carregar cookies: %s", e)


class DownloadService:
    """Serviço para download de mídias usando yt-dlp."""

    def __init__(self) -> None:
        self._temp_dir = tempfile.mkdtemp(prefix="luna_downloads_")
        self._ffmpeg_location = _find_ffmpeg()
        self._http_session: aiohttp.ClientSession | None = None
        self._ig_session: aiohttp.ClientSession | None = None
        # Rate limit: user_id → deque[timestamp] por tipo de mídia
        self._user_rate: dict[tuple[int, str], deque[float]] = {}
        logger.debug("Download temp dir: %s", self._temp_dir)
        if not self._ffmpeg_location:
            logger.warning("ffmpeg não encontrado — merge vídeo+áudio pode falhar")
        # Safety net: limpar temp dir se o processo morrer sem close()
        atexit.register(self._atexit_cleanup)

    def _atexit_cleanup(self) -> None:
        """Cleanup registrado via atexit para quando o processo termina abruptamente."""
        try:
            if os.path.isdir(self._temp_dir):
                shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass

    async def close(self) -> None:
        """Fecha sessões HTTP e remove o diretório temporário."""
        if self._http_session and not self._http_session.closed:
            try:
                await self._http_session.close()
            except Exception:
                pass
        if self._ig_session and not self._ig_session.closed:
            try:
                await self._ig_session.close()
            except Exception:
                pass
        try:
            if os.path.isdir(self._temp_dir):
                shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass
        logger.debug("DownloadService encerrado.")

    def _save_file(self, filepath: str, data: bytes) -> None:
        """Salva um arquivo binário em disco de forma síncrona."""
        with open(filepath, "wb") as f:
            f.write(data)

    def check_rate_limit(self, user_id: int, media_type: str) -> tuple[bool, int]:
        """Verifica rate limit por usuário.

        Retorna (allowed, retry_after_seconds).
        """
        limits = _RATE_LIMITS.get(media_type, (4, 60))
        max_req, window = limits
        key = (user_id, media_type)
        now = _time.monotonic()

        window_deque = self._user_rate.setdefault(key, deque())
        # Limpar entradas expiradas
        while window_deque and (now - window_deque[0]) > window:
            window_deque.popleft()

        if len(window_deque) >= max_req:
            retry_after = int(window - (now - window_deque[0])) + 1
            return False, retry_after

        window_deque.append(now)
        return True, 0

    async def _get_session(self) -> aiohttp.ClientSession:
        """Retorna (ou cria) a sessão HTTP compartilhada."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                }
            )
        return self._http_session

    async def _get_ig_session(self) -> aiohttp.ClientSession:
        """Retorna (ou cria) sessão HTTP com cookies do Instagram."""
        if self._ig_session is None or self._ig_session.closed:
            cookie_jar = aiohttp.CookieJar()
            _load_cookies_to_jar(cookie_jar, domain_filter="instagram")
            self._ig_session = aiohttp.ClientSession(
                cookie_jar=cookie_jar,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                    "X-IG-App-ID": _IG_APP_ID,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        return self._ig_session

    def _base_opts(self) -> dict[str, Any]:
        """Retorna opções base compartilhadas (cookies + ffmpeg_location)."""
        opts: dict[str, Any] = {}
        if os.path.isfile(COOKIES_FILE):
            opts["cookiefile"] = COOKIES_FILE
        if self._ffmpeg_location:
            opts["ffmpeg_location"] = self._ffmpeg_location
        return opts

    async def fetch_info(self, url: str) -> dict[str, Any] | None:
        """Busca informações do vídeo sem baixar."""
        import yt_dlp

        ydl_opts: dict[str, Any] = {
            "format": "best",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
            **self._base_opts(),
        }

        def _extract() -> dict[str, Any] | None:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                    info = ydl.extract_info(url, download=False)
                    return dict(info) if info else None
            except Exception as e:
                logger.warning("Falha ao extrair info de %s: %s", url, e)
                return None

        return await asyncio.get_running_loop().run_in_executor(None, _extract)

    async def fetch_info_images(self, url: str) -> dict[str, Any] | None:
        """Extrai metadados de posts que contêm apenas imagens (sem vídeo).

        Usa ``ignore_no_formats_error`` para que o yt-dlp não lance exceção
        quando o post não possui formatos de vídeo (ex.: foto do Instagram).
        Retorna o dict de info com campo ``_image_urls`` contendo as URLs
        das imagens encontradas, ou ``None`` se nada for encontrado.
        """
        import yt_dlp

        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
            "ignore_no_formats_error": True,
            **self._base_opts(),
        }

        def _extract() -> dict[str, Any] | None:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        return None

                    info = dict(info)

                    # Coletar URLs de imagens do post
                    image_urls: list[str] = []

                    # 1. Thumbnail principal (geralmente a imagem do post)
                    thumb: str | None = (
                        str(info["thumbnail"]) if info.get("thumbnail") else None
                    )
                    if thumb:
                        image_urls.append(thumb)

                    # 2. Lista de thumbnails (múltiplas resoluções)
                    raw_thumbnails = info.get("thumbnails")
                    thumbnails: list[dict[str, Any]] = (
                        list(raw_thumbnails) if isinstance(raw_thumbnails, list) else []
                    )
                    for t in thumbnails:
                        if isinstance(t, dict):
                            t_url = str(t["url"]) if t.get("url") else None
                            if t_url and t_url not in image_urls:
                                image_urls.append(t_url)

                    # 3. Entradas de carrossel (Instagram multi-foto)
                    raw_entries = info.get("entries")
                    entries: list[Any] = (
                        list(raw_entries) if isinstance(raw_entries, list) else []
                    )
                    for entry in entries:
                        if isinstance(entry, dict):
                            e_thumb = (
                                str(entry["thumbnail"])
                                if entry.get("thumbnail")
                                else None
                            )
                            if e_thumb and e_thumb not in image_urls:
                                image_urls.append(e_thumb)
                            raw_e_thumbs = entry.get("thumbnails")
                            e_thumbs: list[dict[str, Any]] = (
                                list(raw_e_thumbs)
                                if isinstance(raw_e_thumbs, list)
                                else []
                            )
                            for t in e_thumbs:
                                if isinstance(t, dict):
                                    t_url = str(t["url"]) if t.get("url") else None
                                    if t_url and t_url not in image_urls:
                                        image_urls.append(t_url)

                    # Sem formatos de vídeo E sem imagens → nada útil
                    has_video = bool(info.get("formats"))
                    if has_video:
                        # Tem vídeo — esse método não deve ser usado
                        return None

                    if not image_urls:
                        return None

                    # Filtrar: pegar apenas a melhor resolução de cada grupo
                    # (thumbnails vêm em várias resoluções; queremos a maior)
                    best = _pick_best_thumbnails(thumbnails)
                    if best:
                        image_urls = best
                    elif thumb:
                        image_urls = [thumb]

                    info["_image_urls"] = image_urls
                    return info

            except Exception as e:
                logger.warning("Falha ao extrair imagens de %s: %s", url, e)
                return None

        return await asyncio.get_running_loop().run_in_executor(None, _extract)

    async def download_images_from_urls(
        self, image_urls: list[str], source_url: str
    ) -> ImageDownloadResult | None:
        """Baixa múltiplas imagens a partir de uma lista de URLs diretas.

        Downloads são feitos em paralelo (até 4 simultâneos) via semáforo.
        """
        session = await self._get_session()
        filepaths: list[str] = []
        total_size = 0
        _sem = asyncio.Semaphore(4)
        _lock = asyncio.Lock()

        async def _download_one(img_url: str) -> None:
            nonlocal total_size
            async with _sem:
                try:
                    async with session.head(
                        img_url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as head_resp:
                        if head_resp.status == 200:
                            content_length = int(head_resp.headers.get("Content-Length", 0))
                            async with _lock:
                                if total_size + content_length > DISCORD_FILE_LIMIT:
                                    logger.info(
                                        "Limite projetado atingido no HEAD ao baixar múltiplas imagens "
                                        "(%.1f MB acumulado)",
                                        (total_size + content_length) / (1024 * 1024),
                                    )
                                    return

                    async with session.get(
                        img_url, timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status != 200:
                            logger.debug(
                                "HTTP %s ao baixar imagem: %s", resp.status, img_url
                            )
                            return

                        content_type = resp.content_type or ""
                        if not content_type.startswith("image/"):
                            logger.debug(
                                "Content-Type inesperado (%s): %s",
                                content_type,
                                img_url,
                            )
                            return

                        data = await resp.read()

                        async with _lock:
                            # Verificar acumulado (thread-safe)
                            if total_size + len(data) > DISCORD_FILE_LIMIT:
                                logger.info(
                                    "Limite atingido ao baixar múltiplas imagens "
                                    "(%.1f MB acumulado)",
                                    (total_size + len(data)) / (1024 * 1024),
                                )
                                return

                            ext = mimetypes.guess_extension(content_type) or ".jpg"
                            if ext in (".jpe",):
                                ext = ".jpg"

                            file_id = uuid.uuid4().hex[:8]
                            filepath = os.path.join(self._temp_dir, f"{file_id}{ext}")

                            await asyncio.to_thread(self._save_file, filepath, data)

                            filepaths.append(filepath)
                            total_size += len(data)

                except asyncio.TimeoutError:
                    logger.warning("Timeout ao baixar imagem: %s", img_url)
                except Exception as e:
                    logger.debug("Erro ao baixar imagem %s: %s", img_url, e)

        await asyncio.gather(*(_download_one(url) for url in image_urls))

        if not filepaths:
            return None

        return ImageDownloadResult(
            filepaths=filepaths,
            source_url=source_url,
            total_size=total_size,
        )

    async def _extract_instagram_video_url(self, url: str) -> dict[str, Any] | None:
        """Tenta extrair a URL direta de um vídeo do Instagram via GraphQL API."""
        shortcode = _extract_instagram_shortcode(url)
        if not shortcode:
            return None

        session = await self._get_ig_session()
        variables = json.dumps({"shortcode": shortcode})
        gql_url = (
            f"https://www.instagram.com/graphql/query/"
            f"?doc_id={_IG_GQL_DOC_ID}&variables={variables}"
        )

        try:
            async with session.get(
                gql_url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception as e:
            logger.debug("Erro na API GraphQL ao extrair vídeo do Instagram %s: %s", shortcode, e)
            return None

        if not isinstance(data, dict):
            return None

        payload = data.get("data")
        if not isinstance(payload, dict):
            return None

        media = payload.get("xdt_shortcode_media") or payload.get("shortcode_media")
        if not isinstance(media, dict) or not media:
            return None

        if media.get("is_video") and media.get("video_url"):
            owner = media.get("owner") or {}
            title = (
                media.get("accessibility_caption")
                or media.get("title")
                or f"Reel by {owner.get('username', 'unknown')}"
            )
            return {
                "video_url": media["video_url"],
                "title": title,
                "uploader": owner.get("full_name") or owner.get("username") or "",
                "thumbnail": media.get("display_url"),
                "duration": media.get("video_duration"),
            }
        return None

    async def _extract_instagram_video_url_via_dd(self, url: str) -> str | None:
        """Tenta extrair o link direto de vídeo do Instagram usando ddinstagram.com como proxy."""
        parsed = urlparse(url)
        dd_url = url
        if parsed.hostname in ("www.instagram.com", "instagram.com", "www.instagr.am", "instagr.am"):
            parsed = parsed._replace(netloc="ddinstagram.com")
            dd_url = parsed.geturl()

        session = await self._get_session()
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
        }
        try:
            async with session.get(dd_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    # Procurar por og:video ou twitter:player:stream
                    for pattern in (
                        r'<meta\s+(?:property|name)="og:video"\s+content="([^"]+)"',
                        r'<meta\s+content="([^"]+)"\s+(?:property|name)="og:video"',
                        r'<meta\s+(?:property|name)="twitter:player:stream"\s+content="([^"]+)"',
                    ):
                        m = re.search(pattern, html, re.IGNORECASE)
                        if m:
                            video_url = html_mod.unescape(m.group(1))
                            if video_url.startswith("http"):
                                return video_url
        except Exception as e:
            logger.debug("Erro ao extrair via ddinstagram: %s", e)
        return None

    async def download_video(self, url: str, quality: str) -> DownloadResult | None:
        """Baixa um vídeo na qualidade especificada."""
        import yt_dlp

        # Se for do Instagram, tenta obter link direto de vídeo via GraphQL/ddinstagram para contornar bloqueios do yt-dlp
        if _is_instagram_url(url):
            gql_info = await self._extract_instagram_video_url(url)
            video_url = None
            title = "Sem título"
            thumbnail = None
            uploader = ""
            duration = None

            if gql_info and gql_info.get("video_url"):
                video_url = gql_info["video_url"]
                title = gql_info.get("title") or title
                thumbnail = gql_info.get("thumbnail") or thumbnail
                uploader = gql_info.get("uploader") or uploader
                duration = gql_info.get("duration") or duration
            else:
                # Fallback: tentar obter link direto via ddinstagram proxy
                dd_video_url = await self._extract_instagram_video_url_via_dd(url)
                if dd_video_url:
                    video_url = dd_video_url

            if video_url:
                file_id = uuid.uuid4().hex[:8]
                filepath = os.path.join(self._temp_dir, f"{file_id}.mp4")
                try:
                    session = await self._get_session()
                    async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            await asyncio.to_thread(self._save_file, filepath, data)
                            return DownloadResult(
                                filepath=filepath,
                                title=title,
                                duration=duration,
                                filesize=os.path.getsize(filepath),
                                thumbnail=thumbnail,
                                uploader=uploader,
                                url=video_url,
                            )
                except Exception as e:
                    logger.warning("Falha ao baixar vídeo direto do Instagram: %s", e)
                    # Caso falhe o download direto, prossegue com o fallback do yt-dlp

        fmt = VIDEO_FORMATS.get(quality)
        if not fmt:
            return None

        file_id = uuid.uuid4().hex[:8]
        output_path = os.path.join(self._temp_dir, f"{file_id}.%(ext)s")

        ydl_opts: dict[str, Any] = {
            "format": fmt,
            "outtmpl": output_path,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "postprocessors": [],
            **self._base_opts(),
        }

        def _download() -> DownloadResult | None:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        return None

                    # Encontrar o arquivo gerado
                    filepath = ydl.prepare_filename(info)
                    # Pode ter extensão diferente após merge
                    base = os.path.splitext(filepath)[0]
                    for ext in (".mp4", ".mkv", ".webm"):
                        candidate = base + ext
                        if os.path.exists(candidate):
                            filepath = candidate
                            break

                    if not os.path.exists(filepath):
                        logger.error(
                            "Arquivo não encontrado após download: %s", filepath
                        )
                        return None

                    # Prefer direct format/media URL if available
                    direct_url = info.get("url")
                    if not direct_url and "requested_downloads" in info:
                        downloads = info["requested_downloads"]
                        if downloads and isinstance(downloads, list):
                            direct_url = downloads[0].get("url") or downloads[0].get("webpage_url")

                    return DownloadResult(
                        filepath=filepath,
                        title=info.get("title") or "Sem título",
                        duration=info.get("duration"),
                        filesize=os.path.getsize(filepath),
                        thumbnail=info.get("thumbnail"),
                        uploader=info.get("uploader"),
                        url=direct_url or info.get("webpage_url", url),
                    )
            except yt_dlp.utils.DownloadError as e:
                clean_msg = re.sub(r'\x1b\[[0-9;]*m', '', str(e))
                if clean_msg.startswith("ERROR: "):
                    clean_msg = clean_msg[7:]
                logger.warning("Falha ao baixar vídeo %s: %s", url, clean_msg)
                raise DownloadError(clean_msg) from e
            except Exception as e:
                logger.exception("Erro inesperado ao baixar vídeo %s: %s", url, e)
                raise DownloadError("Erro inesperado ao processar o vídeo.") from e

        return await asyncio.get_running_loop().run_in_executor(None, _download)

    async def download_video_auto_fit(self, url: str) -> DownloadResult | None:
        """Tenta baixar o vídeo nas qualidades recomendadas de forma progressiva.

        Tenta 720p primeiro, se ultrapassar o limite do Discord tenta 480p, depois 360p.
        """
        # 1. Tentar 720p
        result = await self.download_video(url, "720p")
        if result and result.within_limit:
            return result

        # Se ultrapassar o limite, limpar e tentar 480p
        if result and result.filepath:
            self.cleanup_file(result.filepath)

        # 2. Tentar 480p
        result = await self.download_video(url, "480p")
        if result and result.within_limit:
            return result

        # Se ultrapassar o limite, limpar e tentar 360p
        if result and result.filepath:
            self.cleanup_file(result.filepath)

        # 3. Tentar 360p
        result = await self.download_video(url, "360p")
        return result

    async def download_audio(self, url: str, bitrate: str) -> DownloadResult | None:
        """Baixa apenas o áudio na qualidade especificada."""
        import yt_dlp

        br = AUDIO_FORMATS.get(bitrate)
        if not br:
            return None

        file_id = uuid.uuid4().hex[:8]
        output_path = os.path.join(self._temp_dir, f"{file_id}.%(ext)s")

        ydl_opts: dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": output_path,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": br,
                }
            ],
            **self._base_opts(),
        }

        def _download() -> DownloadResult | None:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        return None

                    # Arquivo final será .mp3
                    filepath = ydl.prepare_filename(info)
                    base = os.path.splitext(filepath)[0]
                    mp3_path = base + ".mp3"

                    if not os.path.exists(mp3_path):
                        # Tentar achar qualquer arquivo com o ID
                        for f in os.listdir(self._temp_dir):
                            if f.startswith(os.path.basename(base)):
                                mp3_path = os.path.join(self._temp_dir, f)
                                break

                    if not os.path.exists(mp3_path):
                        logger.error("Arquivo de áudio não encontrado: %s", mp3_path)
                        return None

                    return DownloadResult(
                        filepath=mp3_path,
                        title=info.get("title") or "Sem título",
                        duration=info.get("duration"),
                        filesize=os.path.getsize(mp3_path),
                        thumbnail=info.get("thumbnail"),
                        uploader=info.get("uploader"),
                        url=info.get("webpage_url", url),
                    )
            except yt_dlp.utils.DownloadError as e:
                clean_msg = re.sub(r'\x1b\[[0-9;]*m', '', str(e))
                if clean_msg.startswith("ERROR: "):
                    clean_msg = clean_msg[7:]
                logger.warning("Falha ao baixar áudio %s: %s", url, clean_msg)
                raise DownloadError(clean_msg) from e
            except Exception as e:
                logger.exception("Erro inesperado ao baixar áudio %s: %s", url, e)
                raise DownloadError("Erro inesperado ao processar o áudio.") from e

        return await asyncio.get_running_loop().run_in_executor(None, _download)

    async def download_image(
        self, url: str, *, source_url: str | None = None
    ) -> ImageDownloadResult | None:
        """Baixa uma imagem (ou conjunto de imagens) de uma URL direta.

        Retorna ``ImageDownloadResult`` com a lista de arquivos baixados,
        ou ``None`` se houver falha.
        """
        session = await self._get_session()

        filepaths: list[str] = []
        total_size = 0

        try:
            # Verificação de tamanho via HEAD
            async with session.head(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as head_resp:
                if head_resp.status == 200:
                    content_length = int(head_resp.headers.get("Content-Length", 0))
                    if content_length > DISCORD_FILE_LIMIT:
                        logger.info(
                            "Imagem excede limite do Discord na verificação HEAD (%.1f MB): %s",
                            content_length / (1024 * 1024),
                            url,
                        )
                        return ImageDownloadResult(
                            filepaths=[],
                            source_url=url,
                            total_size=content_length,
                        )

            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status != 200:
                    logger.warning("HTTP %s ao baixar imagem: %s", resp.status, url)
                    return None

                content_type = resp.content_type or ""
                if not content_type.startswith("image/"):
                    # Pode ser uma página HTML (ex.: post do Instagram).
                    # Tentar extrair imagens via yt-dlp como fallback.
                    logger.debug(
                        "Content-Type não é imagem (%s) para URL: %s — "
                        "tentando fallback via yt-dlp",
                        content_type,
                        url,
                    )
                    return await self._fallback_extract_images(url)

                # Determinar extensão pelo content-type
                ext = mimetypes.guess_extension(content_type) or ".png"
                # mimetypes pode retornar .jpe para jpeg
                if ext in (".jpe",):
                    ext = ".jpg"

                file_id = uuid.uuid4().hex[:8]
                filepath = os.path.join(self._temp_dir, f"{file_id}{ext}")

                data = await resp.read()

                # Verificar tamanho
                if len(data) > DISCORD_FILE_LIMIT:
                    logger.info(
                        "Imagem excede limite do Discord (%.1f MB): %s",
                        len(data) / (1024 * 1024),
                        url,
                    )
                    return ImageDownloadResult(
                        filepaths=[],
                        source_url=url,
                        total_size=len(data),
                    )

                await asyncio.to_thread(self._save_file, filepath, data)

                filepaths.append(filepath)
                total_size += len(data)

        except asyncio.TimeoutError:
            logger.warning("Timeout ao baixar imagem: %s", url)
            return None
        except Exception as e:
            logger.exception("Erro ao baixar imagem %s: %s", url, e)
            return None

        if not filepaths:
            return None

        return ImageDownloadResult(
            filepaths=filepaths,
            source_url=source_url or url,
            total_size=total_size,
        )

    async def _extract_twitter_images(self, url: str) -> dict[str, Any] | None:
        """Extrai imagens em resolução original de um tweet via vxtwitter.

        Faz scraping das meta tags ``og:title``, ``og:description`` e
        ``twitter:image`` da página do vxtwitter (proxy gratuito).
        O vxtwitter retorna as imagens no formato ``rendercombined.jpg?imgs=``
        quando há múltiplas fotos, ou uma URL direta do ``pbs.twimg.com``
        para imagem única.

        Retorna dict normalizado com ``_image_urls``, ``title``, ``uploader``
        ou ``None`` se o tweet não tiver fotos.
        """
        vx_url = _twitter_to_vxtwitter(url)
        if not vx_url:
            return None

        session = await self._get_session()

        # vxtwitter responde com og tags quando o User-Agent é de bot/crawler
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
            ),
        }

        try:
            async with session.get(
                vx_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    logger.debug("vxtwitter HTTP %s para %s", resp.status, url)
                    return None

                text = await resp.text()

        except asyncio.TimeoutError:
            logger.debug("Timeout no vxtwitter: %s", url)
            return None
        except Exception as e:
            logger.debug("Erro no vxtwitter %s: %s", url, e)
            return None

        # ── Extrair meta tags ─────────────────────────────────
        def _meta(prop: str) -> str | None:
            for pattern in (
                rf'<meta\s+(?:property|name)="{prop}"\s+content="([^"]+)"',
                rf'<meta\s+content="([^"]+)"\s+(?:property|name)="{prop}"',
            ):
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    return html_mod.unescape(m.group(1))
            return None

        # Se contiver tags de vídeo, não extrair como imagem
        is_video = False
        for prop in ("og:video", "og:video:url", "og:video:secure_url", "twitter:player"):
            if _meta(prop):
                is_video = True
                break
        
        tw_card = _meta("twitter:card")
        if tw_card == "player" or (tw_card and "video" in tw_card):
            is_video = True

        if is_video:
            logger.info("vxtwitter: post possui vídeo. Ignorando no extrator de imagens.")
            return None

        # twitter:image contém as URLs (rendercombined ou direta)
        tw_image = _meta("twitter:image")
        if not tw_image:
            return None

        image_urls = _parse_vxtwitter_images(tw_image)
        if not image_urls:
            return None

        # Metadados
        og_title = _meta("og:title") or ""
        og_desc = _meta("og:description") or ""

        # og:title do vxtwitter vem como "User (@handle)"
        uploader = og_title
        title = og_desc or f"Tweet by {uploader}"
        if len(title) > 120:
            title = title[:117] + "…"

        logger.info(
            "vxtwitter: %d imagem(ns) em %s",
            len(image_urls),
            url,
        )

        return {
            "_image_urls": image_urls,
            "title": title,
            "uploader": uploader,
            "description": "",
        }

    async def _extract_instagram_images(self, url: str) -> dict[str, Any] | None:
        """Extrai imagens em resolução original de um post do Instagram via
        GraphQL API (``doc_id`` endpoint).

        Retorna dict normalizado com ``_image_urls``, ``title``, ``uploader``
        ou ``None`` se falhar.
        """
        shortcode = _extract_instagram_shortcode(url)
        if not shortcode:
            return None

        session = await self._get_ig_session()

        variables = json.dumps({"shortcode": shortcode})
        gql_url = (
            f"https://www.instagram.com/graphql/query/"
            f"?doc_id={_IG_GQL_DOC_ID}&variables={variables}"
        )

        try:
            async with session.get(
                gql_url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    logger.debug(
                        "Instagram GraphQL HTTP %s para %s", resp.status, shortcode
                    )
                    return None

                ct = resp.content_type or ""
                if "json" not in ct:
                    logger.debug("Instagram GraphQL content-type inesperado: %s", ct)
                    return None

                data = await resp.json()

        except asyncio.TimeoutError:
            logger.debug("Timeout na GraphQL do Instagram: %s", shortcode)
            return None
        except Exception as e:
            logger.debug("Erro na GraphQL do Instagram %s: %s", shortcode, e)
            return None

        # Navegar a resposta GraphQL
        if not isinstance(data, dict):
            logger.debug(
                "Instagram GraphQL resposta inesperada para %s: %s",
                shortcode,
                type(data).__name__,
            )
            return None

        payload = data.get("data")
        if not isinstance(payload, dict):
            logger.debug("Instagram GraphQL sem data para %s", shortcode)
            return None

        media = payload.get("xdt_shortcode_media") or payload.get("shortcode_media")
        if not isinstance(media, dict):
            logger.debug("Instagram GraphQL media inesperada para %s", shortcode)
            return None

        if not media:
            logger.debug("Instagram GraphQL sem media para %s", shortcode)
            return None

        typename = media.get("__typename", "")
        owner = media.get("owner") or {}
        if not isinstance(owner, dict):
            owner = {}
        title = (
            media.get("accessibility_caption")
            or media.get("title")
            or f"Post by {owner.get('username', 'unknown')}"
        )
        uploader = owner.get("full_name") or owner.get("username") or ""

        image_urls: list[str] = []

        def _best_url_from_node(node: dict[str, Any]) -> str | None:
            """Pega a URL de maior resolução de um nó GraphQL."""
            resources = node.get("display_resources") or []
            if resources:
                valid_resources = [r for r in resources if isinstance(r, dict)]
                if not valid_resources:
                    return None

                best = max(
                    valid_resources,
                    key=lambda r: (
                        (r.get("config_width") or 0) * (r.get("config_height") or 0)
                    ),
                )
                src = best.get("src")
                if src:
                    return str(src)
            # Fallback: display_url (geralmente 1080p também)
            display = node.get("display_url")
            return str(display) if display else None

        if typename == "XDTGraphSidecar":
            # Carrossel — múltiplas imagens/vídeos
            sidecar = media.get("edge_sidecar_to_children") or {}
            if not isinstance(sidecar, dict):
                sidecar = {}

            edges = sidecar.get("edges") or []
            for edge in edges:
                if not isinstance(edge, dict):
                    continue

                node = edge.get("node") or {}
                if not isinstance(node, dict):
                    continue

                # Pular vídeos do carrossel (is_video=True)
                if node.get("is_video"):
                    continue
                best = _best_url_from_node(node)
                if best and best not in image_urls:
                    image_urls.append(best)
        else:
            # Post único (XDTGraphImage ou XDTGraphVideo)
            if not media.get("is_video"):
                best = _best_url_from_node(media)
                if best:
                    image_urls.append(best)

        if not image_urls:
            logger.debug(
                "Instagram GraphQL: nenhuma imagem em %s (tipo=%s)",
                shortcode,
                typename,
            )
            return None

        logger.info(
            "Instagram GraphQL: %d imagem(ns) em %s (%s)",
            len(image_urls),
            shortcode,
            typename,
        )

        return {
            "_image_urls": image_urls,
            "title": title,
            "uploader": uploader,
            "description": "",
        }

    async def _fallback_extract_images(self, url: str) -> ImageDownloadResult | None:
        """Fallback: extrai imagens de uma URL quando o download HTTP direto
        retorna HTML em vez de imagem (ex.: posts do Instagram)."""
        # 1. Extratores nativos por plataforma (resolução original, sem crop)
        platform_info = await self._extract_platform_images(url)
        if platform_info and platform_info.get("_image_urls"):
            return await self.download_images_from_urls(
                platform_info["_image_urls"], source_url=url
            )

        # 2. yt-dlp com ignore_no_formats_error
        info = await self.fetch_info_images(url)
        if info:
            image_urls = info.get("_image_urls", [])
            if image_urls:
                logger.info(
                    "Fallback yt-dlp encontrou %d imagem(ns) em %s",
                    len(image_urls),
                    url,
                )
                return await self.download_images_from_urls(image_urls, source_url=url)

        # 3. Fallback final: scraping de og:image / twitter:image
        return await self._scrape_og_and_download(url)

    async def scrape_og_images(self, url: str) -> dict[str, Any] | None:
        """Faz scraping de meta tags Open Graph de uma página web.

        Usa o User-Agent do Discord Bot para que redes sociais (Instagram,
        Twitter, etc.) retornem as meta tags ``og:image`` e ``twitter:image``
        corretamente (em vez de devolver uma SPA vazia).

        Retorna um dict com as chaves:
        - ``image_urls``: lista de URLs de imagem encontradas
        - ``title``: título do post (og:title)
        - ``description``: descrição (og:description)
        - ``uploader``: nome do site (og:site_name)
        Ou ``None`` se nada for encontrado.
        """
        session = await self._get_session()

        # User-Agent do Discord: redes sociais retornam og tags para bots/crawlers
        discord_headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            async with session.get(
                url,
                headers=discord_headers,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    logger.debug(
                        "HTTP %s ao fazer scraping OG de: %s", resp.status, url
                    )
                    return None

                ct = resp.content_type or ""
                if not ct.startswith("text/html"):
                    return None

                text = await resp.text()

        except asyncio.TimeoutError:
            logger.debug("Timeout ao fazer scraping OG de: %s", url)
            return None
        except Exception as e:
            logger.debug("Erro ao fazer scraping OG de %s: %s", url, e)
            return None

        # ── Extrair meta tags ─────────────────────────────────
        image_urls: list[str] = []

        def _extract_meta(prop: str) -> str | None:
            """Extrai o content de uma meta tag pelo property ou name."""
            # property="X" content="Y"  ou  content="Y" property="X"
            for pattern in (
                rf'<meta\s+property="{prop}"\s+content="([^"]+)"',
                rf'<meta\s+content="([^"]+)"\s+property="{prop}"',
                rf'<meta\s+name="{prop}"\s+content="([^"]+)"',
                rf'<meta\s+content="([^"]+)"\s+name="{prop}"',
            ):
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    return html_mod.unescape(m.group(1))
            return None

        # Se contiver tags de vídeo/player, não extrair como imagem
        is_video = False
        for prop in ("og:video", "og:video:url", "og:video:secure_url", "twitter:player", "twitter:player:stream"):
            if _extract_meta(prop):
                is_video = True
                break
        
        tw_card = _extract_meta("twitter:card")
        if tw_card == "player" or (tw_card and "video" in tw_card):
            is_video = True

        if is_video:
            logger.info("scrape_og_images: página possui tags de vídeo. Ignorando no extrator de imagens.")
            return None

        # og:image (principal)
        og_image = _extract_meta("og:image")
        if og_image and og_image.startswith("http"):
            image_urls.append(og_image)

        # twitter:image (fallback / pode ser diferente)
        tw_image = _extract_meta("twitter:image")
        if tw_image and tw_image.startswith("http") and tw_image not in image_urls:
            image_urls.append(tw_image)

        # og:image:url (variante)
        og_image_url = _extract_meta("og:image:url")
        if (
            og_image_url
            and og_image_url.startswith("http")
            and og_image_url not in image_urls
        ):
            image_urls.append(og_image_url)

        if not image_urls:
            return None

        title = _extract_meta("og:title") or _extract_meta("twitter:title") or ""
        description = (
            _extract_meta("og:description")
            or _extract_meta("twitter:description")
            or ""
        )
        site_name = _extract_meta("og:site_name") or ""

        logger.info(
            "Scraping OG encontrou %d imagem(ns) em %s: %s",
            len(image_urls),
            url,
            [u[:80] for u in image_urls],
        )

        return {
            "image_urls": image_urls,
            "title": title,
            "description": description,
            "uploader": site_name,
        }

    async def _scrape_og_and_download(self, url: str) -> ImageDownloadResult | None:
        """Extrai imagens via scraping de og:image e baixa os arquivos."""
        og_data = await self.scrape_og_images(url)
        if not og_data:
            return None

        image_urls: list[str] = og_data.get("image_urls", [])
        if not image_urls:
            return None

        return await self.download_images_from_urls(image_urls, source_url=url)

    async def check_is_image_url(self, url: str) -> bool:
        """Verifica via HEAD request se a URL aponta para uma imagem.

        Combina checagem estática (extensão) com verificação HTTP real.
        """
        # Checagem rápida por extensão / CDN
        if is_image_url(url):
            return True

        # Fallback: HEAD request para checar Content-Type
        try:
            session = await self._get_session()
            async with session.head(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=True,
            ) as resp:
                if resp.status == 200:
                    ct = resp.content_type or ""
                    return ct in IMAGE_CONTENT_TYPES or ct.startswith("image/")
        except Exception:
            pass

        return False

    async def check_has_images_only(self, url: str) -> dict[str, Any] | None:
        """Verifica se a URL contém apenas imagens (sem vídeo) via yt-dlp.

        Retorna o dict de info (com ``_image_urls``) se for um post de imagem,
        ou ``None`` se for vídeo normal ou se nada for encontrado.
        """
        return await self.fetch_info_images(url)

    async def _extract_platform_images(self, url: str) -> dict[str, Any] | None:
        """Tenta extrair imagens via extratores específicos por plataforma.

        - Instagram → GraphQL API (1080p, sem crop, carrossel)
        - Twitter/X → fxtwitter API (resolução original)

        Retorna dict normalizado ou ``None``.
        """
        if _is_instagram_url(url):
            return await self._extract_instagram_images(url)
        if _is_twitter_url(url):
            return await self._extract_twitter_images(url)
        return None

    async def extract_images_any_method(self, url: str) -> dict[str, Any] | None:
        """Tenta extrair imagens de uma URL usando todos os métodos disponíveis.

        Ordem de tentativa:
        1. Extratores nativos por plataforma (Instagram, Twitter/X)
        2. yt-dlp com ``ignore_no_formats_error``
        3. Scraping de ``og:image`` / ``twitter:image``

        Retorna um dict normalizado com:
        - ``_image_urls``: lista de URLs de imagem
        - ``title``, ``uploader``, ``description``
        Ou ``None`` se nenhum método funcionar.
        """
        # 1. Extratores nativos (full-res)
        try:
            platform_info = await self._extract_platform_images(url)
        except Exception as e:
            logger.debug("Extrator nativo de imagens falhou para %s: %s", url, e)
            platform_info = None

        if platform_info and platform_info.get("_image_urls"):
            return platform_info

        # 2. yt-dlp
        try:
            info = await self.fetch_info_images(url)
        except Exception as e:
            logger.debug("yt-dlp imagens falhou para %s: %s", url, e)
            info = None

        if info and info.get("_image_urls"):
            return info

        # 3. OG scraping
        try:
            og_data = await self.scrape_og_images(url)
        except Exception as e:
            logger.debug("OG scraping de imagens falhou para %s: %s", url, e)
            og_data = None

        if og_data and og_data.get("image_urls"):
            # Normalizar para o mesmo formato que fetch_info_images
            return {
                "_image_urls": og_data["image_urls"],
                "title": og_data.get("title", ""),
                "uploader": og_data.get("uploader", ""),
                "description": og_data.get("description", ""),
            }

        return None

    def cleanup_file(self, filepath: str) -> None:
        """Remove um arquivo temporário de download."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists(filepath):
                logger.error("Arquivo ainda existe após remoção: %s", filepath)
        except OSError:
            logger.exception("Erro ao remover arquivo %s", filepath)

    def cleanup_all(self) -> None:
        """Remove todos os arquivos temporários do diretório de downloads."""
        if not os.path.exists(self._temp_dir):
            return
        for f in os.listdir(self._temp_dir):
            self.cleanup_file(os.path.join(self._temp_dir, f))
        logger.debug("Limpeza completa do diretório de downloads.")

    def cleanup_files(self, filepaths: list[str]) -> None:
        """Remove múltiplos arquivos temporários."""
        for fp in filepaths:
            self.cleanup_file(fp)

    async def close(self) -> None:
        """Limpa tudo ao desligar o bot, incluindo o diretório temporário."""
        # Fechar sessões HTTP
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        if self._ig_session and not self._ig_session.closed:
            await self._ig_session.close()

        self.cleanup_all()
        # Remover o diretório temporário em si (cleanup_all só limpa os arquivos dentro)
        try:
            if os.path.isdir(self._temp_dir):
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                logger.debug("Diretório temporário removido: %s", self._temp_dir)
        except OSError:
            logger.exception("Erro ao remover diretório temporário %s", self._temp_dir)
