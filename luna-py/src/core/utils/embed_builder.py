"""
Builder padronizado de embeds.
Garante consistência visual em todo o bot.
"""

from __future__ import annotations

import discord

from config.settings import Colors, Separators


class EmbedBuilder:
    """Fluent interface para criar embeds consistentes."""

    def __init__(self) -> None:
        self._embed = discord.Embed(color=Colors.DEFAULT)

    # ── Factory Methods ───────────────────────────────────────

    @classmethod
    def default(
        cls, title: str | None = None, description: str | None = None
    ) -> EmbedBuilder:
        b = cls()
        if title:
            b._embed.title = title
        if description:
            b._embed.description = description
        return b

    @classmethod
    def success(cls, description: str) -> EmbedBuilder:
        b = cls()
        b._embed.color = Colors.SUCCESS
        b._embed.description = description
        return b

    @classmethod
    def error_user(cls, description: str) -> EmbedBuilder:
        b = cls()
        b._embed.color = Colors.ERROR_USER
        b._embed.description = description
        return b

    @classmethod
    def error_internal(cls, description: str | None = None) -> EmbedBuilder:
        b = cls()
        b._embed.color = Colors.ERROR_INTERNAL
        b._embed.description = (
            description or "Algo deu errado. Se persistir, reporte ao suporte."
        )
        return b

    @classmethod
    def alert(cls, description: str) -> EmbedBuilder:
        b = cls()
        b._embed.color = Colors.ALERT
        b._embed.description = description
        return b

    # ── Builder Methods ───────────────────────────────────────

    def color(self, color: discord.Color) -> EmbedBuilder:
        self._embed.color = color
        return self

    def title(self, text: str) -> EmbedBuilder:
        self._embed.title = text
        return self

    def description(self, text: str) -> EmbedBuilder:
        self._embed.description = text
        return self

    def section(self, title: str) -> EmbedBuilder:
        """Adiciona um separador de seção visual."""
        self._embed.add_field(
            name=Separators.title(title),
            value="",
            inline=False,
        )
        return self

    def field(self, name: str, value: str, inline: bool = False) -> EmbedBuilder:
        self._embed.add_field(name=name, value=value, inline=inline)
        return self

    def stat(self, name: str, value: str | int) -> EmbedBuilder:
        """Campo inline formatado como estatística."""
        self._embed.add_field(name=name, value=f"`{value}`", inline=True)
        return self

    def author(self, name: str, icon_url: str | None = None) -> EmbedBuilder:
        self._embed.set_author(name=name, icon_url=icon_url)
        return self

    def thumbnail(self, url: str) -> EmbedBuilder:
        self._embed.set_thumbnail(url=url)
        return self

    def image(self, url: str) -> EmbedBuilder:
        self._embed.set_image(url=url)
        return self

    def footer(self, text: str, icon_url: str | None = None) -> EmbedBuilder:
        self._embed.set_footer(text=text, icon_url=icon_url)
        return self

    def timestamp(self) -> EmbedBuilder:
        from config.settings import now_brt

        self._embed.timestamp = now_brt()
        return self

    def build(self) -> discord.Embed:
        return self._embed.copy()
