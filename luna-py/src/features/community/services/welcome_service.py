"""
Lógica de negócio para mensagens de boas-vindas.
"""

from __future__ import annotations

import logging
import time

import discord

from core.events import BotEvent, EventBus
from features.community.repositories.welcome_repository import WelcomeRepository
from core.utils.embed_builder import EmbedBuilder

logger = logging.getLogger(__name__)

_CACHE_TTL = 300.0


class WelcomeService:
    """Serviço de Welcome (Mensagens customizáveis de Entrada e Saída)."""

    def __init__(self, repo: WelcomeRepository, event_bus: EventBus) -> None:
        self.repo = repo
        self.bus = event_bus
        self._cache: dict[tuple[int, str], tuple[dict, float]] = {}

    def _invalidate(self, guild_id: int, event_type: str) -> None:
        self._cache.pop((guild_id, event_type), None)

    async def get_config(self, guild_id: int, event_type: str) -> dict:
        now = time.monotonic()
        cache_key = (guild_id, event_type)
        cached = self._cache.get(cache_key)
        if cached and (now - cached[1]) < _CACHE_TTL:
            return cached[0]

        config = await self.repo.get_config(guild_id, event_type)
        if config is not None:
            self._cache[cache_key] = (config, now)
            return config
        return {}

    async def update_config(self, guild_id: int, event_type: str, changed_by: int, **kwargs) -> None:
        await self.repo.update_config(guild_id, event_type, **kwargs)
        self._invalidate(guild_id, event_type)
        await self.bus.emit(
            guild_id,
            BotEvent.CONFIG_CHANGED,
            {"changed_by": changed_by, "fields": list(kwargs.keys()), "event_type": event_type},
        )

    def apply_variables(self, text: str | None, member: discord.Member, config: dict) -> str | None:
        """Substitui as variáveis pelo valor real do membro e do servidor."""
        if not text:
            return None

        guild = member.guild
        emoji = config.get("welcome_emoji") or "👋"

        # Variáveis do Usuário
        text = text.replace("{@user}", member.mention)
        text = text.replace("{user}", member.display_name)
        text = text.replace("{user.id}", str(member.id))
        text = text.replace("{user.avatar}", member.display_avatar.url)

        # Variáveis do Servidor
        text = text.replace("{server}", guild.name)
        text = text.replace("{server.member_count}", str(guild.member_count or 0))
        text = text.replace("{server.icon}", guild.icon.url if guild.icon else "")

        # Variável Genérica
        text = text.replace("{emoji}", emoji)

        return text

    def build_welcome_message(self, member: discord.Member, config: dict) -> tuple[str | None, discord.Embed | None]:
        """Constrói a mensagem e o embed baseado na configuração e nas variáveis."""
        
        # Conteúdo externo da mensagem (fora do embed)
        content = self.apply_variables(config.get("content"), member, config)

        # Embed properties
        title = self.apply_variables(config.get("embed_title"), member, config)
        desc = self.apply_variables(config.get("embed_description"), member, config)
        color_hex = config.get("embed_color")
        
        thumbnail = self.apply_variables(config.get("embed_thumbnail"), member, config)
        image = self.apply_variables(config.get("embed_image"), member, config)
        
        footer_text = self.apply_variables(config.get("embed_footer_text"), member, config)
        footer_icon = self.apply_variables(config.get("embed_footer_icon"), member, config)
        
        author_name = self.apply_variables(config.get("embed_author_name"), member, config)
        author_icon = self.apply_variables(config.get("embed_author_icon"), member, config)

        # Se não há título e nem descrição e nem imagem, talvez o ADM queira apenas enviar 'content'
        if not any([title, desc, image, author_name]):
            return content, None

        builder = EmbedBuilder.default()
        
        if title:
            builder.title(title)
        if desc:
            builder.description(desc)
            
        if color_hex:
            try:
                if color_hex.startswith("#"):
                    color_hex = color_hex[1:]
                builder.color(discord.Color(int(color_hex, 16)))
            except ValueError:
                pass  # Ignora cor inválida

        if thumbnail:
            builder.thumbnail(thumbnail)
            
        if image:
            builder.image(image)
            
        if footer_text:
            builder.footer(text=footer_text, icon_url=footer_icon)
            
        if author_name:
            builder.author(name=author_name, icon_url=author_icon)

        return content, builder.build()
