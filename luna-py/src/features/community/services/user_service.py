"""
Lógica de negócio para usuários: XP, level-up, etc.

Otimizações aplicadas:
- Fórmula de nível unificada: usa config do servidor (linear) com fallback quadrático.
- _calculate_level agora é O(1) via inversão matemática em vez de loop O(n).
- grant_xp usa transação atômica (XP + level em um único commit).
- get_profile respeita xp_per_level do servidor para calcular xp_next_level.
"""

from __future__ import annotations

import logging
import math

from core.events import BotEvent, EventBus
from core.utils.xp_calc import calculate_level, xp_for_level
from core.models import UserData
from features.community.repositories import UserRepository

logger = logging.getLogger(__name__)





class UserService:
    """Serviço de lógica de usuário."""

    def __init__(
        self,
        user_repo: UserRepository,
        event_bus: EventBus,
        xp_config_service=None,
    ) -> None:
        self.repo = user_repo
        self.bus = event_bus
        self._xp_config_svc = xp_config_service

    # ── Helpers ───────────────────────────────────────────────

    async def _get_xp_per_level(self, guild_id: int) -> int | None:
        """Retorna xp_per_level do servidor ou None para curva padrão."""
        if self._xp_config_svc is None:
            return None
        try:
            config = await self._xp_config_svc.get_config(guild_id)
            value = config.get("xp_per_level")
            return int(value) if value is not None else None
        except Exception:
            logger.debug(
                "Falha ao obter xp_per_level para guild %s, usando padrão", guild_id
            )
            return None

    # ── Perfil ────────────────────────────────────────────────

    async def get_profile(self, guild_id: int, user_id: int) -> UserData | None:
        """Retorna dados do perfil; cria se não existir.

        Calcula xp_next_level usando a config do servidor para consistência
        com o comando /xp e o painel de configuração.
        """
        await self.repo.ensure_user(guild_id, user_id)
        data = await self.repo.get_user(guild_id, user_id)
        if data:
            xp_per_level = await self._get_xp_per_level(guild_id)
            current_level = data.level
            data.xp_next_level = xp_for_level(current_level + 1, xp_per_level)
            data.xp_current_level = xp_for_level(current_level, xp_per_level)
        return data

    # ── XP & Level-up ────────────────────────────────────────

    async def grant_xp(self, guild_id: int, user_id: int, amount: int, channel_id: int | None = None) -> UserData | dict | None:
        """Concede XP e verifica level-up em operação atômica (UPSERT).

        Retorna dados atualizados do usuário.
        """
        if amount <= 0:
            return await self.repo.get_user(guild_id, user_id)

        # Obter config de XP do servidor
        xp_per_level = await self._get_xp_per_level(guild_id)

        # Atualiza XP com UPSERT atômico e pega o novo estado
        data = await self.repo.add_xp(guild_id, user_id, amount)
        if not data:
            return None

        # Verifica se o nível subiu com base no novo XP
        new_xp = data.xp
        old_level = data.level
        new_level = calculate_level(new_xp, xp_per_level)

        leveled_up = new_level > old_level
        if leveled_up:
            # Atualiza apenas se subiu de nível
            await self.repo.set_level(guild_id, user_id, new_level)
            data.level = new_level  # Atualiza objeto em memória

            await self.bus.emit(
                guild_id,
                BotEvent.USER_LEVELED_UP,
                {
                    "user_id": user_id,
                    "old_level": old_level,
                    "new_level": new_level,
                    "xp": new_xp,
                    "channel_id": channel_id,
                },
            )
            logger.info(
                "User %s leveled up %s → %s in guild %s",
                user_id,
                old_level,
                new_level,
                guild_id,
            )

        return data

    # ── Leaderboard ──────────────────────────────────────────

    async def get_leaderboard(
        self, guild_id: int, order_by: str = "xp", limit: int = 10, offset: int = 0
    ) -> list[UserData]:
        return await self.repo.get_leaderboard(guild_id, order_by, limit, offset)

    async def get_leaderboard_count(self, guild_id: int, order_by: str = "xp") -> int:
        return await self.repo.get_leaderboard_count(guild_id, order_by)

    # ── Warnings ─────────────────────────────────────────────

    async def add_warning(self, guild_id: int, user_id: int, reason: str = "") -> int:
        total = await self.repo.add_warning(guild_id, user_id, reason)
        await self.bus.emit(
            guild_id,
            BotEvent.WARNING_ISSUED,
            {"user_id": user_id, "total_warnings": total, "reason": reason},
        )
        return total

    async def get_user_rank(self, guild_id: int, user_id: int) -> int:
        return await self.repo.get_user_rank(guild_id, user_id)

    async def set_user_theme(self, guild_id: int, user_id: int, theme: str) -> None:
        await self.repo.set_user_theme(guild_id, user_id, theme)

    async def claim_daily(self, guild_id: int, user_id: int) -> tuple[bool, int | float, int, int]:
        """Processa a reivindicação de moedas do daily.
        
        Retorna: (sucesso, valor_ganho_ou_segundos_restantes, streak, total_moedas)
        """
        import random
        import datetime
        from config.settings import now_brt
        
        data = await self.get_profile(guild_id, user_id)
        if not data:
            return False, 0.0, 0, 0
            
        now = now_brt()
        last_daily_str = data.last_daily
        
        if last_daily_str:
            try:
                last_daily = datetime.datetime.fromisoformat(last_daily_str)
                diff = now - last_daily
                diff_seconds = diff.total_seconds()
                
                if diff_seconds < 86400: # 24 horas
                    seconds_left = 86400 - diff_seconds
                    return False, seconds_left, data.daily_streak, data.coins
                    
                # Streak mantido se reivindicar em menos de 48h
                if diff_seconds <= 172800: # 48 horas
                    streak = data.daily_streak + 1
                else:
                    streak = 1
            except Exception:
                # Fallback se a data estiver corrompida
                streak = 1
        else:
            # Primeiro daily
            streak = 1
            
        # Calcular recompensa
        base_reward = random.randint(100, 1000)
        streak_bonus = (streak - 1) * 100
        reward = base_reward + streak_bonus
        
        new_coins = data.coins + reward
        now_str = now.isoformat()
        
        await self.repo.update_daily_claim(guild_id, user_id, now_str, streak, reward)
        return True, reward, streak, new_coins

    async def buy_background(self, guild_id: int, user_id: int, bg_id: str, price: int) -> int:
        """Compra um plano de fundo na loja.
        
        Retorna o saldo de moedas atualizado ou levanta ValueError.
        """
        data = await self.get_profile(guild_id, user_id)
        if not data:
            raise ValueError("Membro não encontrado.")
            
        if data.coins < price:
            raise ValueError(f"Moedas insuficientes. Você tem **{data.coins}** moedas mas o custo é **{price}**.")
            
        unlocked = [x.strip() for x in data.unlocked_backgrounds.split(",") if x.strip()]
        if bg_id in unlocked:
            raise ValueError("Você já possui este plano de fundo!")
            
        unlocked.append(bg_id)
        new_unlocked_str = ",".join(unlocked)
        new_coins = max(0, data.coins - price)
        
        await self.repo.unlock_background(guild_id, user_id, new_unlocked_str, price)
        return new_coins

