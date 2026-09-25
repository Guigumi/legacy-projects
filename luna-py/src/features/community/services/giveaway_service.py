from __future__ import annotations

import asyncio
import logging
import random
import json
from datetime import datetime
from config.settings import BRT, now_brt
from core.events import BotEvent, EventBus
from features.community.repositories.giveaway_repository import GiveawayRepository

logger = logging.getLogger(__name__)

class GiveawayService:
    def __init__(self, repo: GiveawayRepository, event_bus: EventBus) -> None:
        self.repo = repo
        self.bus = event_bus
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._check_loop())

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def create_giveaway(
        self, guild_id: int, channel_id: int, creator_id: int, 
        prize: str, winner_count: int, ends_at: datetime
    ) -> int:
        return await self.repo.create_giveaway(
            guild_id, channel_id, creator_id, prize, winner_count, ends_at.isoformat()
        )

    async def add_entry(self, giveaway_id: int, user_id: int) -> bool:
        return await self.repo.add_participant(giveaway_id, user_id)

    async def remove_entry(self, giveaway_id: int, user_id: int) -> None:
        await self.repo.remove_participant(giveaway_id, user_id)

    async def get_giveaway(self, giveaway_id: int) -> dict | None:
        return await self.repo.get_giveaway(giveaway_id)

    async def cancel_giveaway(self, giveaway_id: int) -> None:
        await self.repo.cancel_giveaway(giveaway_id)

    async def _check_loop(self) -> None:
        while True:
            try:
                active = await self.repo.get_active_giveaways()
                now = now_brt()
                for gw in active:
                    ends_at = datetime.fromisoformat(gw["ends_at"])
                    if ends_at.tzinfo is None:
                        ends_at = ends_at.replace(tzinfo=BRT)
                    
                    if now >= ends_at:
                        await self.process_giveaway_end(gw)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Erro no loop de giveaways")
            await asyncio.sleep(30)

    async def process_giveaway_end(self, gw: dict) -> None:
        participants = await self.repo.get_participants(gw["id"])
        
        if not participants:
            winners = []
        else:
            # Selecionar ganhadores únicos
            count = min(len(participants), gw["winner_count"])
            winners = random.sample(participants, count)

        await self.repo.end_giveaway(gw["id"], json.dumps(winners))
        
        # Emitir evento para o Cog lidar com o anúncio
        await self.bus.emit(
            gw["guild_id"],
            BotEvent.GIVEAWAY_ENDED,
            {"giveaway": gw, "winners": winners}
        )

    async def reroll(self, giveaway_id: int) -> list[int] | None:
        gw = await self.repo.get_giveaway(giveaway_id)
        if not gw or not gw["ended"]:
            return None
            
        participants = await self.repo.get_participants(gw["id"])
        if not participants:
            return []
            
        count = min(len(participants), gw["winner_count"])
        winners = random.sample(participants, count)
        
        await self.repo.end_giveaway(gw["id"], json.dumps(winners))
        return winners

    async def get_giveaways(self, guild_id: int) -> list[dict]:
        return await self.repo.get_giveaways(guild_id)
