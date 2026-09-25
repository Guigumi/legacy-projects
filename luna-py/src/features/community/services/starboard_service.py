from __future__ import annotations

from features.community.repositories.starboard_repository import StarboardRepository


class StarboardService:
    """Serviço de lógica de negócio para o Starboard."""

    def __init__(self, repo: StarboardRepository) -> None:
        self.repo = repo

    async def get_config(self, guild_id: int) -> dict | None:
        return await self.repo.get_config(guild_id)

    async def save_config(
        self, guild_id: int, channel_id: int, emoji: str, min_stars: int, enabled: int = 1
    ) -> None:
        await self.repo.save_config(guild_id, channel_id, emoji, min_stars, enabled)

    async def disable_starboard(self, guild_id: int) -> None:
        await self.repo.disable_starboard(guild_id)

    async def get_starred_message(self, message_id: int) -> dict | None:
        return await self.repo.get_starred_message(message_id)

    async def register_starred_message(
        self,
        message_id: int,
        starboard_message_id: int,
        guild_id: int,
        channel_id: int,
        star_count: int,
    ) -> None:
        await self.repo.add_starred_message(
            message_id, starboard_message_id, guild_id, channel_id, star_count
        )

    async def update_starred_count(self, message_id: int, star_count: int) -> None:
        await self.repo.update_starred_message_count(message_id, star_count)

    async def remove_starred_message(self, message_id: int) -> None:
        await self.repo.delete_starred_message(message_id)

    async def process_reaction(
        self,
        guild_id: int,
        message_id: int,
        author_id: int,
        reactor_id: int,
        reaction_emoji: str,
        reaction_count: int,
    ) -> dict:
        """Determina a ação a ser tomada com base na reação recebida.

        Retorna um dicionário com a ação ('create', 'update', 'delete', 'none')
        e metadados necessários.
        """
        config = await self.repo.get_config(guild_id)
        if not config or not config.get("enabled"):
            return {"action": "none"}

        # Limpa o emoji para comparação (se for customizado <:name:id> ou unicode)
        config_emoji = config["emoji"]

        # Comparação básica de string (pode vir no formato unicode ou tag completa)
        if reaction_emoji != config_emoji:
            # Caso seja emoji customizado, verifica se o ID ou nome coincide
            if ":" in reaction_emoji and ":" in config_emoji:
                # <:name:id>
                try:
                    r_id = reaction_emoji.split(":")[-1].replace(">", "")
                    c_id = config_emoji.split(":")[-1].replace(">", "")
                    if r_id != c_id:
                        return {"action": "none"}
                except Exception:
                    return {"action": "none"}
            else:
                return {"action": "none"}

        # Bloqueia self-starring
        if author_id == reactor_id:
            return {"action": "self_star", "min_stars": config["min_stars"]}

        starred = await self.repo.get_starred_message(message_id)
        min_stars = config["min_stars"]

        if reaction_count >= min_stars:
            if not starred:
                return {
                    "action": "create",
                    "channel_id": config["channel_id"],
                    "emoji": config_emoji,
                    "count": reaction_count,
                }
            else:
                return {
                    "action": "update",
                    "starboard_message_id": starred["starboard_message_id"],
                    "channel_id": starred["channel_id"],
                    "emoji": config_emoji,
                    "count": reaction_count,
                }
        else:
            if starred:
                return {
                    "action": "delete",
                    "starboard_message_id": starred["starboard_message_id"],
                    "channel_id": starred["channel_id"],
                }
            return {"action": "none"}
