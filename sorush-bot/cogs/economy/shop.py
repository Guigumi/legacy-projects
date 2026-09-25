"""
Sistema de Loja - Admin-Configurável

Permite admins criarem cargos para venda com preço e duração personalizados.
Usuários podem comprar cargos temporários, permanentes ou condicionais usando Mora.
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Select, Button, Modal, TextInput
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

from config import Colors
from services.repositories import user_repo, guild_repo
from services.repositories.shop_repository import shop_item_repo, shop_purchase_repo
from services.event_bus import event_bus, BotEvent
from services.embed_helpers import embed_disabled
from cogs.economy.mora import mora_emoji, get_mora, remove_mora, add_mora

logger = logging.getLogger(__name__)


def format_number(number: int) -> str:
    """Formata número com separadores de milhar"""
    return f"{number:,}".replace(',', '.')


# ======================== CONFIGURAÇÃO ========================

# Tipos de duração
DURATION_PERMANENT = "permanent"  # Para sempre
DURATION_TEMPORARY = "temporary"  # Por X dias
DURATION_CONDITIONAL = "conditional"  # Até perder streak, level, etc.


# ======================== HELPERS (wrappers around repos) ========================

def get_shop_config(guild_id: int) -> dict:
    """Returns shop config dict for backward compat with UI code"""
    return {
        "enabled": guild_repo.is_shop_enabled(guild_id),
        "items": get_shop_items(guild_id),
        "purchases": []
    }


def save_shop_config(guild_id: int, config: dict) -> None:
    """Saves shop enabled state via DB"""
    guild_repo.set_shop_enabled(guild_id, config.get('enabled', True))


def get_shop_items(guild_id: int) -> dict:
    """Returns items dict keyed by role_{id} for backward compat"""
    items_list = shop_item_repo.get_items(guild_id)
    return {f"role_{item['role_id']}": item for item in items_list}


def add_shop_item(
    guild_id: int,
    role_id: int,
    price: int,
    duration_type: str = DURATION_TEMPORARY,
    duration_days: int = 7,
    condition: str = None,
    name: str = None
) -> str:
    """Adiciona item à loja via DB. Retorna ID do item."""
    shop_item_repo.add_item(
        guild_id, role_id, price,
        duration_type=duration_type,
        duration_days=duration_days if duration_type == DURATION_TEMPORARY else None,
        condition=condition if duration_type == DURATION_CONDITIONAL else None,
        name=name
    )
    return f"role_{role_id}"


def update_shop_item(guild_id: int, item_id: str, **kwargs) -> bool:
    """Atualiza item da loja via DB"""
    role_id = int(item_id.replace("role_", ""))
    return shop_item_repo.update_item(guild_id, role_id, **kwargs)


def remove_shop_item(guild_id: int, item_id: str) -> bool:
    """Remove item da loja via DB"""
    role_id = int(item_id.replace("role_", ""))
    return shop_item_repo.remove_item(guild_id, role_id)


def add_purchase(
    guild_id: int,
    user_id: int,
    role_id: int,
    duration_type: str,
    duration_days: int = None,
    condition: str = None
) -> None:
    """Registra compra via DB"""
    shop_purchase_repo.add_purchase(
        guild_id, user_id, role_id,
        duration_type=duration_type,
        duration_days=duration_days,
        condition=condition
    )


def get_expired_purchases(guild_id: int) -> list:
    """Retorna lista de compras expiradas (e remove do DB)"""
    return shop_purchase_repo.get_expired_purchases(guild_id)


def get_user_purchases(guild_id: int, user_id: int) -> list:
    """Retorna compras ativas do usuário via DB"""
    return shop_purchase_repo.get_user_purchases(guild_id, user_id)


def format_duration(item: dict) -> str:
    """Formata a duração do item para exibição"""
    duration_type = item.get('duration_type', DURATION_TEMPORARY)
    
    if duration_type == DURATION_PERMANENT:
        return "♾️ Permanente"
    elif duration_type == DURATION_CONDITIONAL:
        condition = item.get('condition', 'streak')
        conditions = {
            'streak': '🔥 Enquanto tiver streak',
            'level': '📊 Enquanto manter level',
            'activity': '💬 Enquanto ativo no servidor'
        }
        return conditions.get(condition, f'⚡ Condição: {condition}')
    else:
        days = item.get('duration_days', 7)
        return f"📅 {days} dia{'s' if days != 1 else ''}"


def format_duration_short(item: dict) -> str:
    """Formata a duração do item (versão curta)"""
    duration_type = item.get('duration_type', DURATION_TEMPORARY)
    
    if duration_type == DURATION_PERMANENT:
        return "♾️ perm"
    elif duration_type == DURATION_CONDITIONAL:
        condition = item.get('condition', 'streak')
        return f"⚡ {condition}"
    else:
        days = item.get('duration_days', 7)
        return f"📅 {days}d"


# ======================== UI COMPONENTS - COMPRA ========================

class ShopSelect(Select):
    """Menu de seleção de itens da loja"""
    
    def __init__(self, guild: discord.Guild, items: dict):
        options = []
        self.items_data = {}
        
        for item_id, item in items.items():
            role = guild.get_role(item['role_id'])
            if not role:
                continue
            
            name = item.get('name') or role.name
            duration_text = format_duration_short(item)
            
            self.items_data[item_id] = {**item, 'role': role, 'display_name': name}
            
            options.append(discord.SelectOption(
                label=f"{name} - {format_number(item['price'])} mora",
                description=f"{duration_text}",
                value=item_id,
                emoji="🎭"
            ))
        
        if not options:
            options.append(discord.SelectOption(
                label="Loja vazia",
                value="empty",
                emoji="📭"
            ))
        
        super().__init__(
            placeholder="escolha um cargo pra comprar...",
            options=options[:25]
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "empty":
            return await interaction.response.defer()
        
        item_id = self.values[0]
        item = self.items_data.get(item_id)
        
        if not item:
            return await interaction.response.send_message(
                "❌ item não encontrado", ephemeral=True
            )
        
        role = item['role']
        
        # Verificar se já tem o cargo
        if role in interaction.user.roles:
            embed = discord.Embed(
                description=f"❌ você já tem o cargo **{role.name}**",
                color=Colors.USER_ERROR
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Verificar saldo
        user_mora = get_mora(interaction.guild.id, interaction.user.id)
        
        if user_mora < item['price']:
            embed = discord.Embed(
                description=f"❌ você precisa de {mora_emoji()} **{format_number(item['price'])}** "
                           f"mas só tem {mora_emoji()} **{format_number(user_mora)}**",
                color=Colors.USER_ERROR
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Confirmar compra
        duration_text = format_duration(item)
        
        embed = discord.Embed(
            title=f"🎭 {item['display_name']}",
            description=f"Cargo **{role.name}**\n\n"
                       f"**Duração:** {duration_text}\n"
                       f"**Preço:** {mora_emoji()} {format_number(item['price'])}\n"
                       f"**Seu saldo:** {mora_emoji()} {format_number(user_mora)}",
            color=Colors.WARNING
        )
        embed.set_footer(text="confirma a compra?")
        
        view = ConfirmPurchaseView(item_id, item, role)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ConfirmPurchaseView(View):
    """View de confirmação de compra"""
    
    def __init__(self, item_id: str, item: dict, role: discord.Role):
        super().__init__(timeout=60)
        self.item_id = item_id
        self.item = item
        self.role = role
    
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        # Verificar saldo novamente
        user_mora = get_mora(interaction.guild.id, interaction.user.id)
        
        if user_mora < self.item['price']:
            embed = discord.Embed(
                description="❌ você não tem mora suficiente mais",
                color=Colors.USER_ERROR
            )
            return await interaction.response.edit_message(embed=embed, view=None)
        
        # Verificar se já tem o cargo
        if self.role in interaction.user.roles:
            embed = discord.Embed(
                description=f"❌ você já tem o cargo **{self.role.name}**",
                color=Colors.USER_ERROR
            )
            return await interaction.response.edit_message(embed=embed, view=None)
        
        # Processar compra
        try:
            await interaction.user.add_roles(self.role, reason="Compra na loja")
        except discord.Forbidden:
            embed = discord.Embed(
                description="❌ não consigo adicionar o cargo\no bot precisa de permissões",
                color=Colors.ERROR
            )
            return await interaction.response.edit_message(embed=embed, view=None)
        
        remove_mora(
            interaction.guild.id, 
            interaction.user.id, 
            self.item['price'],
            transaction_type='shop',
            description=f'Compra: {self.role.name}'
        )
        add_purchase(
            interaction.guild.id, 
            interaction.user.id, 
            self.role.id,
            self.item.get('duration_type', DURATION_TEMPORARY),
            self.item.get('duration_days'),
            self.item.get('condition')
        )
        
        new_balance = get_mora(interaction.guild.id, interaction.user.id)
        duration_text = format_duration(self.item)
        
        embed = discord.Embed(
            title="✅ Compra realizada!",
            description=f"você comprou **{self.role.name}**\n\n"
                       f"**Duração:** {duration_text}\n"
                       f"**Novo saldo:** {mora_emoji()} **{format_number(new_balance)}**",
            color=Colors.SUCCESS
        )
        
        if self.item.get('duration_type') == DURATION_TEMPORARY:
            embed.set_footer(text="o cargo será removido automaticamente quando expirar")
        elif self.item.get('duration_type') == DURATION_CONDITIONAL:
            embed.set_footer(text="o cargo será removido se a condição não for mantida")
        
        await interaction.response.edit_message(embed=embed, view=None)
        
        # Emit event
        await event_bus.emit(BotEvent.SHOP_PURCHASE, interaction.guild.id, {
            'user_id': interaction.user.id,
            'role_id': self.role.id,
            'price': self.item['price'],
            'duration_type': self.item.get('duration_type', DURATION_TEMPORARY)
        })
        
        self.stop()
    
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            description="❌ compra cancelada",
            color=Colors.USER_ERROR
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class ShopView(View):
    """View principal da loja"""
    
    def __init__(self, guild: discord.Guild, items: dict):
        super().__init__(timeout=120)
        if items:
            self.add_item(ShopSelect(guild, items))


# ======================== UI COMPONENTS - ADMIN CONFIG ========================

class AddItemModal(Modal):
    """Modal para adicionar item à loja"""
    
    def __init__(self, role: discord.Role, duration_type: str, condition: str = None):
        super().__init__(title="Adicionar à Loja")
        self.role = role
        self.duration_type = duration_type
        self.condition = condition
        
        self.price_input = TextInput(
            label="Preço em Mora",
            placeholder="ex: 5000",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.price_input)
        
        if duration_type == DURATION_TEMPORARY:
            self.duration_input = TextInput(
                label="Duração (dias)",
                placeholder="ex: 7",
                min_length=1,
                max_length=4,
                required=True
            )
            self.add_item(self.duration_input)
        else:
            self.duration_input = None
        
        self.name_input = TextInput(
            label="Nome na loja (opcional)",
            placeholder="deixe vazio para usar nome do cargo",
            required=False
        )
        self.add_item(self.name_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price_input.value)
        except ValueError:
            embed = discord.Embed(
                description="❌ preço deve ser um número",
                color=Colors.USER_ERROR
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        if price < 1:
            embed = discord.Embed(
                description="❌ preço deve ser maior que 0",
                color=Colors.USER_ERROR
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        duration_days = 7
        if self.duration_input:
            try:
                duration_days = int(self.duration_input.value)
            except ValueError:
                embed = discord.Embed(
                    description="❌ duração deve ser um número",
                    color=Colors.USER_ERROR
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            
            if duration_days < 1 or duration_days > 365:
                embed = discord.Embed(
                    description="❌ duração deve ser entre 1 e 365 dias",
                    color=Colors.USER_ERROR
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        name = self.name_input.value.strip() if self.name_input.value else None
        
        add_shop_item(
            interaction.guild.id,
            self.role.id,
            price,
            self.duration_type,
            duration_days,
            self.condition,
            name
        )
        
        display_name = name or self.role.name
        duration_text = format_duration({
            'duration_type': self.duration_type,
            'duration_days': duration_days,
            'condition': self.condition
        })
        
        embed = discord.Embed(
            title="✅ Item adicionado à loja!",
            description=f"**{display_name}**\n\n"
                       f"Cargo: {self.role.mention}\n"
                       f"Preço: {mora_emoji()} **{format_number(price)}**\n"
                       f"Duração: {duration_text}",
            color=Colors.SUCCESS
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Atualizar view pai
        if hasattr(self, 'parent_view') and self.parent_view:
            try:
                await self.parent_view.refresh_embed(interaction)
            except Exception:
                pass


class EditItemModal(Modal):
    """Modal para editar item existente"""
    
    def __init__(self, guild_id: int, item_id: str, item: dict, role: discord.Role):
        super().__init__(title=f"Editar: {role.name[:40]}")
        self.guild_id = guild_id
        self.item_id = item_id
        self.item = item
        self.role = role
        
        self.price_input = TextInput(
            label="Preço em Mora",
            placeholder="ex: 5000",
            default=str(item.get('price', 1000)),
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.price_input)
        
        if item.get('duration_type') == DURATION_TEMPORARY:
            self.duration_input = TextInput(
                label="Duração (dias)",
                placeholder="ex: 7",
                default=str(item.get('duration_days', 7)),
                min_length=1,
                max_length=4,
                required=True
            )
            self.add_item(self.duration_input)
        else:
            self.duration_input = None
        
        self.name_input = TextInput(
            label="Nome na loja",
            placeholder="deixe vazio para usar nome do cargo",
            default=item.get('name') or '',
            required=False
        )
        self.add_item(self.name_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price_input.value)
        except ValueError:
            return await interaction.response.send_message("❌ preço inválido", ephemeral=True)
        
        if price < 1:
            return await interaction.response.send_message("❌ preço deve ser maior que 0", ephemeral=True)
        
        updates = {'price': price}
        
        if self.duration_input:
            try:
                duration_days = int(self.duration_input.value)
                if duration_days < 1 or duration_days > 365:
                    return await interaction.response.send_message("❌ duração deve ser 1-365 dias", ephemeral=True)
                updates['duration_days'] = duration_days
            except ValueError:
                return await interaction.response.send_message("❌ duração inválida", ephemeral=True)
        
        name = self.name_input.value.strip() if self.name_input.value else None
        updates['name'] = name
        
        update_shop_item(self.guild_id, self.item_id, **updates)
        
        embed = discord.Embed(
            description=f"✅ **{self.role.name}** atualizado!",
            color=Colors.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        if hasattr(self, 'parent_view') and self.parent_view:
            await self.parent_view.refresh_embed(interaction)


class DurationTypeSelect(Select):
    """Select para escolher tipo de duração"""
    
    def __init__(self, role: discord.Role, parent_view: 'ShopConfigView' = None):
        self.role = role
        self._parent_view = parent_view
        
        options = [
            discord.SelectOption(
                label="Temporário",
                description="O cargo expira após X dias",
                emoji="📅",
                value=DURATION_TEMPORARY
            ),
            discord.SelectOption(
                label="Permanente",
                description="O cargo nunca expira",
                emoji="♾️",
                value=DURATION_PERMANENT
            ),
            discord.SelectOption(
                label="Enquanto tiver Streak",
                description="Perde o cargo se perder o streak do daily",
                emoji="🔥",
                value=f"{DURATION_CONDITIONAL}:streak"
            ),
            discord.SelectOption(
                label="Enquanto ativo",
                description="Perde se ficar inativo por muito tempo",
                emoji="💬",
                value=f"{DURATION_CONDITIONAL}:activity"
            ),
        ]
        
        super().__init__(
            placeholder="escolha o tipo de duração...",
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        
        if value.startswith(DURATION_CONDITIONAL):
            duration_type = DURATION_CONDITIONAL
            condition = value.split(':')[1]
        else:
            duration_type = value
            condition = None
        
        modal = AddItemModal(self.role, duration_type, condition)
        # Usar _parent_view que foi passado no construtor
        modal.parent_view = self._parent_view
        
        await interaction.response.send_modal(modal)


class ItemSelectForEdit(Select):
    """Select para escolher item para editar/remover"""
    
    def __init__(self, guild: discord.Guild, items: dict, action: str = "edit"):
        self.guild = guild
        self.items = items
        self.action = action
        
        options = []
        for item_id, item in items.items():
            role = guild.get_role(item['role_id'])
            if not role:
                continue
            
            name = item.get('name') or role.name
            duration_text = format_duration_short(item)
            
            options.append(discord.SelectOption(
                label=name[:100],
                description=f"{mora_emoji()} {format_number(item['price'])} • {duration_text}",
                value=item_id,
                emoji="🎭"
            ))
        
        if not options:
            options.append(discord.SelectOption(
                label="Nenhum item",
                value="none",
                emoji="📭"
            ))
        
        placeholder = "escolha um item para editar..." if action == "edit" else "escolha um item para remover..."
        super().__init__(placeholder=placeholder, options=options[:25])
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.defer()
        
        item_id = self.values[0]
        item = self.items.get(item_id)
        
        if not item:
            return await interaction.response.send_message("❌ item não encontrado", ephemeral=True)
        
        role = self.guild.get_role(item['role_id'])
        
        if self.action == "edit":
            modal = EditItemModal(self.guild.id, item_id, item, role)
            modal.parent_view = getattr(self.view, 'parent_view', None)
            await interaction.response.send_modal(modal)
        else:  # remove
            if remove_shop_item(self.guild.id, item_id):
                embed = discord.Embed(
                    description=f"✅ **{role.name if role else 'Item'}** removido da loja",
                    color=Colors.SUCCESS
                )
            else:
                embed = discord.Embed(
                    description="❌ erro ao remover item",
                    color=Colors.ERROR
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            parent = getattr(self.view, 'parent_view', None)
            if parent:
                await parent.refresh_embed(interaction)


class AddItemView(View):
    """View para adicionar item (escolher duração)"""
    
    def __init__(self, role: discord.Role, parent_view: 'ShopConfigView'):
        super().__init__(timeout=60)
        self.role = role
        self.parent_view = parent_view
        
        # Passar parent_view diretamente para o select
        select = DurationTypeSelect(role, parent_view)
        self.add_item(select)
    
    async def refresh_embed(self, interaction: discord.Interaction):
        if self.parent_view:
            await self.parent_view.refresh_embed(interaction)


class ShopConfigView(View):
    """View principal de configuração da loja (estilo dailyconfig)"""
    
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
        """Gera o embed de configuração da loja"""
        config = get_shop_config(self.guild.id)
        items = config.get('items', {})
        enabled = config.get('enabled', True)
        
        status = "Aberta" if enabled else "Fechada"
        
        embed = discord.Embed(
            title="🏪 Config Loja",
            color=Colors.XP
        )
        
        embed.add_field(
            name="Status",
            value=f"```{status}```",
            inline=True
        )
        embed.add_field(
            name="Itens",
            value=f"```{len(items)}```",
            inline=True
        )
        embed.add_field(name="", value="\u200b", inline=True)
        
        # Lista de itens
        if items:
            lines = []
            for item_id, item in list(items.items())[:8]:
                role = self.guild.get_role(item['role_id'])
                if not role:
                    continue
                
                name = item.get('name') or role.name
                price = format_number(item['price'])
                duration = format_duration_short(item)
                
                lines.append(f"**{name}** • {price} • {duration}")
            
            if lines:
                embed.add_field(
                    name="Itens",
                    value="\n".join(lines),
                    inline=False
                )
            
            if len(items) > 8:
                embed.set_footer(text=f"...e mais {len(items) - 8} itens")
        else:
            embed.add_field(
                name="Itens",
                value="nenhum item cadastrado",
                inline=False
            )
        
        return embed
    
    async def refresh_embed(self, interaction: discord.Interaction):
        """Atualiza o embed após mudanças"""
        if self.message:
            try:
                embed = self.get_config_embed()
                await self.message.edit(embed=embed, view=self)
            except discord.NotFound:
                pass
    
    @discord.ui.button(label="Adicionar Item", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="➕ Adicionar Item",
            description="Digite a **menção ou ID do cargo** que deseja adicionar à loja.\n\n"
                       "Exemplo: `@VIP` ou `1234567890`",
            color=Colors.INFO
        )
        embed.set_footer(text="Aguardando resposta... (30s)")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id
        
        try:
            msg = await interaction.client.wait_for('message', timeout=30.0, check=check)
            
            # Tentar encontrar o cargo
            role = None
            content = msg.content.strip()
            
            # Por menção
            if msg.role_mentions:
                role = msg.role_mentions[0]
            # Por ID
            elif content.isdigit():
                role = self.guild.get_role(int(content))
            # Por nome
            else:
                role = discord.utils.get(self.guild.roles, name=content)
            
            # Deletar mensagem do usuário
            try:
                await msg.delete()
            except:
                pass
            
            if not role:
                await interaction.followup.send("❌ cargo não encontrado", ephemeral=True)
                return
            
            if role >= self.guild.me.top_role:
                await interaction.followup.send(
                    "❌ não posso gerenciar esse cargo (está acima de mim)",
                    ephemeral=True
                )
                return
            
            # Verificar se já está na loja
            items = get_shop_items(self.guild.id)
            for item in items.values():
                if item['role_id'] == role.id:
                    await interaction.followup.send(
                        f"❌ **{role.name}** já está na loja",
                        ephemeral=True
                    )
                    return
            
            # Mostrar opções de duração
            embed = discord.Embed(
                title=f"➕ Adicionar: {role.name}",
                description="Escolha o **tipo de duração** para este cargo:",
                color=Colors.INFO
            )
            
            view = AddItemView(role, self)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except TimeoutError:
            await interaction.followup.send("❌ tempo esgotado", ephemeral=True)
    
    @discord.ui.button(label="Editar Item", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def edit_button(self, interaction: discord.Interaction, button: Button):
        items = get_shop_items(self.guild.id)
        
        if not items:
            embed = discord.Embed(
                description="📭 não há itens para editar",
                color=Colors.WARNING
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        embed = discord.Embed(
            title="✏️ Editar Item",
            description="Selecione o item que deseja editar:",
            color=Colors.INFO
        )
        
        view = View(timeout=60)
        view.parent_view = self
        select = ItemSelectForEdit(self.guild, items, "edit")
        select.view = view
        view.add_item(select)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="Remover Item", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        items = get_shop_items(self.guild.id)
        
        if not items:
            embed = discord.Embed(
                description="📭 não há itens para remover",
                color=Colors.WARNING
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        embed = discord.Embed(
            title="🗑️ Remover Item",
            description="Selecione o item que deseja **remover**:",
            color=Colors.WARNING
        )
        
        view = View(timeout=60)
        view.parent_view = self
        select = ItemSelectForEdit(self.guild, items, "remove")
        select.view = view
        view.add_item(select)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="Abrir/Fechar", style=discord.ButtonStyle.secondary, emoji="🔒", row=1)
    async def toggle_button(self, interaction: discord.Interaction, button: Button):
        config = get_shop_config(self.guild.id)
        config['enabled'] = not config.get('enabled', True)
        save_shop_config(self.guild.id, config)
        
        status = "✅ aberta" if config['enabled'] else "❌ fechada"
        embed = discord.Embed(
            description=f"loja {status}",
            color=Colors.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        await self.refresh_embed(interaction)
    
    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.secondary, emoji="❌", row=1)
    async def close_button(self, interaction: discord.Interaction, button: Button):
        for child in self.children:
            child.disabled = True
        
        embed = self.get_config_embed()
        embed.set_footer(text="✅ Configuração finalizada")
        
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# ======================== COG ========================

class Shop(commands.Cog):
    """Sistema de loja admin-configurável"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_expired_roles.start()
        self.check_conditional_roles.start()
    
    async def cog_check(self, ctx: commands.Context) -> bool:
        """Check if economy feature is enabled for this guild"""
        if ctx.guild and not guild_repo.is_feature_enabled(ctx.guild.id, "economy"):
            await ctx.send(embed=embed_disabled("economia"), ephemeral=True)
            return False
        return True
    
    def cog_unload(self):
        self.check_expired_roles.cancel()
        self.check_conditional_roles.cancel()
    
    # -------------------- TASK: VERIFICAR CARGOS EXPIRADOS --------------------
    
    @tasks.loop(minutes=30)
    async def check_expired_roles(self):
        """Verifica e remove cargos temporários expirados"""
        for guild in self.bot.guilds:
            expired = get_expired_purchases(guild.id)
            
            for purchase in expired:
                try:
                    member = guild.get_member(purchase['user_id'])
                    if not member:
                        continue
                    
                    role = guild.get_role(purchase['role_id'])
                    if role and role in member.roles:
                        await member.remove_roles(role, reason="Cargo da loja expirado")
                except Exception:
                    continue
    
    @check_expired_roles.before_loop
    async def before_check_expired(self):
        await self.bot.wait_until_ready()
    
    # -------------------- TASK: VERIFICAR CARGOS CONDICIONAIS --------------------
    
    @tasks.loop(hours=1)
    async def check_conditional_roles(self):
        """Verifica cargos condicionais (streak, atividade)"""
        for guild in self.bot.guilds:
            purchases = shop_purchase_repo.find_all(guild_id=guild.id, duration_type=DURATION_CONDITIONAL)
            
            for purchase in purchases:
                condition = purchase.get('condition')
                user_id = purchase['user_id']
                role_id = purchase['role_id']
                
                member = guild.get_member(user_id)
                if not member:
                    continue
                
                role = guild.get_role(role_id)
                if not role or role not in member.roles:
                    continue
                
                should_remove = False
                
                if condition == 'streak':
                    user = user_repo.get_or_create_user(guild.id, user_id)
                    current_streak = user.get('daily_claim_streak', 0)
                    if current_streak == 0:
                        should_remove = True
                
                elif condition == 'activity':
                    user = user_repo.get_or_create_user(guild.id, user_id)
                    last_active = user.get('last_message_time')
                    if last_active:
                        try:
                            last_active = datetime.fromisoformat(last_active)
                            if datetime.now(timezone.utc) - last_active > timedelta(days=7):
                                should_remove = True
                        except:
                            pass
                
                if should_remove:
                    try:
                        await member.remove_roles(role, reason=f"Condição não mantida: {condition}")
                    except:
                        pass
                    shop_purchase_repo.delete(guild_id=guild.id, user_id=user_id, role_id=role_id)
    
    @check_conditional_roles.before_loop
    async def before_check_conditional(self):
        await self.bot.wait_until_ready()
    
    # -------------------- LOJA --------------------
    
    @commands.hybrid_command(
        name='loja',
        aliases=['shop', 'store'],
        description='Abre a loja do servidor'
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def shop_command(self, ctx: commands.Context):
        """Mostra a loja do servidor"""
        config = get_shop_config(ctx.guild.id)
        
        if not config.get('enabled', True):
            embed = discord.Embed(
                description="loja fechada neste servidor",
                color=Colors.INFO
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        items = get_shop_items(ctx.guild.id)
        
        # Filtrar itens com cargos válidos
        valid_items = {}
        for item_id, item in items.items():
            role = ctx.guild.get_role(item['role_id'])
            if role:
                valid_items[item_id] = item
        
        if not valid_items:
            embed = discord.Embed(
                title=f"{mora_emoji()} Loja",
                description="loja vazia\n\nadmins: `/lojaconfig`",
                color=Colors.INFO
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        user_mora = get_mora(ctx.guild.id, ctx.author.id)
        
        embed = discord.Embed(
            title=f"{mora_emoji()} Loja",
            description=f"saldo: **{format_number(user_mora)}**",
            color=Colors.PRIMARY
        )
        
        # Listar itens
        lines = []
        for item_id, item in valid_items.items():
            role = ctx.guild.get_role(item['role_id'])
            name = item.get('name') or role.name
            duration_text = format_duration_short(item)
            lines.append(f"**{name}** — {format_number(item['price'])} ({duration_text})")
        
        embed.add_field(
            name="Cargos",
            value="\n".join(lines[:10]),
            inline=False
        )
        
        view = ShopView(ctx.guild, valid_items)
        await ctx.reply(embed=embed, view=view, mention_author=False)
    
    # -------------------- COMPRAS --------------------
    
    @commands.hybrid_command(
        name='compras',
        aliases=['purchases', 'minhascompras', 'mypurchases'],
        description='Mostra seus cargos comprados ativos'
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def compras_command(self, ctx: commands.Context):
        """Mostra cargos comprados ativos"""
        purchases = get_user_purchases(ctx.guild.id, ctx.author.id)
        
        if not purchases:
            embed = discord.Embed(
                description="você não tem cargos comprados ativos",
                color=Colors.INFO
            )
            return await ctx.reply(embed=embed, mention_author=False)
        
        embed = discord.Embed(
            title="🛒 Compras",
            color=Colors.PRIMARY
        )
        
        lines = []
        now = datetime.now(timezone.utc)
        
        for purchase in purchases:
            role = ctx.guild.get_role(purchase['role_id'])
            if not role:
                continue
            
            duration_type = purchase.get('duration_type', DURATION_TEMPORARY)
            
            if duration_type == DURATION_PERMANENT:
                time_text = "permanente"
            elif duration_type == DURATION_CONDITIONAL:
                condition = purchase.get('condition', 'streak')
                conditions = {
                    'streak': 'enquanto tiver streak',
                    'activity': 'enquanto ativo'
                }
                time_text = conditions.get(condition, condition)
            else:
                expires_at = purchase.get('expires_at')
                if expires_at:
                    expires_at = datetime.fromisoformat(expires_at)
                    remaining = expires_at - now
                    
                    if remaining.days > 0:
                        time_text = f"{remaining.days}d restantes"
                    elif remaining.seconds > 3600:
                        time_text = f"{remaining.seconds // 3600}h restantes"
                    else:
                        time_text = f"{remaining.seconds // 60}min restantes"
                else:
                    time_text = "?"
            
            lines.append(f"**{role.name}** — {time_text}")
        
        if lines:
            embed.description = "\n".join(lines)
        else:
            embed.description = "nenhum cargo ativo"
        
        await ctx.reply(embed=embed, mention_author=False)
    
    # -------------------- ADMIN: CONFIG LOJA --------------------
    
    @commands.hybrid_command(
        name='configloja',
        aliases=['shopconfig', 'lojaconfig'],
        description='Painel de configuração da loja do servidor'
    )
    @commands.has_permissions(administrator=True)
    async def shop_config_command(self, ctx: commands.Context):
        """Abre painel de configuração da loja (admin)"""
        view = ShopConfigView(ctx.guild, ctx.author.id)
        embed = view.get_config_embed()
        
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Shop(bot))
