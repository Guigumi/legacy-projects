"""
Sistema de Apostas e Jogos de Azar

Jogos de aposta com Mora: slots, coinflip, roleta.
Com controles de risco: cooldown, limite diário, odds balanceadas.
"""
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from typing import Optional
import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from config import Colors
from services.repositories import user_repo, guild_repo
from services.event_bus import event_bus, BotEvent
from services.embed_helpers import embed_disabled
from cogs.economy.mora import mora_emoji, get_mora, add_mora, remove_mora

logger = logging.getLogger(__name__)


def format_number(number: int) -> str:
    """Formata número com separadores de milhar"""
    return f"{number:,}".replace(',', '.')


# ======================== CONFIGURAÇÃO ========================

# Valores padrão
DEFAULT_CONFIG = {
    "enabled": True,
    "min_bet": 50,
    "max_bet": 50000,
    "daily_loss_limit": 10000,
    "house_edge": 0.02,
    "slots_enabled": True,
    "coinflip_enabled": True,
    "roulette_enabled": True,
}

# Slots config
SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "⭐"]
SLOT_PAYOUTS = {
    "7️⃣7️⃣7️⃣": 8.0,    # Jackpot (reduzido de 10x)
    "💎💎💎": 4.0,
    "⭐⭐⭐": 3.5,
    "🍇🍇🍇": 2.5,
    "🍊🍊🍊": 2.0,
    "🍋🍋🍋": 1.5,
    "🍒🍒🍒": 1.2,
}


# ======================== CONFIG HELPERS ========================

def get_gambling_config(guild_id: int) -> dict:
    """Retorna configuração de gambling do servidor via DB"""
    config = DEFAULT_CONFIG.copy()
    config.update(guild_repo.get_gambling_config(guild_id))
    return config


def save_gambling_config(guild_id: int, config: dict) -> None:
    """Salva configuração de gambling do servidor via DB"""
    guild_repo.set_gambling_config(
        guild_id,
        enabled=config.get('enabled', True),
        min_bet=config.get('min_bet', 50),
        max_bet=config.get('max_bet', 50000),
        daily_loss_limit=config.get('daily_loss_limit', 10000),
        house_edge=config.get('house_edge', 0.02),
    )


def get_daily_losses(guild_id: int, user_id: int) -> int:
    """Retorna quanto o usuário perdeu hoje"""
    user = user_repo.get_or_create_user(guild_id, user_id)
    last_reset = user.get('gambling_daily_reset')
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if last_reset != today:
        # Resetar perdas diárias
        user_repo.update_user(guild_id, user_id, gambling_daily_losses=0, gambling_daily_reset=today)
        return 0
    
    return user.get('gambling_daily_losses', 0)


def add_daily_loss(guild_id: int, user_id: int, amount: int) -> None:
    """Adiciona perda diária"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    user_repo.update_user(guild_id, user_id, gambling_daily_reset=today)
    user_repo.increment_user(guild_id, user_id, gambling_daily_losses=amount)


# ======================== HELPERS ========================

def validate_bet(guild_id: int, user_id: int, bet: int) -> tuple[bool, str]:
    """Valida uma aposta com controles de risco."""
    config = get_gambling_config(guild_id)
    
    if not config.get('enabled', True):
        return False, "apostas estão desativadas neste servidor"
    
    if bet <= 0:
        return False, "valor da aposta deve ser positivo"
    
    balance = get_mora(guild_id, user_id)
    min_bet = config.get('min_bet', 50)
    max_bet = config.get('max_bet', 50000)
    daily_limit = config.get('daily_loss_limit', 10000)
    
    if bet < min_bet:
        return False, f"aposta mínima é {mora_emoji()} **{format_number(min_bet)}**"
    if bet > max_bet:
        return False, f"aposta máxima é {mora_emoji()} **{format_number(max_bet)}**"
    if bet > balance:
        return False, f"você só tem {mora_emoji()} **{format_number(balance)}**"
    
    # Verificar limite diário de perdas
    daily_losses = get_daily_losses(guild_id, user_id)
    if daily_losses >= daily_limit:
        return False, f"você atingiu o limite diário de perdas ({mora_emoji()} {format_number(daily_limit)})\n\nvolta amanhã!"
    
    return True, ""


def record_gambling_result(guild_id: int, user_id: int, bet: int, won: bool, profit: int) -> None:
    """Registra resultado de aposta no banco"""
    if won:
        user_repo.increment_user(guild_id, user_id, gambling_wins=1, gambling_profit=profit)
    else:
        user_repo.increment_user(guild_id, user_id, gambling_losses=1, gambling_profit=-bet)
        add_daily_loss(guild_id, user_id, bet)
    
    # Emit event (fire-and-forget from sync context)
    event_bus.emit_nowait(BotEvent.GAMBLING_RESULT, guild_id, {
        'user_id': user_id,
        'bet': bet,
        'won': won,
        'profit': profit if won else -bet
    })


def apply_house_edge(win_chance: float, guild_id: int) -> float:
    """Aplica a vantagem da casa na chance de vitória"""
    config = get_gambling_config(guild_id)
    house_edge = config.get('house_edge', 0.02)
    return win_chance * (1 - house_edge)


def spin_slots(guild_id: int) -> tuple[list[str], float]:
    """Gira os slots. Retorna (símbolos, multiplicador)."""
    # Peso dos símbolos (mais raros = menor peso)
    weights = [30, 25, 20, 15, 5, 3, 2]
    
    symbols = random.choices(SLOT_SYMBOLS, weights=weights, k=3)
    result = "".join(symbols)
    
    # Verificar vitória
    multiplier = SLOT_PAYOUTS.get(result, 0)
    
    # Duas iguais = 0.4x (reduzido)
    if multiplier == 0 and symbols[0] == symbols[1]:
        multiplier = 0.4
    elif multiplier == 0 and symbols[1] == symbols[2]:
        multiplier = 0.4
    
    return symbols, multiplier


# ======================== UI COMPONENTS ========================

# Valores de aposta pré-definidos para botões
BET_AMOUNTS = [50, 100, 500, 1000, 5000]


class BetAmountModal(discord.ui.Modal):
    """Modal para digitar valor personalizado de aposta"""
    
    def __init__(self, game_type: str, choice: str = None):
        super().__init__(title="Valor da Aposta")
        self.game_type = game_type
        self.choice = choice
        
        self.amount_input = discord.ui.TextInput(
            label="Quanto você quer apostar?",
            placeholder="ex: 100, 500, 1000",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.amount_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
        except ValueError:
            return await interaction.response.send_message(
                "digite um número válido", ephemeral=True
            )
        
        # Validar aposta
        valid, msg = validate_bet(interaction.guild.id, interaction.user.id, amount)
        if not valid:
            return await interaction.response.send_message(msg, ephemeral=True)
        
        # Executar o jogo
        if self.game_type == "slots":
            await execute_slots(interaction, amount)
        elif self.game_type == "coinflip":
            await show_coinflip_choice(interaction, amount)
        elif self.game_type == "roulette":
            if self.choice:
                await execute_roulette(interaction, amount, self.choice)
            else:
                await show_roulette_choice(interaction, amount)


class BetSelectView(View):
    """View para selecionar valor da aposta"""
    
    def __init__(self, author_id: int, guild_id: int, game_type: str, choice: str = None):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.guild_id = guild_id
        self.game_type = game_type
        self.choice = choice  # Para roleta
        
        balance = get_mora(guild_id, author_id)
        config = get_gambling_config(guild_id)
        min_bet = config.get('min_bet', 50)
        
        # Adicionar botões de valor
        for amount in BET_AMOUNTS:
            if amount <= balance and amount >= min_bet:
                btn = discord.ui.Button(
                    label=format_number(amount),
                    style=discord.ButtonStyle.primary,
                    custom_id=f"bet_{amount}"
                )
                btn.callback = self.make_bet_callback(amount)
                self.add_item(btn)
        
        # Botão "Outro valor"
        custom_btn = discord.ui.Button(
            label="Outro",
            style=discord.ButtonStyle.secondary,
            emoji="✏️",
            custom_id="bet_custom"
        )
        custom_btn.callback = self.custom_amount
        self.add_item(custom_btn)
        
        # Botão cancelar
        cancel_btn = discord.ui.Button(
            label="Cancelar",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id="bet_cancel",
            row=1
        )
        cancel_btn.callback = self.cancel
        self.add_item(cancel_btn)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("não é sua vez", ephemeral=True)
            return False
        return True
    
    def make_bet_callback(self, amount: int):
        async def callback(interaction: discord.Interaction):
            # Validar aposta novamente
            valid, msg = validate_bet(self.guild_id, interaction.user.id, amount)
            if not valid:
                return await interaction.response.send_message(msg, ephemeral=True)
            
            if self.game_type == "slots":
                await execute_slots(interaction, amount)
            elif self.game_type == "coinflip":
                await show_coinflip_choice(interaction, amount)
            elif self.game_type == "roulette":
                if self.choice:
                    await execute_roulette(interaction, amount, self.choice)
                else:
                    await show_roulette_choice(interaction, amount)
            
            self.stop()
        return callback
    
    async def custom_amount(self, interaction: discord.Interaction):
        modal = BetAmountModal(self.game_type, self.choice)
        await interaction.response.send_modal(modal)
        self.stop()
    
    async def cancel(self, interaction: discord.Interaction):
        embed = discord.Embed(description="aposta cancelada", color=Colors.USER_ERROR)
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class CoinflipChoiceView(View):
    """View para escolher cara ou coroa"""
    
    def __init__(self, bet: int, author_id: int, guild_id: int):
        super().__init__(timeout=30)
        self.bet = bet
        self.author_id = author_id
        self.guild_id = guild_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("não é sua vez", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="Cara", style=discord.ButtonStyle.primary, emoji="👤")
    async def heads(self, interaction: discord.Interaction, button: Button):
        await execute_coinflip(interaction, self.bet, "cara", self.guild_id)
        self.stop()
    
    @discord.ui.button(label="Coroa", style=discord.ButtonStyle.primary, emoji="👑")
    async def tails(self, interaction: discord.Interaction, button: Button):
        await execute_coinflip(interaction, self.bet, "coroa", self.guild_id)
        self.stop()
    
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        # Devolver a mora (não foi removida ainda neste fluxo)
        embed = discord.Embed(description="aposta cancelada", color=Colors.USER_ERROR)
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class RouletteChoiceView(View):
    """View para escolher opção da roleta"""
    
    def __init__(self, bet: int, author_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.bet = bet
        self.author_id = author_id
        self.guild_id = guild_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("não é sua vez", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="Vermelho", style=discord.ButtonStyle.danger, row=0)
    async def red(self, interaction: discord.Interaction, button: Button):
        await execute_roulette(interaction, self.bet, "vermelho")
        self.stop()
    
    @discord.ui.button(label="Preto", style=discord.ButtonStyle.secondary, row=0)
    async def black(self, interaction: discord.Interaction, button: Button):
        await execute_roulette(interaction, self.bet, "preto")
        self.stop()
    
    @discord.ui.button(label="Verde (0)", style=discord.ButtonStyle.success, row=0)
    async def green(self, interaction: discord.Interaction, button: Button):
        await execute_roulette(interaction, self.bet, "verde")
        self.stop()
    
    @discord.ui.button(label="Par", style=discord.ButtonStyle.primary, row=1)
    async def even(self, interaction: discord.Interaction, button: Button):
        await execute_roulette(interaction, self.bet, "par")
        self.stop()
    
    @discord.ui.button(label="Ímpar", style=discord.ButtonStyle.primary, row=1)
    async def odd(self, interaction: discord.Interaction, button: Button):
        await execute_roulette(interaction, self.bet, "ímpar")
        self.stop()
    
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(description="aposta cancelada", color=Colors.USER_ERROR)
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


# ======================== GAME EXECUTION HELPERS ========================

async def show_coinflip_choice(interaction: discord.Interaction, bet: int):
    """Mostra botões de cara ou coroa"""
    embed = discord.Embed(
        title="🪙 Cara ou Coroa",
        description=f"apostando **{format_number(bet)}**\n\nescolha um lado:",
        color=Colors.PRIMARY
    )
    
    view = CoinflipChoiceView(bet, interaction.user.id, interaction.guild.id)
    await interaction.response.edit_message(embed=embed, view=view)


async def show_roulette_choice(interaction: discord.Interaction, bet: int):
    """Mostra botões de opções da roleta"""
    embed = discord.Embed(
        title="🎡 Roleta",
        description=f"apostando **{format_number(bet)}**\n\nescolha onde apostar:",
        color=Colors.PRIMARY
    )
    embed.add_field(
        name="Multiplicadores",
        value="**Cores:** 1.9x\n**Par/Ímpar:** 1.9x\n**Verde:** 30x",
        inline=False
    )
    
    view = RouletteChoiceView(bet, interaction.user.id, interaction.guild.id)
    await interaction.response.edit_message(embed=embed, view=view)


async def execute_slots(interaction: discord.Interaction, bet: int):
    """Executa o jogo de slots"""
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    
    # Remover aposta
    remove_mora(guild_id, user_id, bet)
    
    # Animação
    embed = discord.Embed(
        title="🎰 Slots",
        description="```\n❓ ❓ ❓\n```\ngirando...",
        color=Colors.PRIMARY
    )
    await interaction.response.edit_message(embed=embed, view=None)
    
    await asyncio.sleep(1.2)
    
    # Resultado
    symbols, multiplier = spin_slots(guild_id)
    result_display = " ".join(symbols)
    
    if multiplier > 0:
        winnings = int(bet * multiplier)
        add_mora(guild_id, user_id, winnings,
                 transaction_type='gambling_win',
                 description=f'Slots: {multiplier}x')
        profit = winnings - bet
        record_gambling_result(guild_id, user_id, bet, profit > 0, max(profit, 0))
        
        new_balance = get_mora(guild_id, user_id)
        
        if multiplier >= 4:
            title = "🎰 JACKPOT!"
        elif multiplier >= 2:
            title = "🎰 GRANDE VITÓRIA!"
        elif multiplier >= 1:
            title = "🎰 Vitória!"
        else:
            title = "🎰 Quase..."
        
        color = Colors.SUCCESS if profit > 0 else Colors.WARNING
        
        embed = discord.Embed(
            title=title,
            description=f"```\n{result_display}\n```\n"
                       f"**{multiplier}x** — ganhou **{format_number(winnings)}**",
            color=color
        )
        embed.add_field(name="Saldo", value=f"```{format_number(new_balance)}```", inline=True)
    else:
        record_gambling_result(guild_id, user_id, bet, False, 0)
        new_balance = get_mora(guild_id, user_id)
        
        embed = discord.Embed(
            title="🎰 Sem sorte...",
            description=f"```\n{result_display}\n```\n"
                       f"perdeu **{format_number(bet)}**",
            color=Colors.WARNING
        )
        embed.add_field(name="Saldo", value=f"```{format_number(new_balance)}```", inline=True)
    
    await interaction.message.edit(embed=embed)


async def execute_coinflip(interaction: discord.Interaction, bet: int, choice: str, guild_id: int):
    """Executa o coinflip"""
    user_id = interaction.user.id
    
    # Verificar saldo novamente
    balance = get_mora(guild_id, user_id)
    if balance < bet:
        embed = discord.Embed(description="mora insuficiente", color=Colors.USER_ERROR)
        return await interaction.response.edit_message(embed=embed, view=None)
    
    # Remover aposta
    remove_mora(guild_id, user_id, bet)
    
    # Animação
    embed = discord.Embed(description="🪙 girando...", color=Colors.PRIMARY)
    await interaction.response.edit_message(embed=embed, view=None)
    await asyncio.sleep(1.5)
    
    # Resultado (48% de chance por house edge)
    win_chance = apply_house_edge(0.50, guild_id)
    won = random.random() < win_chance
    
    result = choice if won else ("coroa" if choice == "cara" else "cara")
    emoji = "👤" if result == "cara" else "👑"
    
    if won:
        winnings = int(bet * 1.95)
        add_mora(guild_id, user_id, winnings,
                 transaction_type='gambling_win',
                 description=f'Coinflip: ganhou {winnings}')
        profit = winnings - bet
        record_gambling_result(guild_id, user_id, bet, True, profit)
        new_balance = get_mora(guild_id, user_id)
        
        embed = discord.Embed(
            title=f"{emoji} {result.upper()}!",
            description=f"ganhou **{format_number(winnings)}**",
            color=Colors.SUCCESS
        )
        embed.add_field(name="Saldo", value=f"```{format_number(new_balance)}```", inline=True)
    else:
        record_gambling_result(guild_id, user_id, bet, False, 0)
        new_balance = get_mora(guild_id, user_id)
        
        embed = discord.Embed(
            title=f"{emoji} {result.upper()}!",
            description=f"perdeu **{format_number(bet)}**",
            color=Colors.WARNING
        )
        embed.add_field(name="Saldo", value=f"```{format_number(new_balance)}```", inline=True)
    
    await interaction.message.edit(embed=embed)


async def execute_roulette(interaction: discord.Interaction, bet: int, choice: str):
    """Executa a roleta"""
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    
    # Verificar saldo novamente
    balance = get_mora(guild_id, user_id)
    if balance < bet:
        embed = discord.Embed(description="mora insuficiente", color=Colors.USER_ERROR)
        return await interaction.response.edit_message(embed=embed, view=None)
    
    # Remover aposta
    remove_mora(guild_id, user_id, bet)
    
    # Definir multiplicador
    RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}
    
    choice = choice.lower()
    if choice in ["vermelho", "preto"]:
        multiplier = 1.9
    elif choice == "verde":
        multiplier = 30
    elif choice in ["par", "ímpar", "impar"]:
        multiplier = 1.9
    else:
        multiplier = 1.9  # fallback
    
    # Animação
    embed = discord.Embed(title="🎡 Roleta", description="girando...", color=Colors.PRIMARY)
    await interaction.response.edit_message(embed=embed, view=None)
    await asyncio.sleep(2)
    
    # Resultado
    result = random.randint(0, 36)
    
    if result == 0:
        result_color = "🟢"
        result_type = "green"
    elif result in RED_NUMBERS:
        result_color = "🔴"
        result_type = "red"
    else:
        result_color = "⚫"
        result_type = "black"
    
    # Verificar vitória
    won = False
    if choice == "vermelho" and result_type == "red":
        won = True
    elif choice == "preto" and result_type == "black":
        won = True
    elif choice == "verde" and result == 0:
        won = True
    elif choice == "par" and result != 0 and result % 2 == 0:
        won = True
    elif choice in ["ímpar", "impar"] and result % 2 == 1:
        won = True
    
    if won:
        winnings = int(bet * multiplier)
        add_mora(guild_id, user_id, winnings,
                 transaction_type='gambling_win',
                 description=f'Roleta: {result} ({multiplier}x)')
        profit = winnings - bet
        record_gambling_result(guild_id, user_id, bet, True, profit)
        new_balance = get_mora(guild_id, user_id)
        
        embed = discord.Embed(
            title=f"🎡 {result_color} {result}",
            description=f"**{multiplier}x** — ganhou **{format_number(winnings)}**",
            color=Colors.SUCCESS
        )
        embed.add_field(name="Saldo", value=f"```{format_number(new_balance)}```", inline=True)
    else:
        record_gambling_result(guild_id, user_id, bet, False, 0)
        new_balance = get_mora(guild_id, user_id)
        
        embed = discord.Embed(
            title=f"🎡 {result_color} {result}",
            description=f"perdeu **{format_number(bet)}**",
            color=Colors.WARNING
        )
        embed.add_field(name="Saldo", value=f"```{format_number(new_balance)}```", inline=True)
    
    await interaction.message.edit(embed=embed)


# Legacy CoinflipView for old flow
class CoinflipView(View):
    """View para escolher cara ou coroa (legacy)"""
    
    def __init__(self, bet: int, author_id: int, guild_id: int):
        super().__init__(timeout=30)
        self.bet = bet
        self.author_id = author_id
        self.guild_id = guild_id
        self.choice = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ essa aposta não é sua", ephemeral=True
            )
            return False
        return True
    
    @discord.ui.button(label="Cara", style=discord.ButtonStyle.primary, emoji="👤")
    async def heads(self, interaction: discord.Interaction, button: Button):
        self.choice = "cara"
        await self.flip_coin(interaction)
    
    @discord.ui.button(label="Coroa", style=discord.ButtonStyle.primary, emoji="👑")
    async def tails(self, interaction: discord.Interaction, button: Button):
        self.choice = "coroa"
        await self.flip_coin(interaction)
    
    async def flip_coin(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        
        # Verificar saldo novamente
        balance = get_mora(self.guild_id, user_id)
        if balance < self.bet:
            embed = discord.Embed(
                description="❌ você não tem mora suficiente mais",
                color=Colors.USER_ERROR
            )
            return await interaction.response.edit_message(embed=embed, view=None)
        
        # Remover aposta (transação registrada após resultado)
        remove_mora(self.guild_id, user_id, self.bet)
        
        # Animação
        embed = discord.Embed(
            description="🪙 girando...",
            color=Colors.PRIMARY
        )
        await interaction.response.edit_message(embed=embed, view=None)
        await asyncio.sleep(1.5)
        
        # Resultado com house edge (48% de chance de ganhar)
        win_chance = apply_house_edge(0.50, self.guild_id)
        won = random.random() < win_chance
        
        # Se ganhou, o resultado é a escolha do usuário
        # Se perdeu, é o oposto
        result = self.choice if won else ("coroa" if self.choice == "cara" else "cara")
        
        if won:
            winnings = int(self.bet * 1.95)  # 1.95x ao invés de 2x
            add_mora(self.guild_id, user_id, winnings,
                     transaction_type='gambling_win',
                     description=f'Coinflip: ganhou {winnings}')
            profit = winnings - self.bet
            record_gambling_result(self.guild_id, user_id, self.bet, True, profit)
            
            new_balance = get_mora(self.guild_id, user_id)
            
            emoji = "👤" if result == "cara" else "👑"
            embed = discord.Embed(
                title=f"{emoji} {result.upper()}!",
                description=f"você ganhou {mora_emoji()} **{format_number(winnings)}**!",
                color=Colors.SUCCESS
            )
            embed.add_field(
                name="Novo Saldo",
                value=f"```{format_number(new_balance)}```",
                inline=True
            )
        else:
            record_gambling_result(self.guild_id, user_id, self.bet, False, 0)
            
            new_balance = get_mora(self.guild_id, user_id)
            
            emoji = "👤" if result == "cara" else "👑"
            embed = discord.Embed(
                title=f"{emoji} {result.upper()}!",
                description=f"você perdeu {mora_emoji()} **{format_number(self.bet)}**",
                color=Colors.WARNING
            )
            embed.add_field(
                name="Novo Saldo",
                value=f"```{format_number(new_balance)}```",
                inline=True
            )
        
        await interaction.message.edit(embed=embed, view=None)
        self.stop()


# ======================== COG ========================

class Gambling(commands.Cog):
    """Jogos de aposta com Mora"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def cog_check(self, ctx: commands.Context) -> bool:
        """Check if economy feature is enabled for this guild"""
        if ctx.guild and not guild_repo.is_feature_enabled(ctx.guild.id, "economy"):
            await ctx.send(embed=embed_disabled("economia"), ephemeral=True)
            return False
        return True
    
    # -------------------- SLOTS --------------------
    
    @commands.hybrid_command(
        name='slots',
        aliases=['slot', 'cacaniqueis'],
        description='Jogue no caça-níqueis'
    )
    @commands.cooldown(1, 8, commands.BucketType.user)  # 8s cooldown
    async def slots_command(self, ctx: commands.Context):
        """Joga no caça-níqueis - escolha o valor pelos botões"""
        config = get_gambling_config(ctx.guild.id)
        
        if not config.get('slots_enabled', True):
            embed = discord.Embed(
                description="slots está desativado neste servidor",
                color=Colors.INFO
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        balance = get_mora(ctx.guild.id, ctx.author.id)
        if balance < config.get('min_bet', 50):
            embed = discord.Embed(
                description=f"mora insuficiente\n\naposta mínima: **{format_number(config.get('min_bet', 50))}**",
                color=Colors.USER_ERROR
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        embed = discord.Embed(
            title="🎰 Slots",
            description=f"saldo: **{format_number(balance)}**\n\nescolha quanto apostar:",
            color=Colors.PRIMARY
        )
        embed.add_field(
            name="",
            value="**Prêmios**\n"
                  "3 iguais = 2x a 5x\n"
                  "2 iguais = 0.5x a 0.8x",
            inline=False
        )
        
        view = BetSelectView(ctx.author.id, ctx.guild.id, "slots")
        await ctx.reply(embed=embed, view=view, mention_author=False)
    
    # -------------------- MOEDA --------------------
    
    @commands.hybrid_command(
        name='moeda',
        aliases=['coinflip', 'cf', 'flip'],
        description='Aposte cara ou coroa'
    )
    @commands.cooldown(1, 6, commands.BucketType.user)  # 6s cooldown
    async def moeda_command(self, ctx: commands.Context):
        """Aposta em cara ou coroa - escolha o valor pelos botões"""
        config = get_gambling_config(ctx.guild.id)
        
        if not config.get('coinflip_enabled', True):
            embed = discord.Embed(
                description="coinflip está desativado neste servidor",
                color=Colors.INFO
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        balance = get_mora(ctx.guild.id, ctx.author.id)
        if balance < config.get('min_bet', 50):
            embed = discord.Embed(
                description=f"mora insuficiente\n\naposta mínima: **{format_number(config.get('min_bet', 50))}**",
                color=Colors.USER_ERROR
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        embed = discord.Embed(
            title="🪙 Cara ou Coroa",
            description=f"saldo: **{format_number(balance)}**\n\nescolha quanto apostar:",
            color=Colors.PRIMARY
        )
        embed.add_field(
            name="",
            value="**Prêmio:** 1.95x",
            inline=False
        )
        
        view = BetSelectView(ctx.author.id, ctx.guild.id, "coinflip")
        await ctx.reply(embed=embed, view=view, mention_author=False)
    
    # -------------------- ROLETA --------------------
    
    @commands.hybrid_command(
        name='roleta',
        aliases=['roulette', 'spin'],
        description='Gire a roleta!'
    )
    @commands.cooldown(1, 10, commands.BucketType.user)  # 10s cooldown
    async def roulette_command(self, ctx: commands.Context):
        """Roleta de casino - escolha o valor pelos botões"""
        config = get_gambling_config(ctx.guild.id)
        
        if not config.get('roulette_enabled', True):
            embed = discord.Embed(
                description="roleta está desativada neste servidor",
                color=Colors.INFO
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        balance = get_mora(ctx.guild.id, ctx.author.id)
        if balance < config.get('min_bet', 50):
            embed = discord.Embed(
                description=f"mora insuficiente\n\naposta mínima: **{format_number(config.get('min_bet', 50))}**",
                color=Colors.USER_ERROR
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        embed = discord.Embed(
            title="🎡 Roleta",
            description=f"saldo: **{format_number(balance)}**\n\nescolha quanto apostar:",
            color=Colors.PRIMARY
        )
        embed.add_field(
            name="",
            value="**Cores:** 1.9x\n**Par/Ímpar:** 1.9x\n**Verde (0):** 30x",
            inline=False
        )
        
        view = BetSelectView(ctx.author.id, ctx.guild.id, "roulette")
        await ctx.reply(embed=embed, view=view, mention_author=False)
    
    # -------------------- ESTATÍSTICAS --------------------
    
    @commands.hybrid_command(
        name='gambling',
        aliases=['apostas', 'gamblestats'],
        description='Mostra suas estatísticas de apostas'
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def gambling_stats_command(self, ctx: commands.Context, membro: Optional[discord.Member] = None):
        """Estatísticas de apostas"""
        target = membro or ctx.author
        user = user_repo.get_or_create_user(ctx.guild.id, target.id)
        
        wins = user.get('gambling_wins', 0)
        losses = user.get('gambling_losses', 0)
        profit = user.get('gambling_profit', 0)
        total_games = wins + losses
        daily_losses = get_daily_losses(ctx.guild.id, target.id)
        
        config = get_gambling_config(ctx.guild.id)
        daily_limit = config.get('daily_loss_limit', 10000)
        
        win_rate = (wins / total_games * 100) if total_games > 0 else 0
        
        profit_text = f"+{format_number(profit)}" if profit >= 0 else format_number(profit)
        
        embed = discord.Embed(
            title="🎰 Apostas",
            color=Colors.SUCCESS if profit >= 0 else Colors.WARNING
        )
        
        embed.set_author(
            name=target.display_name,
            icon_url=target.display_avatar.url
        )
        
        embed.add_field(
            name="Vitórias",
            value=f"```{format_number(wins)}```",
            inline=True
        )
        embed.add_field(
            name="Derrotas",
            value=f"```{format_number(losses)}```",
            inline=True
        )
        embed.add_field(
            name="Win Rate",
            value=f"```{win_rate:.1f}%```",
            inline=True
        )
        embed.add_field(
            name="Balanço",
            value=f"```{profit_text}```",
            inline=True
        )
        embed.add_field(
            name="Limite Diário",
            value=f"```{format_number(daily_losses)}/{format_number(daily_limit)}```",
            inline=True
        )
        
        await ctx.reply(embed=embed, mention_author=False)
    
    # -------------------- CONFIG (ADMIN) --------------------
    
    @commands.hybrid_group(
        name='gamblingconfig',
        aliases=['gcfg'],
        description='Configuração de apostas do servidor'
    )
    @commands.has_permissions(administrator=True)
    async def gambling_config(self, ctx: commands.Context):
        """Configuração de apostas (admin)"""
        if ctx.invoked_subcommand is None:
            config = get_gambling_config(ctx.guild.id)
            
            status = "Ativado" if config.get('enabled') else "Desativado"
            
            games = []
            if config.get('slots_enabled', True):
                games.append("Slots")
            if config.get('coinflip_enabled', True):
                games.append("Moeda")
            if config.get('roulette_enabled', True):
                games.append("Roleta")
            
            embed = discord.Embed(
                title="⚙️ Config Apostas",
                color=Colors.PRIMARY
            )
            
            embed.add_field(
                name="Sistema",
                value=f"```{status}```",
                inline=True
            )
            embed.add_field(
                name="Aposta Mín/Máx",
                value=f"```{format_number(config.get('min_bet', 50))}/{format_number(config.get('max_bet', 50000))}```",
                inline=True
            )
            embed.add_field(
                name="Limite Diário",
                value=f"```{format_number(config.get('daily_loss_limit', 10000))}```",
                inline=True
            )
            embed.add_field(
                name="Jogos",
                value=f"```{', '.join(games) if games else 'Nenhum'}```",
                inline=False
            )
            
            embed.set_footer(text="/gamblingconfig <toggle|limite|aposta|jogo>")
            
            await ctx.reply(embed=embed, mention_author=False)
    
    @gambling_config.command(name='toggle', description='Ativa/desativa sistema de apostas')
    @commands.has_permissions(administrator=True)
    async def gambling_toggle(self, ctx: commands.Context):
        """Ativa/desativa apostas"""
        config = get_gambling_config(ctx.guild.id)
        config['enabled'] = not config.get('enabled', True)
        save_gambling_config(ctx.guild.id, config)
        
        status = "✅ ativado" if config['enabled'] else "❌ desativado"
        embed = discord.Embed(
            description=f"sistema de apostas {status}",
            color=Colors.SUCCESS
        )
        await ctx.reply(embed=embed, mention_author=False)
    
    @gambling_config.command(name='limite', description='Define limite diário de perdas')
    @commands.has_permissions(administrator=True)
    @app_commands.describe(valor="Limite máximo de perda diária")
    async def gambling_limit(self, ctx: commands.Context, valor: int):
        """Define limite diário"""
        if valor < 100:
            embed = discord.Embed(description="❌ limite mínimo é 100", color=Colors.USER_ERROR)
            return await ctx.reply(embed=embed, mention_author=False)
        
        config = get_gambling_config(ctx.guild.id)
        config['daily_loss_limit'] = valor
        save_gambling_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            description=f"✅ limite diário definido para {mora_emoji()} **{format_number(valor)}**",
            color=Colors.SUCCESS
        )
        await ctx.reply(embed=embed, mention_author=False)
    
    @gambling_config.command(name='aposta', description='Define limites de aposta')
    @commands.has_permissions(administrator=True)
    @app_commands.describe(minimo="Aposta mínima", maximo="Aposta máxima")
    async def gambling_bet_limits(self, ctx: commands.Context, minimo: int, maximo: int):
        """Define limites de aposta"""
        if minimo < 10:
            embed = discord.Embed(description="❌ mínimo não pode ser menor que 10", color=Colors.USER_ERROR)
            return await ctx.reply(embed=embed, mention_author=False)
        if maximo < minimo:
            embed = discord.Embed(description="❌ máximo não pode ser menor que mínimo", color=Colors.USER_ERROR)
            return await ctx.reply(embed=embed, mention_author=False)
        
        config = get_gambling_config(ctx.guild.id)
        config['min_bet'] = minimo
        config['max_bet'] = maximo
        save_gambling_config(ctx.guild.id, config)
        
        embed = discord.Embed(
            description=f"✅ limites definidos: {mora_emoji()} **{format_number(minimo)}** - **{format_number(maximo)}**",
            color=Colors.SUCCESS
        )
        await ctx.reply(embed=embed, mention_author=False)
    
    @gambling_config.command(name='jogo', description='Ativa/desativa um jogo específico')
    @commands.has_permissions(administrator=True)
    @app_commands.describe(jogo="Nome do jogo: slots, coinflip, roleta")
    async def gambling_game_toggle(self, ctx: commands.Context, jogo: str):
        """Ativa/desativa um jogo"""
        jogo = jogo.lower()
        game_keys = {
            'slots': 'slots_enabled',
            'slot': 'slots_enabled',
            'coinflip': 'coinflip_enabled',
            'cf': 'coinflip_enabled',
            'moeda': 'coinflip_enabled',
            'roleta': 'roulette_enabled',
            'roulette': 'roulette_enabled',
        }
        
        if jogo not in game_keys:
            embed = discord.Embed(
                description="❌ jogo inválido\n\nuse: `slots`, `coinflip`, `roleta`",
                color=Colors.USER_ERROR
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        config = get_gambling_config(ctx.guild.id)
        key = game_keys[jogo]
        config[key] = not config.get(key, True)
        save_gambling_config(ctx.guild.id, config)
        
        status = "✅ ativado" if config[key] else "❌ desativado"
        embed = discord.Embed(
            description=f"**{jogo}** {status}",
            color=Colors.SUCCESS
        )
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Gambling(bot))
