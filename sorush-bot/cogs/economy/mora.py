"""
Sistema de Economia - Mora (Moeda)

Comandos básicos de economia: saldo, daily, transferir, ranking.
"""
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from typing import Optional
import random
import logging

from config import Colors
from services.repositories import user_repo, transaction_repo, guild_repo
from services.embed_helpers import embed_success, embed_error, embed_warning, embed_info, embed_disabled
from services.event_bus import event_bus, BotEvent

logger = logging.getLogger(__name__)


def format_number(number: int) -> str:
    """Formata número com separadores de milhar"""
    return f"{number:,}".replace(',', '.')


# ======================== CONSTANTES ========================

MORA_EMOJI = "🪙"

# Valores padrão (podem ser alterados por servidor)
DEFAULT_DAILY_BASE = 500
DEFAULT_DAILY_STREAK_BONUS = 50
DEFAULT_DAILY_MAX_STREAK_BONUS = 1000

TRANSFER_MIN = 10
TRANSFER_TAX = 0.0  # 0% de taxa (pode mudar depois)


# ======================== CONFIG WRAPPERS (guild_repo) ========================

def get_daily_config(guild_id: int) -> dict:
    """Retorna configuração do daily do servidor via DB"""
    return guild_repo.get_daily_config(guild_id)


def set_daily_config(guild_id: int, base: int = None, streak_bonus: int = None, max_streak_bonus: int = None) -> None:
    """Define configuração do daily do servidor via DB"""
    guild_repo.set_daily_config(guild_id, base=base, streak_bonus=streak_bonus, max_streak_bonus=max_streak_bonus)


# ======================== HELPERS ========================

def mora_emoji() -> str:
    """Retorna o emoji de mora"""
    return MORA_EMOJI


def get_mora(guild_id: int, user_id: int) -> int:
    """Retorna o saldo de mora do usuário"""
    user = user_repo.get_or_create_user(guild_id, user_id)
    return user.get('mora', 0)


def add_mora(guild_id: int, user_id: int, amount: int, transaction_type: str = None, description: str = None, related_user_id: int = None) -> int:
    """Adiciona mora ao usuário. Retorna novo saldo."""
    user_repo.get_or_create_user(guild_id, user_id)
    user_repo.increment_user(guild_id, user_id, mora=amount, mora_total_earned=amount)
    new_balance = get_mora(guild_id, user_id)
    
    # Registrar transação
    if transaction_type:
        transaction_repo.add_transaction(guild_id, user_id, transaction_type, amount, new_balance, description, related_user_id)
    
    return new_balance


def remove_mora(guild_id: int, user_id: int, amount: int, transaction_type: str = None, description: str = None, related_user_id: int = None) -> bool:
    """Remove mora do usuário. Retorna False se não tiver saldo."""
    current = get_mora(guild_id, user_id)
    if current < amount:
        return False
    
    user_repo.increment_user(guild_id, user_id, mora=-amount, mora_total_spent=amount)
    
    # Registrar transação
    if transaction_type:
        new_balance = get_mora(guild_id, user_id)
        transaction_repo.add_transaction(guild_id, user_id, transaction_type, -amount, new_balance, description, related_user_id)
    
    return True


def transfer_mora(guild_id: int, from_id: int, to_id: int, amount: int) -> tuple[bool, str]:
    """Transfere mora entre usuários. Retorna (sucesso, mensagem)."""
    if amount < TRANSFER_MIN:
        return False, f"valor mínimo é {mora_emoji()} **{TRANSFER_MIN}**"
    
    if amount <= 0:
        return False, "valor deve ser positivo"
    
    if from_id == to_id:
        return False, "você não pode transferir pra si mesmo"
    
    sender_balance = get_mora(guild_id, from_id)
    if sender_balance < amount:
        return False, f"você só tem {mora_emoji()} **{format_number(sender_balance)}**"
    
    # Aplicar taxa (se houver)
    tax = int(amount * TRANSFER_TAX)
    received = amount - tax
    
    # Executar transferência com registro de transação
    remove_mora(guild_id, from_id, amount, 
                transaction_type='transfer_out', 
                description=f'Transferência enviada',
                related_user_id=to_id)
    add_mora(guild_id, to_id, received,
             transaction_type='transfer_in',
             description=f'Transferência recebida',
             related_user_id=from_id)
    
    return True, f"transferido {mora_emoji()} **{format_number(received)}**"


# ======================== UI COMPONENTS - BANCO ========================

TRANSACTION_EMOJIS = {
    'daily': '📅',
    'transfer_in': '📥',
    'transfer_out': '📤',
    'shop': '🛒',
    'gambling_win': '🎰',
    'gambling_lose': '🎲',
    'reward': '🎁',
    'admin': '⚙️',
    'other': '💫'
}

def get_transaction_emoji(tx_type: str) -> str:
    """Retorna emoji para tipo de transação"""
    return TRANSACTION_EMOJIS.get(tx_type, '💫')


def format_transaction_amount(amount: int) -> str:
    """Formata valor da transação com cor"""
    if amount > 0:
        return f"+{format_number(amount)}"
    return f"{format_number(amount)}"


class BancoView(discord.ui.View):
    """View interativa para o comando banco"""
    
    def __init__(self, guild: discord.Guild, user: discord.Member, viewer_id: int):
        super().__init__(timeout=180)
        self.guild = guild
        self.user = user
        self.viewer_id = viewer_id
        self.message: Optional[discord.Message] = None
        self.page = 0
        self.filter_type: Optional[str] = None
        self.transactions_per_page = 5
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer_id:
            await interaction.response.send_message(
                "❌ apenas quem usou o comando pode interagir", 
                ephemeral=True
            )
            return False
        return True
    
    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
    
    def get_embed(self) -> discord.Embed:
        """Gera o embed do banco"""
        user_data = user_repo.get_or_create_user(self.guild.id, self.user.id)
        mora_amount = user_data.get('mora', 0)
        total_earned = user_data.get('mora_total_earned', 0)
        total_spent = user_data.get('mora_total_spent', 0)
        
        # Ranking
        rank = user_repo.get_user_rank(self.guild.id, self.user.id, 'mora')
        rank_text = f"#{rank}" if rank else "-"
        
        # Estatísticas dos últimos 7 dias
        stats = transaction_repo.get_transaction_stats(self.guild.id, self.user.id, 7)
        
        # Lucro/prejuízo
        net = total_earned - total_spent
        net_text = f"+{format_number(net)}" if net >= 0 else format_number(net)
        
        embed = discord.Embed(
            title="",
            description=" ",
            color=Colors.XP
        )
        
        embed.set_author(
            name=self.user.display_name,
            icon_url=self.user.display_avatar.url
        )
        
        embed.add_field(name="─────〔 Banco 〕─────", value="", inline=False)
        
        # Linha 1: Saldo, Ranking, Balanço
        embed.add_field(
            name="Saldo",
            value=f"```{format_number(mora_amount)}```",
            inline=True
        )
        embed.add_field(
            name="Ranking",
            value=f"```{rank_text}```",
            inline=True
        )
        embed.add_field(
            name="Balanço",
            value=f"```{net_text}```",
            inline=True
        )
        
        # Últimos 7 dias (compacto)
        week_earned = stats['total_earned']
        week_spent = stats['total_spent']
        week_net = week_earned - week_spent
        week_text = f"+{format_number(week_net)}" if week_net >= 0 else format_number(week_net)
        
        embed.add_field(
            name="Últimos 7 dias",
            value=f"`{week_text}` • Ganho: `{format_number(week_earned)}` • Gasto: `{format_number(week_spent)}`",
            inline=False
        )
        
        # Histórico de transações
        transactions = transaction_repo.get_transactions(
            self.guild.id,
            self.user.id,
            limit=50,
            transaction_type=self.filter_type
        )
        
        if transactions:
            start = self.page * self.transactions_per_page
            end = start + self.transactions_per_page
            page_transactions = transactions[start:end]
            total_pages = (len(transactions) + self.transactions_per_page - 1) // self.transactions_per_page
            
            tx_lines = []
            for tx in page_transactions:
                amount = tx['amount']
                amount_str = format_transaction_amount(amount)
                desc = tx.get('description', tx['type'])
                
                # Formatar data
                try:
                    dt = datetime.fromisoformat(tx['created_at'])
                    date_str = dt.strftime("%d/%m")
                except:
                    date_str = "?"
                
                # Incluir usuário relacionado se houver
                related = ""
                if tx.get('related_user_id'):
                    member = self.guild.get_member(tx['related_user_id'])
                    if member:
                        related = f" • {member.display_name}"
                
                tx_lines.append(f"`{date_str}` **{amount_str}** — {desc}{related}")
            
            filter_text = f" ({self.filter_type})" if self.filter_type else ""
            embed.add_field(
                name=f"Histórico{filter_text} ({self.page + 1}/{total_pages})",
                value="\n".join(tx_lines) if tx_lines else "nenhuma transação",
                inline=False
            )
        else:
            embed.add_field(
                name="Histórico",
                value="nenhuma transação",
                inline=False
            )
        
        # Atualizar botões de navegação
        self._update_navigation_buttons(transactions)
        
        embed.set_footer(text="⏱️ Expira em 3 minutos")
        
        return embed
    
    def _update_navigation_buttons(self, transactions: list):
        """Atualiza estado dos botões de navegação"""
        total_pages = (len(transactions) + self.transactions_per_page - 1) // self.transactions_per_page if transactions else 1
        
        for child in self.children:
            if hasattr(child, 'custom_id'):
                if child.custom_id == 'prev_page':
                    child.disabled = self.page <= 0
                elif child.custom_id == 'next_page':
                    child.disabled = self.page >= total_pages - 1
    
    async def refresh(self, interaction: discord.Interaction):
        """Atualiza o embed"""
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="prev_page", row=0)
    async def prev_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self.refresh(interaction)
    
    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="next_page", row=0)
    async def next_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await self.refresh(interaction)
    
    @discord.ui.button(label="📅 Daily", style=discord.ButtonStyle.secondary, custom_id="filter_daily", row=1)
    async def filter_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_type = 'daily' if self.filter_type != 'daily' else None
        self.page = 0
        self._update_filter_buttons()
        await self.refresh(interaction)
    
    @discord.ui.button(label="📥 Recebido", style=discord.ButtonStyle.secondary, custom_id="filter_in", row=1)
    async def filter_in(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_type = 'transfer_in' if self.filter_type != 'transfer_in' else None
        self.page = 0
        self._update_filter_buttons()
        await self.refresh(interaction)
    
    @discord.ui.button(label="📤 Enviado", style=discord.ButtonStyle.secondary, custom_id="filter_out", row=1)
    async def filter_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_type = 'transfer_out' if self.filter_type != 'transfer_out' else None
        self.page = 0
        self._update_filter_buttons()
        await self.refresh(interaction)
    
    @discord.ui.button(label="🎰 Apostas", style=discord.ButtonStyle.secondary, custom_id="filter_gambling", row=1)
    async def filter_gambling(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.filter_type = 'gambling' if self.filter_type != 'gambling' else None
        self.page = 0
        self._update_filter_buttons()
        await self.refresh(interaction)
    
    def _update_filter_buttons(self):
        """Atualiza estilo dos botões de filtro para mostrar qual está ativo"""
        filter_map = {
            'filter_daily': 'daily',
            'filter_in': 'transfer_in',
            'filter_out': 'transfer_out',
            'filter_gambling': 'gambling',
        }
        
        for child in self.children:
            if hasattr(child, 'custom_id') and child.custom_id in filter_map:
                if self.filter_type == filter_map[child.custom_id]:
                    child.style = discord.ButtonStyle.primary
                else:
                    child.style = discord.ButtonStyle.secondary


# ======================== UI COMPONENTS - DAILY CONFIG ========================

class EditBaseModal(discord.ui.Modal):
    """Modal para editar valor base do daily"""
    
    def __init__(self, guild_id: int):
        super().__init__(title="Editar Valor Base")
        self.guild_id = guild_id
        
        config = get_daily_config(guild_id)
        
        self.base_input = discord.ui.TextInput(
            label="Valor Base do Daily",
            placeholder="ex: 500",
            default=str(config['base']),
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.base_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.base_input.value)
        except ValueError:
            return await interaction.response.send_message(
                "❌ digite um número válido", ephemeral=True
            )
        
        if value < 1:
            return await interaction.response.send_message(
                "❌ o valor deve ser maior que 0", ephemeral=True
            )
        
        set_daily_config(self.guild_id, base=value)
        
        embed = discord.Embed(
            description=f"✅ valor base alterado para {mora_emoji()} **{format_number(value)}**",
            color=Colors.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Update parent view
        if hasattr(self, 'parent_view') and self.parent_view:
            await self.parent_view.refresh_embed(interaction)


class EditStreakModal(discord.ui.Modal):
    """Modal para editar bônus de streak"""
    
    def __init__(self, guild_id: int):
        super().__init__(title="Editar Bônus de Streak")
        self.guild_id = guild_id
        
        config = get_daily_config(guild_id)
        
        self.streak_input = discord.ui.TextInput(
            label="Bônus por dia de Streak",
            placeholder="ex: 50",
            default=str(config['streak_bonus']),
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.streak_input)
        
        self.max_input = discord.ui.TextInput(
            label="Bônus Máximo de Streak",
            placeholder="ex: 1000",
            default=str(config['max_streak_bonus']),
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.max_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            streak_value = int(self.streak_input.value)
            max_value = int(self.max_input.value)
        except ValueError:
            return await interaction.response.send_message(
                "❌ digite números válidos", ephemeral=True
            )
        
        if streak_value < 0 or max_value < 0:
            return await interaction.response.send_message(
                "❌ os valores não podem ser negativos", ephemeral=True
            )
        
        set_daily_config(self.guild_id, streak_bonus=streak_value, max_streak_bonus=max_value)
        
        embed = discord.Embed(
            description=f"✅ streak configurado:\n"
                       f"Bônus: {mora_emoji()} **+{format_number(streak_value)}**/dia\n"
                       f"Máximo: {mora_emoji()} **{format_number(max_value)}**",
            color=Colors.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Update parent view
        if hasattr(self, 'parent_view') and self.parent_view:
            await self.parent_view.refresh_embed(interaction)


class DailyConfigView(discord.ui.View):
    """View principal para configuração do Daily com botões"""
    
    def __init__(self, guild: discord.Guild, user_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.message: Optional[discord.Message] = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ apenas quem usou o comando pode interagir", 
                ephemeral=True
            )
            return False
        return True
    
    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
    
    def get_config_embed(self) -> discord.Embed:
        """Gera o embed de configuração do daily"""
        config = get_daily_config(self.guild.id)
        
        embed = discord.Embed(
            title=f"{mora_emoji()} Configuração do Daily",
            description="Configure os valores da recompensa diária do servidor.\n"
                       "Use os botões abaixo para editar cada configuração.",
            color=Colors.XP
        )
        
        # Valor Base
        base = config['base']
        embed.add_field(
            name="💰 Recompensa Base",
            value=f"{mora_emoji()} **{format_number(base)}** por dia\n"
                 f"└ valor que todos recebem ao usar `/daily`",
            inline=False
        )
        
        # Bônus de Streak
        streak = config['streak_bonus']
        max_streak = config['max_streak_bonus']
        
        # Calcular quantos dias para max
        days_to_max = max_streak // streak if streak > 0 else 0
        
        embed.add_field(
            name="🔥 Bônus de Streak",
            value=f"{mora_emoji()} **+{format_number(streak)}** por dia de streak\n"
                 f"└ máximo: {mora_emoji()} **{format_number(max_streak)}** ({days_to_max} dias)",
            inline=False
        )
        
        # Exemplo de recompensa
        day1 = base + streak
        day7 = base + min(7 * streak, max_streak)
        day30 = base + min(30 * streak, max_streak)
        
        embed.add_field(
            name="📊 Simulação de Recompensa",
            value=f"```\n"
                 f"Dia 1:  {format_number(day1)} mora\n"
                 f"Dia 7:  {format_number(day7)} mora\n"
                 f"Dia 30: {format_number(day30)} mora\n"
                 f"```",
            inline=False
        )
        
        # Valores padrão
        embed.add_field(
            name="ℹ️ Valores Padrão",
            value=f"Base: `{DEFAULT_DAILY_BASE}` • Streak: `+{DEFAULT_DAILY_STREAK_BONUS}/dia` • Max: `{DEFAULT_DAILY_MAX_STREAK_BONUS}`",
            inline=False
        )
        
        embed.set_footer(text="⏱️ Expira em 5 minutos")
        
        return embed
    
    async def refresh_embed(self, interaction: discord.Interaction):
        """Atualiza o embed após mudanças"""
        if self.message:
            try:
                embed = self.get_config_embed()
                await self.message.edit(embed=embed, view=self)
            except discord.NotFound:
                pass
    
    @discord.ui.button(label="Editar Base", style=discord.ButtonStyle.primary, emoji="💰", row=0)
    async def edit_base_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditBaseModal(self.guild.id)
        modal.parent_view = self
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Editar Streak", style=discord.ButtonStyle.primary, emoji="🔥", row=0)
    async def edit_streak_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditStreakModal(self.guild.id)
        modal.parent_view = self
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Resetar Padrão", style=discord.ButtonStyle.danger, emoji="🔄", row=1)
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        set_daily_config(
            self.guild.id,
            base=DEFAULT_DAILY_BASE,
            streak_bonus=DEFAULT_DAILY_STREAK_BONUS,
            max_streak_bonus=DEFAULT_DAILY_MAX_STREAK_BONUS
        )
        
        embed = discord.Embed(
            description=f"🔄 valores restaurados para o padrão",
            color=Colors.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        await self.refresh_embed(interaction)
    
    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.secondary, emoji="❌", row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        
        embed = self.get_config_embed()
        embed.set_footer(text="✅ Configuração finalizada")
        
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# ======================== DAILY LOGIC ========================

def claim_daily(guild_id: int, user_id: int) -> tuple[bool, int, int, str]:
    """
    Resgata recompensa diária.
    Retorna: (sucesso, valor_ganho, streak_atual, mensagem)
    """
    user = user_repo.get_or_create_user(guild_id, user_id)
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    
    last_claim = user.get('last_daily_claim')
    current_streak = user.get('daily_claim_streak', 0)
    max_streak = user.get('max_daily_claim_streak', 0)
    
    # Já resgatou hoje?
    if last_claim == today:
        # Calcular tempo até meia-noite UTC
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        remaining = tomorrow - now
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        
        if hours > 0:
            time_str = f"{hours}h {minutes}min"
        else:
            time_str = f"{minutes}min"
        
        return False, 0, current_streak, f"você já resgatou hoje\n\n⏰ próximo daily em **{time_str}**"
    
    # Calcular streak
    # Primeiro dia = streak 0 (sem bônus)
    # Segundo dia consecutivo = streak 1 (primeiro bônus)
    if last_claim is None:
        # Nunca resgatou antes - primeiro dia
        new_streak = 0
    elif last_claim == yesterday:
        # Resgatou ontem - incrementa streak
        new_streak = current_streak + 1
    else:
        # Perdeu streak - volta ao 0
        new_streak = 0
    
    # Obter configuração do servidor
    daily_config = get_daily_config(guild_id)
    base_reward = daily_config['base']
    streak_bonus_per_day = daily_config['streak_bonus']
    max_streak_bonus = daily_config['max_streak_bonus']
    
    # Calcular recompensa (streak 0 = sem bônus)
    streak_bonus = min(new_streak * streak_bonus_per_day, max_streak_bonus)
    reward = base_reward + streak_bonus
    
    # Bônus aleatório dinâmico
    # 2% de chance de 3x, 10% de chance de 2x
    bonus_msg = ""
    roll = random.random()
    if roll < 0.02:  # 2% para 3x
        reward *= 3
        bonus_msg = " 🌟 **TRIPLO! (3x)**"
    elif roll < 0.12:  # 10% para 2x (0.02 + 0.10)
        reward *= 2
        bonus_msg = " ✨ **DOBRO! (2x)**"
    
    # Atualizar dados
    new_max = max(max_streak, new_streak)
    user_repo.update_user(guild_id, user_id,
                   last_daily_claim=today,
                   daily_claim_streak=new_streak,
                   max_daily_claim_streak=new_max)
    
    # Adicionar mora com registro de transação
    new_balance = add_mora(guild_id, user_id, reward,
                           transaction_type='daily',
                           description=f'Daily (streak: {new_streak}){bonus_msg}')
    
    return True, reward, new_streak, bonus_msg


# ======================== COG ========================

class Mora(commands.Cog):
    """Sistema de economia com Mora"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def cog_check(self, ctx: commands.Context) -> bool:
        """Check if economy feature is enabled for this guild"""
        if ctx.guild and not guild_repo.is_feature_enabled(ctx.guild.id, "economy"):
            await ctx.send(embed=embed_disabled("economia"), ephemeral=True)
            return False
        return True
    
    # -------------------- BANCO --------------------
    
    @commands.hybrid_command(
        name='banco',
        aliases=['bank', 'mora', 'saldo', 'bal', 'carteira'],
        description='Mostra seu banco com saldo, estatísticas e histórico de transações'
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def banco_command(self, ctx: commands.Context, membro: Optional[discord.Member] = None):
        """Mostra banco com histórico de transações"""
        target = membro or ctx.author
        
        view = BancoView(ctx.guild, target, ctx.author.id)
        embed = view.get_embed()
        
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg
    
    # -------------------- DAILY --------------------
    
    @commands.hybrid_command(
        name='daily',
        aliases=['diario', 'diaria'],
        description='Resgata sua recompensa diária de Mora'
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def daily_command(self, ctx: commands.Context):
        """Resgata recompensa diária"""
        success, reward, streak, extra_msg = claim_daily(ctx.guild.id, ctx.author.id)
        
        if not success:
            embed = discord.Embed(
                description=extra_msg,
                color=Colors.USER_ERROR
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        new_balance = get_mora(ctx.guild.id, ctx.author.id)
        
        embed = discord.Embed(
            title=f"{mora_emoji()} Daily",
            description=f"você recebeu **{format_number(reward)}**{extra_msg}",
            color=Colors.SUCCESS
        )
        
        embed.add_field(
            name="Streak",
            value=f"```{streak} dias```",
            inline=True
        )
        embed.add_field(
            name="Saldo",
            value=f"```{format_number(new_balance)}```",
            inline=True
        )
        
        await ctx.reply(embed=embed, mention_author=False)
        
        # Emit event
        await event_bus.emit(BotEvent.DAILY_CLAIMED, ctx.guild.id, {
            'user_id': ctx.author.id,
            'reward': reward,
            'streak': streak
        })
    
    @commands.hybrid_command(
        name='pagar',
        aliases=['transferir', 'transfer', 'pay', 'give', 'doar'],
        description='Transfere Mora para outro usuário'
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    @app_commands.describe(
        membro="Usuário que vai receber",
        valor="Quantidade de Mora"
    )
    async def transfer_command(self, ctx: commands.Context, membro: discord.Member, valor: int):
        """Transfere Mora para outro usuário"""
        if membro.bot:
            embed = discord.Embed(
                description="❌ você não pode transferir pra bots",
                color=Colors.USER_ERROR
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        success, message = transfer_mora(ctx.guild.id, ctx.author.id, membro.id, valor)
        
        if not success:
            embed = discord.Embed(
                description=f"❌ {message}",
                color=Colors.USER_ERROR
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        embed = discord.Embed(
            title=f"{mora_emoji()} Transferência",
            description=f"{ctx.author.mention} → {membro.mention}\n\n{message}",
            color=Colors.SUCCESS
        )
        
        # Mostrar novos saldos
        sender_bal = get_mora(ctx.guild.id, ctx.author.id)
        receiver_bal = get_mora(ctx.guild.id, membro.id)
        
        embed.add_field(
            name="Seu Saldo",
            value=f"```{format_number(sender_bal)}```",
            inline=True
        )
        embed.add_field(
            name=f"{membro.display_name}",
            value=f"```{format_number(receiver_bal)}```",
            inline=True
        )
        
        await ctx.reply(embed=embed, mention_author=False)
    
    # -------------------- RICOS --------------------
    
    @commands.hybrid_command(
        name='ricos',
        aliases=['richest', 'topmora', 'moratop'],
        description='Ranking dos mais ricos do servidor'
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def richest_command(self, ctx: commands.Context):
        """Ranking de Mora do servidor"""
        leaderboard = user_repo.get_leaderboard_values(ctx.guild.id, 'mora', 10)
        
        if not leaderboard:
            embed = discord.Embed(
                description="ninguém tem mora ainda\n\nuse `/daily` pra começar",
                color=Colors.INFO
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        
        for i, (user_id, mora_amount) in enumerate(leaderboard):
            medal = medals[i] if i < 3 else f"`{i+1}`"
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            
            lines.append(f"{medal} **{name}** — {format_number(mora_amount)}")
        
        embed = discord.Embed(
            title=f"{mora_emoji()} Ranking",
            description="\n".join(lines),
            color=Colors.XP
        )
        
        # Posição do autor
        user_rank = user_repo.get_user_rank(ctx.guild.id, ctx.author.id, 'mora')
        user_mora = get_mora(ctx.guild.id, ctx.author.id)
        
        embed.set_footer(
            text=f"sua posição: #{user_rank or '?'} • {format_number(user_mora)} mora"
        )
        
        await ctx.reply(embed=embed, mention_author=False)
    
    # -------------------- ADMIN: CONFIGURAR DAILY --------------------
    
    @commands.hybrid_command(
        name='configdaily',
        aliases=['dailyconfig', 'economyconfig'],
        description='Painel de configuração do daily do servidor'
    )
    @commands.has_permissions(administrator=True)
    async def daily_config_command(self, ctx: commands.Context):
        """Abre painel de configuração do daily (admin)"""
        view = DailyConfigView(ctx.guild, ctx.author.id)
        embed = view.get_config_embed()
        
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Mora(bot))
