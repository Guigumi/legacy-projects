"""
Serviço de integração com a Steam Store API.
Busca jogos, preços, avaliações, sinopse e conquistas.
"""

from __future__ import annotations

import html
import logging
import re

import aiohttp

logger = logging.getLogger(__name__)

STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
STORE_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
STORE_REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"
ACHIEVEMENTS_URL = "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
PLAYER_COUNT_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"

# Limpar tags HTML da sinopse
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove tags HTML e decodifica entidades."""
    clean = _TAG_RE.sub("", text)
    return html.unescape(clean).strip()


def _truncate(text: str, length: int = 300) -> str:
    if len(text) <= length:
        return text
    return text[: length - 1].rsplit(" ", 1)[0] + "…"


class SteamService:
    """Cliente async para a Steam Store API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def search_game(self, query: str) -> dict | None:
        """Busca um jogo pelo nome. Retorna o primeiro resultado."""
        session = await self._get_session()
        params = {"term": query, "l": "english", "cc": "US"}
        try:
            async with session.get(STORE_SEARCH_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Steam search falhou: %s", resp.status)
                    return None
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.exception("Erro no search Steam: %s", e)
            return None

        items = data.get("items") or []
        if not items:
            return None

        # Priorizar match exato pelo nome
        query_lower = query.lower().strip()
        for item in items:
            if item.get("name", "").lower().strip() == query_lower:
                return item

        # Senão, priorizar quem começa com o termo
        for item in items:
            if item.get("name", "").lower().startswith(query_lower):
                return item

        return items[0]

    async def get_app_details(self, appid: int) -> dict | None:
        """Busca detalhes completos de um jogo."""
        session = await self._get_session()
        params = {"appids": str(appid), "l": "portuguese", "cc": "BR"}
        try:
            async with session.get(STORE_DETAILS_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Steam details falhou: %s", resp.status)
                    return None
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.exception("Erro no details Steam: %s", e)
            return None

        app_data = data.get(str(appid))
        if not app_data or not app_data.get("success"):
            return None
        return app_data.get("data")

    async def get_review_summary(self, appid: int) -> dict | None:
        """Busca resumo de avaliações de um jogo."""
        session = await self._get_session()
        url = STORE_REVIEWS_URL.format(appid=appid)
        params = {"json": "1", "language": "all", "purchase_type": "all"}
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Steam reviews falhou: %s", resp.status)
                    return None
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.exception("Erro no reviews Steam: %s", e)
            return None
        return data.get("query_summary")

    async def get_achievement_count(self, appid: int) -> int:
        """Retorna quantidade de conquistas de um jogo."""
        session = await self._get_session()
        params = {"key": self.api_key, "appid": str(appid)}
        try:
            async with session.get(ACHIEVEMENTS_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Steam achievements falhou: %s", resp.status)
                    return 0
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.exception("Erro no achievements Steam: %s", e)
            return 0

        game = data.get("game") or {}
        stats = game.get("availableGameStats") or {}
        achievements = stats.get("achievements") or []
        return len(achievements)

    async def get_player_count(self, appid: int) -> int:
        """Busca quantidade de jogadores online atuais."""
        session = await self._get_session()
        params = {"appid": str(appid)}
        try:
            async with session.get(PLAYER_COUNT_URL, params=params) as resp:
                if resp.status != 200:
                    return 0
                data = await resp.json()
                return data.get("response", {}).get("player_count", 0)
        except Exception:
            return 0

    async def get_screenshots(self, app_id: int) -> list[str]:
        """Busca URLs de screenshots de um jogo."""
        details = await self.get_app_details(app_id)
        if not details:
            return []
        screenshots = details.get("screenshots") or []
        return [s.get("path_full") for s in screenshots if s.get("path_full")]

    async def get_full_game_info(self, query: str) -> dict | None:
        """Busca completa: search → details + reviews + achievements."""
        search = await self.search_game(query)
        if not search:
            return None

        appid = search["id"]
        details = await self.get_app_details(appid)
        if not details:
            return None

        reviews = await self.get_review_summary(appid)
        achievements = await self.get_achievement_count(appid)
        player_count = await self.get_player_count(appid)

        # Preço
        price_info = details.get("price_overview")
        if price_info:
            price = price_info.get("final_formatted", "?")
            discount = price_info.get("discount_percent", 0)
            original = price_info.get("initial_formatted", "")
        elif details.get("is_free"):
            price = "Gratuito"
            discount = 0
            original = ""
        else:
            price = "Indisponível"
            discount = 0
            original = ""

        # Avaliação
        if reviews:
            total_reviews = reviews.get("total_reviews", 0)
            positive = reviews.get("total_positive", 0)
            if total_reviews > 0:
                pct = round((positive / total_reviews) * 100)
                desc = reviews.get("review_score_desc", "")
                review_str = f"{desc} ({pct}% de {_fmt_reviews(total_reviews)})"
            else:
                review_str = "Sem avaliações"
        else:
            review_str = "Sem avaliações"

        # Sinopse
        raw_desc = (
            details.get("short_description") or details.get("about_the_game") or ""
        )
        synopsis = _truncate(_strip_html(raw_desc), 300)

        # Gêneros
        genres = [g["description"] for g in (details.get("genres") or [])[:4]]

        # Imagem
        header_image = details.get("header_image", "")

        # Desenvolvedores / Publishers
        developers = ", ".join(details.get("developers") or ["?"])
        publishers = ", ".join(details.get("publishers") or ["?"])

        # Plataformas
        platforms = details.get("platforms") or {}
        plat_list = []
        if platforms.get("windows"):
            plat_list.append("")
        if platforms.get("mac"):
            plat_list.append("")
        if platforms.get("linux"):
            plat_list.append("")

        return {
            "appid": appid,
            "name": details.get("name", search.get("name", "?")),
            "price": price,
            "discount": discount,
            "original_price": original,
            "review": review_str,
            "synopsis": synopsis,
            "achievements": achievements,
            "genres": genres,
            "header_image": header_image,
            "developers": developers,
            "publishers": publishers,
            "platforms": " ".join(plat_list) if plat_list else "?",
            "player_count": player_count,
            "url": f"https://store.steampowered.com/app/{appid}",
        }

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


def _fmt_reviews(n: int) -> str:
    """Formata quantidade de reviews."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
