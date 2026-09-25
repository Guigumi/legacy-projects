"""
PvP Battle System
Epic battles between users with random items
"""
import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, Optional, Tuple, List, Union

import discord
from discord.ext import commands
from discord.ui import Button, View

import config
from config import Colors

logger = logging.getLogger(__name__)

INITIAL_HEALTH = 1000
TURN_TIME = 30  # seconds
MAX_TURNS = 30  # Maximum turn limit

# Battle colors
BATTLE_COLORS = {
    "fight": 0xE74C3C,      # Red - Active battle
    "victory": 0x2ECC71,    # Green - Victory
    "defeat": 0x95A5A6,     # Gray - Defeat
    "waiting": 0xF39C12,    # Yellow - Waiting
    "info": 0x3498DB,       # Blue - Information
}

# ATTACK items (damage balanced for 1000 HP)
ATTACK_ITEMS = {
    # normal
    "👤 Adm": (444, 444),
    "🎹 Teclado": (80, 120),
    "🪑 Cadeira Gamer": (100, 150),
    "🧱 Tijolo": (120, 160),
    "🔫 Glock-18": (150, 200),
    "💣 Bomba": (200, 300),
    
    # games
    "🐦‍⬛ Pássaro com adagas": (120, 200),
    "⚔️ Artes do Ferrão": (120, 180),
    "💨 Dash": (90, 140),
    "🦴 Gaster Blaster": (140, 280),
    "🔪 Faca Real": (200, 340),
    "🗡️ Zenith": (200, 340),
    "🌙 Lâmina da Noite": (200, 340),
    "⚔️ Lâminas do Caos": (220, 360),
    "🎮 Mega Buster": (180, 300),
    "🪄 Gravity Gun": (160, 280),
    "🐢 Casco Vermelho": (130, 220),
    "🎱 Master Ball": (250, 400),
    "🪨 Terraprisma": (200, 350),
    "🔫 Scar Lendária": (300, 450),
    "🎯 Backstab": (250, 400),
    "🗡️ Espada de Netherite": (150, 200),
}

# DEFENSE items (defense balanced for 1000 HP)
DEFENSE_ITEMS = {
    # normal
    "🛡️ Escudo de madeira": (80, 140),
    "🛡️ Escudo de ferro": (140, 240),
    "🛡️ Escudo de diamante": (240, 300),
    "🗽 Estatua da Liberdade": (100, 150),


    # games 
    "💎 Coração de cristal": (100, 180),
    "❤️ Determinação": (200, 300),
    "🐚 Carapaça Baldur": (100, 180),
    "💙 Coração Frágil": (100, 150),
    "🐢 Carapaça Robusta": (70, 150),
    "🔵 Escudo de Sonho": (70, 140),
    "🖤 Máscara Fraturada": (130, 200),
    "🐢 Armadura de Tartaruga": (120, 200),
    "👼 Armadura consagrada": (100, 180),
    "💔 Coração de cristal": (140, 190),
    "🛡️ Ankh Shield": (130, 180),
}

# MIXED items (can be very good or very weak - balanced for 1000 HP)
# Rebalanced: higher damage potential, lower chance of bad outcome
MIXED_ITEMS = {
    # normal - (damage, defense)
    "🎲 Dado de RPG": [(400, 50), (200, 0), (300, 100)],
    "🎰 Slot Machine": [(350, 80), (150, 50), (280, 120)],
    "🃏 Coringa": [(450, 0), (180, 100), (100, 150)],

    # games
    "⚫ Void Heart": [(500, 0), (200, 150), (350, 50)],
    "💔 Bad Time": [(600, -50), (250, 100), (150, 200)],
    "🎵 Mettaton": [(300, 150), (200, 200), (250, 100)],
    "🪦 Reaper Leviatan": [(550, 0), (220, 120), (380, 50)],
    "🎵 Ocarina of Time": [(400, 150), (200, 180), (300, 120)],
    "👥 Mahoraga": [(500, 100), (250, 150), (350, 80)],
}

# PARRY items (block 100% damage - 1x per battle)
PARRY_ITEMS = {
    "⚡ Parry": "Defendeu no timing perfeito!",
    "🌀 Dodge": "Esquivou no momento certo!",
    "🪦 Totem of Undying": "Sobreviveu a morte!",
    "🪁 Glider padrão": "Caiu com segurança!",
    "⏳ Adiamento": "Adiou o ataque inimigo!",
    "🛡️ Shield of Cthulhu": "Isso pode?"
}

# ======================== BATTLE SYSTEM ========================

def create_hp_bar(current: int, max_hp: int, length: int = 6) -> str:
    """Creates visual HP bar"""
    if current <= 0:
        return "💀 `0`"
    
    percent = current / max_hp
    filled = max(1, int(percent * length))  # Minimum 1 while alive
    empty = length - filled
    
    if percent > 0.5:
        bar_char = "🟩"
    elif percent > 0.25:
        bar_char = "🟨"
    else:
        bar_char = "🟥"
    
    return f"{bar_char * filled}{'⬜' * empty} `{current}`"


class BattlePlayer:
    """Represents a player in battle"""
    
    def __init__(self, member: discord.Member):
        self.member = member
        self.health = INITIAL_HEALTH
        self.max_health = INITIAL_HEALTH
        self.active_defense = 0  # Temporary defense for the turn
        self.parry_active = False  # If parry is active
        self.mixed_uses = 0    # Mixed item usage counter
        self.parry_uses = 0    # Parry usage counter
        self.consecutive_attacks = 0
        self.consecutive_defenses = 0
    
    def attack(self) -> Tuple[str, int]:
        """Performs an attack with random item"""
        self.consecutive_defenses = 0
        self.consecutive_attacks += 1
        
        item_name = random.choice(list(ATTACK_ITEMS.keys()))
        damage_range = ATTACK_ITEMS[item_name]
        damage = random.randint(damage_range[0], damage_range[1])
        
        # Fatigue system (3+ consecutive attacks)
        if self.consecutive_attacks >= 3:
            damage = int(damage * 0.5)
            
        return item_name, damage
    
    def defend(self) -> Tuple[str, int]:
        """Defends with random item"""
        self.consecutive_attacks = 0
        self.consecutive_defenses += 1
        
        item_name = random.choice(list(DEFENSE_ITEMS.keys()))
        
        # Shield break system (3+ consecutive defenses)
        if self.consecutive_defenses >= 3:
            defense = -10  # Debuff: Takes more damage
        else:
            damage_range = DEFENSE_ITEMS[item_name]
            defense = random.randint(damage_range[0], damage_range[1])
            # Buff on first defense
            if self.consecutive_defenses == 1:
                defense += 5
            
        self.active_defense = defense
        return item_name, defense
    
    def use_parry(self) -> Tuple[str, str]:
        """Activates parry - completely blocks the next attack"""
        self.consecutive_attacks = 0
        self.consecutive_defenses = 0
        self.parry_uses += 1
        self.parry_active = True
        
        item_name = random.choice(list(PARRY_ITEMS.keys()))
        description = PARRY_ITEMS[item_name]
        return item_name, description
    
    def use_mixed(self) -> Tuple[str, int, int]:
        """Uses random mixed item"""
        self.mixed_uses += 1
        self.consecutive_attacks = 0
        self.consecutive_defenses = 0
        
        item_name = random.choice(list(MIXED_ITEMS.keys()))
        variant = random.choice(MIXED_ITEMS[item_name])
        
        damage, defense = variant[0], variant[1]
        self.active_defense = defense
        
        return item_name, damage, defense
    
    def receive_damage(self, damage: int) -> Tuple[int, bool]:
        """Receives damage considering active defense and parry. Returns (real_damage, was_parry)"""
        # Check parry first
        if self.parry_active:
            self.parry_active = False
            return 0, True
        
        real_damage = max(0, damage - self.active_defense)
        self.health = max(0, self.health - real_damage)
        return real_damage, False
    
    def reset_defense(self):
        """Resets active defense after the turn"""
        self.active_defense = 0
    
    def get_health_bar(self) -> str:
        """Returns visual health bar"""
        return create_hp_bar(self.health, self.max_health, 6)
    
    def is_alive(self) -> bool:
        """Checks if still alive"""
        return self.health > 0
    
    def can_parry(self) -> bool:
        """Checks if can use parry (1x per battle)"""
        return self.parry_uses < 1

class BattleView(View):
    """View with battle action buttons - Simultaneous System"""
    
    def __init__(self, battle: 'Battle'):
        super().__init__(timeout=TURN_TIME)
        self.battle = battle
        self.action_p1: Optional[str] = None
        self.action_p2: Optional[str] = None
    
    def _get_button_state(self, player: BattlePlayer, custom_id: str) -> Optional[Tuple[bool, str, discord.ButtonStyle]]:
        """Returns (disabled, label, style) for a button based on player, or None if no change needed"""
        if custom_id == "misto" and player.mixed_uses >= 1:
            return (True, "🎲 Usado", discord.ButtonStyle.secondary)
        if custom_id == "parry" and player.parry_uses >= 1:
            return (True, "⚡ Usado", discord.ButtonStyle.secondary)
        return None

    @discord.ui.button(label="⚔️ Atacar", style=discord.ButtonStyle.danger, custom_id="atacar", row=0)
    async def attack_button(self, interaction: discord.Interaction, button: Button):
        await self._process_action(interaction, "atacar")
    
    @discord.ui.button(label="🛡️ Defender", style=discord.ButtonStyle.primary, custom_id="defender", row=0)
    async def defend_button(self, interaction: discord.Interaction, button: Button):
        await self._process_action(interaction, "defender")
    
    @discord.ui.button(label="🎲 Trunfo", style=discord.ButtonStyle.success, custom_id="misto", row=0)
    async def mixed_button(self, interaction: discord.Interaction, button: Button):
        await self._process_action(interaction, "misto")
    
    @discord.ui.button(label="⚡ Parry", style=discord.ButtonStyle.secondary, custom_id="parry", row=1)
    async def parry_button(self, interaction: discord.Interaction, button: Button):
        await self._process_action(interaction, "parry")
    
    @discord.ui.button(label="🏳️ Desistir", style=discord.ButtonStyle.secondary, custom_id="desistir", row=1)
    async def surrender_button(self, interaction: discord.Interaction, button: Button):
        # Check if is one of the players
        if interaction.user.id == self.battle.player1.member.id:
            self.action_p1 = "desistir"
            await interaction.response.defer()
        elif interaction.user.id == self.battle.player2.member.id:
            self.action_p2 = "desistir"
            await interaction.response.defer()
        else:
            return await interaction.response.send_message(f"{config.EMOJI_ERROR} Você não está nesta batalha!", ephemeral=True)
        
        # Check if both chose
        if self.action_p1 is not None and self.action_p2 is not None:
            self.stop()
    
    async def _process_action(self, interaction: discord.Interaction, action: str):
        """Processes the action chosen by the player"""
        user_id = interaction.user.id
        
        # Identify which player
        if user_id == self.battle.player1.member.id:
            player = self.battle.player1
            if self.action_p1 is not None:
                return await interaction.response.send_message(
                    f"{config.EMOJI_WARNING} Você já escolheu sua ação!",
                    ephemeral=True
                )
        elif user_id == self.battle.player2.member.id:
            player = self.battle.player2
            if self.action_p2 is not None:
                return await interaction.response.send_message(
                    f"{config.EMOJI_WARNING} Você já escolheu sua ação!",
                    ephemeral=True
                )
        else:
            return await interaction.response.send_message(
                f"{config.EMOJI_ERROR} Você não está nesta batalha!",
                ephemeral=True
            )
        
        # Check restrictions
        if action == "misto" and player.mixed_uses >= 1:
            return await interaction.response.send_message("❌ Você já usou seu Trunfo!", ephemeral=True)
        if action == "parry" and player.parry_uses >= 1:
            return await interaction.response.send_message("❌ Você já usou seu Parry!", ephemeral=True)
        
        # Register action
        if user_id == self.battle.player1.member.id:
            self.action_p1 = action
        else:
            self.action_p2 = action
        
        # Only defer, no message
        await interaction.response.defer()
        
        # Check if both chose
        if self.action_p1 is not None and self.action_p2 is not None:
            self.stop()
    
    async def on_timeout(self):
        """When time runs out without choice"""
        if self.action_p1 is None:
            self.action_p1 = random.choice(["atacar", "defender"])
        if self.action_p2 is None:
            self.action_p2 = random.choice(["atacar", "defender"])


class Battle:
    """Manages battle logic - Simultaneous System"""
    
    def __init__(self, player1: discord.Member, player2: discord.Member, channel: discord.TextChannel):
        self.player1 = BattlePlayer(player1)
        self.player2 = BattlePlayer(player2)
        self.channel = channel
        self.turn_number = 1
        self.message: Optional[discord.Message] = None
        self.finished = False
        self.winner: Optional[BattlePlayer] = None
        self.history: List[str] = []
        self._message_valid = True
    
    def create_waiting_embed(self) -> discord.Embed:
        """Creates embed while waiting for player choices"""
        embed = discord.Embed(
            title=f"⚔️ Battle T{self.turn_number}",
            color=BATTLE_COLORS["waiting"]
        )
        
        # Player 1
        p1_icons = ""
        if self.player1.mixed_uses < 1:
            p1_icons += "🎲"
        if self.player1.can_parry():
            p1_icons += "⚡"
        
        embed.add_field(
            name=f"▸ {self.player1.member.display_name[:15]}",
            value=f"{self.player1.get_health_bar()}\n{p1_icons}",
            inline=True
        )
        
        embed.add_field(name="​", value="⚔️", inline=True)
        
        # Player 2
        p2_icons = ""
        if self.player2.mixed_uses < 1:
            p2_icons += "🎲"
        if self.player2.can_parry():
            p2_icons += "⚡"
        
        embed.add_field(
            name=f"▸ {self.player2.member.display_name[:15]}",
            value=f"{self.player2.get_health_bar()}\n{p2_icons}",
            inline=True
        )
        
        embed.set_footer(text=f"{TURN_TIME}s para escolher")
        return embed
    
    def create_result_embed(self, result_text: str) -> discord.Embed:
        """Creates embed with turn result"""
        embed = discord.Embed(
            title=f"⚔️ Battle T{self.turn_number}",
            description=result_text[:500],
            color=BATTLE_COLORS["fight"]
        )
        
        # Player 1
        p1_icons = ""
        if self.player1.mixed_uses < 1:
            p1_icons += "🎲"
        if self.player1.parry_active:
            p1_icons += "⚡"
        
        embed.add_field(
            name=f"▸ {self.player1.member.display_name[:15]}",
            value=f"{self.player1.get_health_bar()}\n{p1_icons}",
            inline=True
        )
        
        embed.add_field(name="​", value="⚔️", inline=True)
        
        # Player 2
        p2_icons = ""
        if self.player2.mixed_uses < 1:
            p2_icons += "🎲"
        if self.player2.parry_active:
            p2_icons += "⚡"
        
        embed.add_field(
            name=f"▸ {self.player2.member.display_name[:15]}",
            value=f"{self.player2.get_health_bar()}\n{p2_icons}",
            inline=True
        )
        
        return embed
    
    def execute_action(self, player: BattlePlayer, opponent: BattlePlayer, action: str) -> Tuple[str, int, int]:
        """Executes action and returns (result_text, damage_dealt, defense_gained)"""
        if action == "atacar":
            item, damage = player.attack()
            return (item, damage, 0)
        elif action == "defender":
            item, defense = player.defend()
            return (item, 0, defense)
        elif action == "parry":
            item_name, description = player.use_parry()
            return (f"{item_name} - {description}", 0, 999)  # 999 = parry
        elif action == "misto":
            item, damage, defense = player.use_mixed()
            return (item, damage, defense)
        return ("❓", 0, 0)
    
    def process_simultaneous_turn(self, action1: str, action2: str) -> str:
        """Processes both players' actions simultaneously"""
        # Execute actions
        item1, damage1, def1 = self.execute_action(self.player1, self.player2, action1)
        item2, damage2, def2 = self.execute_action(self.player2, self.player1, action2)
        
        lines = []
        p1_name = self.player1.member.display_name[:12]
        p2_name = self.player2.member.display_name[:12]
        
        # P1 attacks/acts
        if damage1 > 0:
            real_damage, was_parry = self.player2.receive_damage(damage1)
            if was_parry:
                lines.append(f"{p1_name} ➜ {item1} ➜ ⚡ PARRY!")
            elif real_damage < damage1:
                blocked = damage1 - real_damage
                lines.append(f"{p1_name} ➜ {item1} ➜ -{real_damage} HP (🛡️ {blocked})")
            else:
                lines.append(f"{p1_name} ➜ {item1} ➜ -{real_damage} HP")
        elif action1 == "defender":
            if def1 < 0:
                lines.append(f"{p1_name} ➜ {item1} ➜ 💔 Vulnerável")
            else:
                lines.append(f"{p1_name} ➜ {item1} ➜ +{def1} 🛡️")
        elif action1 == "parry":
            lines.append(f"{p1_name} ➜ ⚡ Parry pronto")
        elif action1 == "misto" and def1 > 0 and def1 != 999:
            lines.append(f"{p1_name} ➜ {item1} ➜ +{def1} 🛡️")
        
        # P2 attacks/acts
        if damage2 > 0:
            real_damage, was_parry = self.player1.receive_damage(damage2)
            if was_parry:
                lines.append(f"{p2_name} ➜ {item2} ➜ ⚡ PARRY!")
            elif real_damage < damage2:
                blocked = damage2 - real_damage
                lines.append(f"{p2_name} ➜ {item2} ➜ -{real_damage} HP (🛡️ {blocked})")
            else:
                lines.append(f"{p2_name} ➜ {item2} ➜ -{real_damage} HP")
        elif action2 == "defender":
            if def2 < 0:
                lines.append(f"{p2_name} ➜ {item2} ➜ 💔 Vulnerável")
            else:
                lines.append(f"{p2_name} ➜ {item2} ➜ +{def2} 🛡️")
        elif action2 == "parry":
            lines.append(f"{p2_name} ➜ ⚡ Parry pronto")
        elif action2 == "misto" and def2 > 0 and def2 != 999:
            lines.append(f"{p2_name} ➜ {item2} ➜ +{def2} 🛡️")
        
        # Reset defenses for next turn
        self.player1.reset_defense()
        self.player2.reset_defense()
        
        return "\n".join(lines) if lines else "Nada aconteceu..."
    
    async def start(self):
        """Starts the battle with simultaneous system"""
        try:
            # Send initial message
            embed = self.create_waiting_embed()
            view = BattleView(self)
            self.message = await self.channel.send(
                content=f"⚔️ {self.player1.member.mention} vs {self.player2.member.mention} - Escolham suas ações!",
                embed=embed,
                view=view
            )
            
        except Exception as e:
            logger.error(f"Error sending initial message: {e}")
            self.finished = True
            return
        
        while not self.finished and self.turn_number <= MAX_TURNS:
            try:
                # Wait for both players to choose
                await view.wait()
                
                # Check for surrender
                if view.action_p1 == "desistir":
                    self.winner = self.player2
                    self.finished = True
                    break
                if view.action_p2 == "desistir":
                    self.winner = self.player1
                    self.finished = True
                    break
                
                # Process actions
                action1 = view.action_p1 or "atacar"
                action2 = view.action_p2 or "atacar"
                
                result = self.process_simultaneous_turn(action1, action2)
                self.history.append(result)
                
                # Check for game end
                if not self.player1.is_alive():
                    self.winner = self.player2
                    self.finished = True
                elif not self.player2.is_alive():
                    self.winner = self.player1
                    self.finished = True
                
                if self.finished:
                    await self.finalize(result)
                    break
                
                # Show turn result
                embed = self.create_result_embed(result)
                await self.message.edit(content=None, embed=embed, view=None)
                
                # Longer pause to read the result (3 seconds)
                await asyncio.sleep(3)
                
                # Next turn
                self.turn_number += 1
                
                # Create new view for next turn
                view = BattleView(self)
                embed = self.create_waiting_embed()
                await self.message.edit(
                    content=f"⚔️ {self.player1.member.mention} vs {self.player2.member.mention} - Escolham suas ações!",
                    embed=embed,
                    view=view
                )
                
            except Exception as e:
                logger.error(f"Error in battle loop: {e}")
                self.finished = True
                break
        
        # If turn limit reached
        if self.turn_number > MAX_TURNS and not self.finished:
            if self.player1.health > self.player2.health:
                self.winner = self.player1
            elif self.player2.health > self.player1.health:
                self.winner = self.player2
            await self.finalize(f"⏱️ Limite de {MAX_TURNS} turnos!")
    
    async def finalize(self, last_action: str = ""):
        """Finalizes the battle and shows winner"""
        if self.winner:
            loser = self.player2 if self.winner == self.player1 else self.player1
            
            embed = discord.Embed(
                title="🏆 Vitória!",
                color=BATTLE_COLORS["victory"]
            )
            embed.set_author(
                name=f"{self.winner.member.display_name} venceu!",
                icon_url=self.winner.member.display_avatar.url
            )
        else:
            embed = discord.Embed(
                title="🤝 Empate!",
                description="A batalha terminou sem vencedor",
                color=BATTLE_COLORS["info"]
            )
        
        # Final status
        p1_status = "👑" if self.winner == self.player1 else "💀"
        p2_status = "👑" if self.winner == self.player2 else "💀"
        
        embed.add_field(
            name=f"{p1_status} {self.player1.member.display_name[:15]}",
            value=f"{self.player1.health} HP",
            inline=True
        )
        embed.add_field(
            name=f"{p2_status} {self.player2.member.display_name[:15]}",
            value=f"{self.player2.health} HP",
            inline=True
        )
        
        embed.set_footer(text=f"{self.turn_number} turnos • GG!")
        
        # Remove buttons
        try:
            if self.message and self._message_valid:
                await self.message.edit(embed=embed, view=None)
        except discord.errors.NotFound:
            logger.debug("Battle message not found when finalizing")
            try:
                await self.channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Error sending final embed: {e}")
        except Exception as e:
            logger.error(f"Error finalizing battle: {e}")
            try:
                await self.channel.send(embed=embed)
            except:
                pass


# ======================== COG ========================

class BattleGame(commands.Cog):
    """⚔️ PvP Battle System"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_battles: Dict[int, Battle] = {}
    
    @commands.hybrid_command(
        name="batalha",
        aliases=["battle", "duel", "fight"],
        description="⚔️ Desafie alguém para uma batalha épica!"
    )
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def batalha(
        self,
        ctx: commands.Context,
        oponente: Optional[discord.Member] = None
    ):
        """
        Starts a PvP battle against another user
        
        Each player has 100 HP and can:
        - ⚔️ Attack: Deal damage with random items
        - 🛡️ Defend: Reduce damage on next turn
        - 🎲 Trump: Mixed item (can be OP or terrible)
        
        Example: /batalha @usuario
        """
        
        if not oponente:
            embed = discord.Embed(
                title="⚔️ Sistema de Batalha",
                description="Desafie alguém para uma batalha!",
                color=BATTLE_COLORS["info"]
            )
            embed.add_field(
                name="📖 Como usar",
                value="`/batalha @usuario`",
                inline=False
            )
            embed.add_field(
                name="⚔️ Ações",
                value=(
                    "**⚔️ Atacar** — Dano com itens aleatórios\n"
                    "**🛡️ Defender** — Reduz dano recebido\n"
                    "**🎲 Trunfo** — Item misto (1x por batalha)\n"
                    "**⚡ Parry** — Bloqueia 100% do dano (1x)"
                ),
                inline=False
            )
            embed.add_field(
                name="📋 Sistema",
                value="Ambos jogadores agem **simultaneamente**!",
                inline=False
            )
            embed.set_footer(text=f"{INITIAL_HEALTH} HP • {TURN_TIME}s por turno")
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Validations
        if oponente.id == ctx.author.id:
            embed = discord.Embed(title="❌ Erro", description="Você não pode batalhar sozinho", color=Colors.ERROR)
            return await ctx.send(embed=embed, ephemeral=True)
        
        if oponente.bot:
            embed = discord.Embed(title="❌ Erro", description="Bots não batalham", color=Colors.ERROR)
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Validar se é um canal de texto
        if not isinstance(ctx.channel, discord.TextChannel):
            embed = discord.Embed(title="❌ Erro", description="Batalhas só funcionam em canais de texto", color=Colors.ERROR)
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Check if there's already an active battle in the channel
        if ctx.channel.id in self.active_battles:
            embed = discord.Embed(title="⚠️ Ocupado", description="Já há uma batalha neste canal", color=Colors.WARNING)
            return await ctx.send(embed=embed, ephemeral=True)
        
        embed = discord.Embed(title="⚔️ Desafio", color=BATTLE_COLORS["waiting"])
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="▸ Desafiante", value=ctx.author.mention, inline=True)
        embed.add_field(name="▸ Oponente", value=oponente.mention, inline=True)
        embed.set_footer(text="60s para aceitar")
        
        # Acceptance view
        view = AcceptBattleView(ctx.author, oponente, self)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
    
    async def start_battle(self, player1: discord.Member, player2: discord.Member, channel: discord.TextChannel):
        """Starts a new battle"""
        try:
            battle = Battle(player1, player2, channel)
            self.active_battles[channel.id] = battle
            
            await battle.start()
            
            # Remove from active list
            if channel.id in self.active_battles:
                del self.active_battles[channel.id]
        except Exception as e:
            logger.error(f"Error during battle: {e}")
            embed = discord.Embed(
                title="❌ Erro na Batalha",
                description=f"Algo deu errado: {str(e)[:100]}",
                color=Colors.ERROR
            )
            await channel.send(embed=embed)
    
    @batalha.error
    async def batalha_error(self, ctx: commands.Context, error: Exception):
        """Handles command errors"""
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏳ Aguarde",
                description=f"Você pode desafiar novamente em **{error.retry_after:.1f}s**",
                color=Colors.WARNING
            )
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.NoPrivateMessage):
            embed = discord.Embed(
                title="❌ Erro",
                description="Batalhas só podem acontecer em servidores!",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
        else:
            logger.error(f"Error in batalha command: {error}")
            embed = discord.Embed(
                title="❌ Erro",
                description=f"Algo deu errado: {str(error)[:100]}",
                color=Colors.ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)


class AcceptBattleView(View):
    """View for accepting or declining a battle"""
    
    def __init__(self, challenger: Union[discord.Member, discord.User], opponent: discord.Member, cog: "BattleGame"):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.cog = cog
        self.message: Optional[discord.Message] = None
        self.accepted = False

    @discord.ui.button(label="✅ Aceitar Desafio", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.opponent.id:
            embed = discord.Embed(
                description=f"❌ Apenas **{self.opponent.display_name}** pode aceitar!",
                color=Colors.ERROR
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        self.accepted = True
        
        # Confirm acceptance
        embed = discord.Embed(
            description="⚔️ Desafio aceito! Preparando arena...",
            color=BATTLE_COLORS["fight"]
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Disable buttons
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True  # type: ignore
        
        # Update original message
        accept_embed = discord.Embed(
            title="⚔️ DESAFIO ACEITO!",
            description=f"**{self.opponent.mention}** aceitou o desafio de **{self.challenger.mention}**!",
            color=BATTLE_COLORS["fight"]
        )
        accept_embed.set_footer(text="A batalha começará em instantes...")
        if self.message:
            await self.message.edit(embed=accept_embed, view=None)
        
        # Short dramatic pause
        await asyncio.sleep(1)
        
        # Start battle (check if it's a valid TextChannel)
        if interaction.channel and isinstance(interaction.channel, discord.TextChannel):
            # Convert to Member if necessary
            if isinstance(self.challenger, discord.User) and interaction.guild:
                challenger_member = interaction.guild.get_member(self.challenger.id)
                if challenger_member:
                    await self.cog.start_battle(challenger_member, self.opponent, interaction.channel)
            elif isinstance(self.challenger, discord.Member):
                await self.cog.start_battle(self.challenger, self.opponent, interaction.channel)
        self.stop()
    
    @discord.ui.button(label="❌ Recusar", style=discord.ButtonStyle.danger)
    async def decline_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.opponent.id:
            embed = discord.Embed(
                description=f"❌ Apenas **{self.opponent.display_name}** pode recusar!",
                color=Colors.ERROR
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        embed = discord.Embed(
            title="🏳️ Desafio Recusado",
            description=f"{self.opponent.mention} recusou o desafio.",
            color=BATTLE_COLORS["defeat"]
        )
        embed.set_footer(text="talvez da próxima vez")
        
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()
    
    async def on_timeout(self):
        """When acceptance time expires"""
        if self.accepted:
            return
        
        if self.message:
            embed = discord.Embed(
                title="⏱️ Tempo Esgotado",
                description=f"{self.opponent.mention} não respondeu a tempo.",
                color=BATTLE_COLORS["defeat"]
            )
            embed.set_footer(text="tente desafiar novamente")
            
            try:
                await self.message.edit(embed=embed, view=None)
            except:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BattleGame(bot))
