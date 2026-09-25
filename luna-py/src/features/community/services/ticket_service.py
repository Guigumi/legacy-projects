from __future__ import annotations

from features.community.repositories.ticket_repository import TicketRepository


class TicketService:
    """Serviço de lógica de negócio para o sistema de tickets."""

    def __init__(self, repo: TicketRepository) -> None:
        self.repo = repo

    async def get_config(self, guild_id: int) -> dict | None:
        """Busca a configuração do sistema de tickets para a guilda."""
        return await self.repo.get_config(guild_id)

    async def get_active_ticket_by_user(self, guild_id: int, creator_id: int) -> dict | None:
        """Busca se o usuário já possui um ticket ativo/aberto na guilda."""
        return await self.repo.get_active_ticket_by_user(guild_id, creator_id)

    async def save_config(
        self,
        guild_id: int,
        category_id: int,
        support_role_id: int,
        log_channel_id: int | None = None,
    ) -> None:
        """Salva a configuração do sistema de tickets para a guilda."""
        await self.repo.save_config(guild_id, category_id, support_role_id, log_channel_id)

    async def get_next_ticket_number(self, guild_id: int) -> int:
        """Gera e retorna o próximo número sequencial de ticket."""
        return await self.repo.get_next_ticket_number(guild_id)

    async def create_ticket(
        self,
        guild_id: int,
        channel_id: int,
        creator_id: int,
    ) -> None:
        """Cria e registra o ticket aberto no banco de dados."""
        await self.repo.create_ticket(guild_id, channel_id, creator_id)

    async def get_ticket_by_channel(self, channel_id: int) -> dict | None:
        """Busca informações de um ticket associado a um canal."""
        return await self.repo.get_ticket_by_channel(channel_id)

    async def claim_ticket(self, channel_id: int, claimant_id: int) -> None:
        """Registra a atribuição do ticket a um staff."""
        await self.repo.claim_ticket(channel_id, claimant_id)

    async def close_ticket(self, channel_id: int, closed_by: int) -> None:
        """Registra o fechamento do ticket."""
        await self.repo.close_ticket(channel_id, closed_by)
