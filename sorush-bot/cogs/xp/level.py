"""
XP and Level System
Manages experience, ranking and roles by level
"""
from datetime import datetime
from typing import Optional, List, Tuple
import logging

import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput

from services.repositories import user_repo, xp_role_repo, guild_repo
from config import Colors
from services.xp.utils import (
    create_progress_bar, calculate_level, format_xp,
    RANK_EMOJIS
)

logger = logging.getLogger(__name__)


# ======================== VIEWS ========================

class LeaderboardView(View):
    """View for ranking pagination"""
    
    def __init__(self, cog: 'XP', guild_id: int, user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.page = 0
        self.per_page = 10
        self._leaderboard_cache: List[Tuple[int, int]] = []
        self._cache_loaded = False
    
    def _load_leaderboard(self):
        """Load the complete leaderboard (max 50 users)"""
        if not self._cache_loaded:
            self._leaderboard_cache = user_repo.get_leaderboard_values(self.guild_id, "xp", limit=50)
            self._cache_loaded = True
    
    def _get_page_data(self) -> List[Tuple[int, int]]:
        """Return data for current page"""
        self._load_leaderboard()
        start = self.page * self.per_page
        end = start + self.per_page
        return self._leaderboard_cache[start:end]
    
    def _get_total_pages(self) -> int:
        """Return total number of pages"""
        self._load_leaderboard()
        total = len(self._leaderboard_cache)
        return max(1, (total + self.per_page - 1) // self.per_page)
    
    async def get_embed(self) -> discord.Embed:
        """Generate ranking embed for current page"""
        page_data = self._get_page_data()
        total_pages = self._get_total_pages()
        
        if not page_data:
            return discord.Embed(title="🏆 Ranking XP", description="Nenhum usuário encontrado", color=Colors.WARNING)
        
        embed = discord.Embed(title="🏆 Ranking XP", color=Colors.XP)
        
        # Build ranking list
        ranking_text = ""
        offset = self.page * self.per_page
        
        for i, (uid, xp_val) in enumerate(page_data):
            position = offset + i + 1
            
            # Emoji based on position
            if position <= 10:
                emoji = RANK_EMOJIS[position - 1]
            else:
                emoji = f"`#{position}`"
            
            # Calculate level
            level, _, _ = calculate_level(xp_val)
            
            # Highlight if it's the requesting user
            if uid == self.user_id:
                ranking_text += f"**{emoji} <@{uid}> — Lv.{level} • `{format_xp(xp_val)} XP`** ⬅️\n"
            else:
                ranking_text += f"{emoji} <@{uid}> — Lv.{level} • `{format_xp(xp_val)} XP`\n"
        
        embed.description = ranking_text
        
        # Footer with page
        embed.set_footer(
            text=f"Página {self.page + 1}/{total_pages} • {len(self._leaderboard_cache)} usuários no ranking"
        )
        
        return embed
    
    def _update_buttons(self):
        """Update button states"""
        total_pages = self._get_total_pages()
        self.previous_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= total_pages - 1
    
    @discord.ui.button(label="◀️ Anterior", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Apenas quem usou o comando pode navegar!", ephemeral=True)
        
        if self.page > 0:
            self.page -= 1
        self._update_buttons()
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Próximo ▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Apenas quem usou o comando pode navegar!", ephemeral=True)
        
        total_pages = self._get_total_pages()
        if self.page < total_pages - 1:
            self.page += 1
        self._update_buttons()
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)


# ======================== XP CONFIG MODALS ========================

class XPAmountModal(Modal, title="⚙️ Configurar XP por Ação"):
    """Modal para configurar XP por mensagem e voz"""
    
    message_xp = TextInput(
        label="XP por Mensagem",
        placeholder="Ex: 1 (use 0 para desativar)",
        required=True,
        max_length=5,
        default="1"
    )
    
    voice_xp = TextInput(
        label="XP por Minuto em Voice",
        placeholder="Ex: 2 (use 0 para desativar)",
        required=True,
        max_length=5,
        default="2"
    )
    
    def __init__(self, cog: 'XP', guild_id: int, current_msg: int = 1, current_voice: int = 2):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.message_xp.default = str(max(0, current_msg))
        self.voice_xp.default = str(max(0, current_voice))
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            msg_val = int(self.message_xp.value)
            voice_val = int(self.voice_xp.value)
            
            if msg_val < 0 or voice_val < 0:
                await interaction.response.send_message(
                    "❌ Os valores não podem ser negativos!", 
                    ephemeral=True
                )
                return
            
            self.cog.set_xp_config(self.guild_id, msg_val, voice_val)
            
            embed = discord.Embed(title="⚙️ XP Config", color=Colors.SUCCESS)
            embed.add_field(name="Mensagem", value=f"```{msg_val} XP```", inline=True)
            embed.add_field(name="Voice", value=f"```{voice_val} XP/min```", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Digite apenas números válidos!", 
                ephemeral=True
            )


class AddXPRoleModal(Modal, title="🎭 Adicionar Cargo por XP"):
    """Modal para adicionar cargo de XP"""
    
    role_id = TextInput(
        label="ID do Cargo",
        placeholder="Ex: 1234567890123456789",
        required=True,
        max_length=20
    )
    
    xp_required = TextInput(
        label="XP Necessário",
        placeholder="Ex: 1000",
        required=True,
        max_length=10
    )
    
    def __init__(self, cog: 'XP', guild: discord.Guild):
        super().__init__()
        self.cog = cog
        self.guild = guild
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_id.value)
            xp_val = int(self.xp_required.value)
            
            if xp_val < 1:
                await interaction.response.send_message(
                    "❌ O XP necessário deve ser maior que 0!", 
                    ephemeral=True
                )
                return
            
            role = self.guild.get_role(role_id)
            if not role:
                await interaction.response.send_message(
                    "❌ Cargo não encontrado! Verifique o ID.", 
                    ephemeral=True
                )
                return
            
            if role.position >= self.guild.me.top_role.position:
                await interaction.response.send_message(
                    f"❌ O cargo {role.mention} está acima do meu cargo!", 
                    ephemeral=True
                )
                return
            
            # Save the role config
            self.cog.set_role(self.guild.id, role.id, xp_val)
            
            # Send initial response
            embed = discord.Embed(
                title="⏳ Cargo de XP Adicionado",
                description=f"{role.mention} será dado ao atingir **{xp_val:,} XP**\n\n🔄 Verificando usuários elegíveis...",
                color=Colors.INFO
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Assign role to eligible users
            success, failed = await self.cog.assign_role_to_eligible_users(self.guild, role, xp_val)
            
            # Update with results
            embed = discord.Embed(
                title="✅ Cargo de XP Configurado",
                description=f"{role.mention} — **{xp_val:,} XP**",
                color=Colors.SUCCESS
            )
            
            if success > 0 or failed > 0:
                result_text = f"✅ `{success}` usuários receberam o cargo"
                if failed > 0:
                    result_text += f"\n❌ `{failed}` falharam (permissões)"
                embed.add_field(
                    name="📊 Atribuição Retroativa",
                    value=result_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="📊 Atribuição Retroativa",
                    value="Nenhum usuário elegível encontrado",
                    inline=False
                )
            
            await interaction.edit_original_response(embed=embed)
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Digite apenas números válidos!", 
                ephemeral=True
            )


class ResetUserXPModal(Modal, title="🗑️ Resetar XP de Usuários"):
    """Modal para resetar XP de usuários"""
    
    user_ids = TextInput(
        label="IDs dos Usuários (separados por vírgula)",
        placeholder="Ex: 123456789, 987654321 ou 'all' para todos",
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph
    )
    
    def __init__(self, cog: 'XP', guild: discord.Guild):
        super().__init__()
        self.cog = cog
        self.guild = guild
    
    async def on_submit(self, interaction: discord.Interaction):
        input_value = self.user_ids.value.strip().lower()
        
        if input_value == "all":
            # Reset all users - show confirmation first
            confirm_view = ResetAllXPConfirmView(self.cog, self.guild, interaction.user.id)
            embed = discord.Embed(
                title="⚠️ Confirmar Reset de TODOS os XP",
                description=(
                    "**ATENÇÃO:** Isso irá zerar o XP de **TODOS** os usuários do servidor!\n\n"
                    "Esta ação **NÃO PODE SER DESFEITA**.\n\n"
                    "Tem certeza?"
                ),
                color=Colors.WARNING
            )
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
            return
        
        # Parse individual user IDs
        try:
            user_ids = [int(uid.strip()) for uid in input_value.split(",") if uid.strip().isdigit()]
        except ValueError:
            await interaction.response.send_message(
                "❌ IDs inválidos! Use números separados por vírgula.",
                ephemeral=True
            )
            return
        
        if not user_ids:
            await interaction.response.send_message(
                "❌ Nenhum ID válido fornecido!",
                ephemeral=True
            )
            return
        
        # Reset XP for specific users and remove XP roles
        success_count = 0
        roles_removed = 0
        xp_roles = self.cog.get_roles(self.guild.id)
        xp_role_ids = [int(rid) for rid in xp_roles.keys()] if xp_roles else []
        
        for user_id in user_ids:
            try:
                user_repo.update_user(self.guild.id, user_id, xp=0, xp_from_messages=0, xp_from_voice=0, xp_from_reactions=0)
                success_count += 1
                
                # Remove XP roles from user
                member = self.guild.get_member(user_id)
                if member and xp_role_ids:
                    roles_to_remove = [self.guild.get_role(rid) for rid in xp_role_ids]
                    roles_to_remove = [r for r in roles_to_remove if r and r in member.roles]
                    if roles_to_remove:
                        try:
                            await member.remove_roles(*roles_to_remove, reason="XP Resetado")
                            roles_removed += len(roles_to_remove)
                        except Exception:
                            pass
            except Exception:
                pass
        
        embed = discord.Embed(
            title="✅ XP Resetado",
            description=f"O XP de **{success_count}** usuário(s) foi zerado.",
            color=Colors.SUCCESS
        )
        
        if roles_removed > 0:
            embed.add_field(
                name="🎭 Cargos Removidos",
                value=f"`{roles_removed}` cargo(s) de XP foram removidos.",
                inline=False
            )
        
        if success_count < len(user_ids):
            embed.add_field(
                name="⚠️ Aviso",
                value=f"`{len(user_ids) - success_count}` usuário(s) não foram encontrados ou falharam.",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ResetAllXPConfirmView(View):
    """View para confirmar reset de todo XP"""
    
    def __init__(self, cog: 'XP', guild: discord.Guild, user_id: int):
        super().__init__(timeout=30)
        self.cog = cog
        self.guild = guild
        self.user_id = user_id
    
    @discord.ui.button(label="⚠️ SIM, RESETAR TUDO", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return
        
        # Get XP roles to remove
        xp_roles = self.cog.get_roles(self.guild.id)
        xp_role_ids = [int(rid) for rid in xp_roles.keys()] if xp_roles else []
        
        # Get all users and reset their XP
        leaderboard = user_repo.get_leaderboard_values(self.guild.id, "xp", limit=10000)
        count = 0
        roles_removed = 0
        
        for user_id, _ in leaderboard:
            try:
                user_repo.update_user(self.guild.id, user_id, xp=0, xp_from_messages=0, xp_from_voice=0, xp_from_reactions=0)
                count += 1
                
                # Remove XP roles from user
                member = self.guild.get_member(user_id)
                if member and xp_role_ids:
                    roles_to_remove = [self.guild.get_role(rid) for rid in xp_role_ids]
                    roles_to_remove = [r for r in roles_to_remove if r and r in member.roles]
                    if roles_to_remove:
                        try:
                            await member.remove_roles(*roles_to_remove, reason="XP Resetado - Reset Total")
                            roles_removed += len(roles_to_remove)
                        except Exception:
                            pass
            except Exception:
                pass
        
        embed = discord.Embed(title="✅ XP Resetado", color=Colors.SUCCESS)
        embed.add_field(name="Usuários", value=f"```{count}```", inline=True)
        
        if roles_removed > 0:
            embed.add_field(name="Cargos", value=f"```{roles_removed}```", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=None)
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return
        
        embed = discord.Embed(title="❌ Cancelado", description="Reset cancelado", color=Colors.INFO)
        await interaction.response.edit_message(embed=embed, view=None)


# ======================== XP CONFIG VIEWS ========================

class XPConfigTabSelect(Select):
    """Select menu para navegar entre as abas de configuração"""
    
    def __init__(self):
        options = [
            discord.SelectOption(
                label="XP por Ação",
                description="Configure quanto XP ganha por mensagem e voz",
                emoji="⚡",
                value="xp_amounts"
            ),
            discord.SelectOption(
                label="Cargos por XP",
                description="Configure cargos automáticos por XP",
                emoji="🎭",
                value="xp_roles"
            ),
            discord.SelectOption(
                label="Mensagens",
                description="Configure mensagens de level up",
                emoji="💬",
                value="messages"
            ),
            discord.SelectOption(
                label="Gerenciamento Geral",
                description="Visualize e gerencie todas as configurações",
                emoji="⚙️",
                value="general"
            )
        ]
        super().__init__(
            placeholder="📋 Selecione uma aba...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: XPConfigView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode navegar!", 
                ephemeral=True
            )
        
        view.current_tab = self.values[0]
        embed = view.get_tab_embed()
        view.update_buttons()
        await interaction.response.edit_message(embed=embed, view=view)


class RemoveRoleSelect(Select):
    """Select menu para remover cargos de XP"""
    
    def __init__(self, cog: 'XP', guild: discord.Guild):
        self.cog = cog
        self.guild = guild
        
        roles = cog.get_roles(guild.id)
        options = []
        
        if roles:
            roles_sorted = sorted(roles.items(), key=lambda x: int(x[1]))
            for rid, xp_req in roles_sorted[:25]:  # Max 25 options
                role = guild.get_role(int(rid))
                if role:
                    options.append(discord.SelectOption(
                        label=role.name[:100],
                        description=f"{int(xp_req):,} XP necessário",
                        value=str(rid),
                        emoji="🎭"
                    ))
        
        if not options:
            options.append(discord.SelectOption(
                label="Nenhum cargo configurado",
                value="none",
                emoji="❌"
            ))
        
        super().__init__(
            placeholder="🗑️ Selecione um cargo para remover...",
            options=options,
            min_values=1,
            max_values=1,
            disabled=len(roles) == 0
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: XPConfigView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode navegar!", 
                ephemeral=True
            )
        
        if self.values[0] == "none":
            return await interaction.response.send_message(
                "❌ Não há cargos para remover!", 
                ephemeral=True
            )
        
        role_id = int(self.values[0])
        role = self.guild.get_role(role_id)
        
        if self.cog.remove_role(self.guild.id, role_id):
            embed = discord.Embed(
                title="✅ Cargo Removido",
                description=f"O cargo {role.mention if role else f'ID:{role_id}'} foi removido do sistema de XP.",
                color=Colors.SUCCESS
            )
        else:
            embed = discord.Embed(
                title="❌ Erro",
                description="Não foi possível remover o cargo.",
                color=Colors.ERROR
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Refresh view
        view.refresh_role_select()
        embed = view.get_tab_embed()
        await interaction.message.edit(embed=embed, view=view)


class XPConfigView(View):
    """View principal para configuração de XP com abas"""
    
    def __init__(self, cog: 'XP', guild: discord.Guild, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user_id = user_id
        self.current_tab = "xp_amounts"
        
        # Add tab selector
        self.tab_select = XPConfigTabSelect()
        self.add_item(self.tab_select)
        
        # Role removal select (initially hidden)
        self.role_select: Optional[RemoveRoleSelect] = None
        
        self.update_buttons()
    
    def refresh_role_select(self):
        """Refresh the role select options"""
        if self.role_select:
            self.remove_item(self.role_select)
        
        if self.current_tab == "xp_roles":
            self.role_select = RemoveRoleSelect(self.cog, self.guild)
            self.add_item(self.role_select)
    
    def update_buttons(self):
        """Update buttons based on current tab"""
        # Remove all buttons except select menus
        items_to_remove = [item for item in self.children if isinstance(item, Button)]
        for item in items_to_remove:
            self.remove_item(item)
        
        # Remove role select if not on roles tab
        if self.role_select and self.current_tab != "xp_roles":
            self.remove_item(self.role_select)
            self.role_select = None
        
        if self.current_tab == "xp_amounts":
            self.add_item(self.edit_xp_button)
        elif self.current_tab == "xp_roles":
            self.add_item(self.add_role_button)
            self.refresh_role_select()
        elif self.current_tab == "messages":
            self.add_item(self.toggle_levelup_msg_button)
            self.add_item(self.set_levelup_channel_button)
        elif self.current_tab == "general":
            self.add_item(self.toggle_system_button)
            self.add_item(self.toggle_accumulate_button)
            self.add_item(self.reset_user_xp_button)
            self.add_item(self.reset_button)
    
    def get_tab_embed(self) -> discord.Embed:
        """Generate embed for current tab"""
        if self.current_tab == "xp_amounts":
            return self._get_xp_amounts_embed()
        elif self.current_tab == "xp_roles":
            return self._get_xp_roles_embed()
        elif self.current_tab == "messages":
            return self._get_messages_embed()
        else:
            return self._get_general_embed()
    
    def _get_xp_amounts_embed(self) -> discord.Embed:
        """Embed para aba de XP por ação"""
        cfg = self.cog.get_xp_config(self.guild.id)
        
        embed = discord.Embed(
            title="⚡ Configuração de XP por Ação",
            description="Configure quanto XP os membros ganham por cada ação.",
            color=Colors.XP,
            timestamp=datetime.now()
        )
        
        # Message XP
        if cfg["enabled"] and cfg["message"] > 0:
            msg_value = f"**{cfg['message']} XP** por mensagem"
            msgs_for_10k = 10000 // cfg['message']
            msg_estimate = f"~{msgs_for_10k:,} mensagens para 10.000 XP"
        elif cfg["enabled"] and cfg["message"] == 0:
            msg_value = "❌ **Desativado**"
            msg_estimate = "Mensagens não dão XP"
        else:
            msg_value = "⚠️ **Não configurado**"
            msg_estimate = "Configure para ativar"
        
        embed.add_field(
            name="💬 XP por Mensagem",
            value=f"{msg_value}\n└ {msg_estimate}",
            inline=False
        )
        
        # Voice XP
        if cfg["enabled"] and cfg["voice"] > 0:
            voice_value = f"**{cfg['voice']} XP** por minuto"
            mins_for_10k = 10000 // cfg['voice']
            hours = mins_for_10k // 60
            mins = mins_for_10k % 60
            voice_estimate = f"~{hours}h {mins}min para 10.000 XP"
        elif cfg["enabled"] and cfg["voice"] == 0:
            voice_value = "❌ **Desativado**"
            voice_estimate = "Voice não dá XP"
        else:
            voice_value = "⚠️ **Não configurado**"
            voice_estimate = "Configure para ativar"
        
        embed.add_field(
            name="🎤 XP por Voice",
            value=f"{voice_value}\n└ {voice_estimate}",
            inline=False
        )
        
        # Recommendations
        embed.add_field(
            name="💡 Valores Recomendados",
            value=(
                "```\n"
                "Casual:      MSG: 3  |  VOZ: 1\n"
                "Balanceado:  MSG: 2  |  VOZ: 2\n"
                "Competitivo: MSG: 1  |  VOZ: 3\n"
                "```"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use o botão abaixo para editar os valores")
        
        return embed
    
    def _get_xp_roles_embed(self) -> discord.Embed:
        """Embed para aba de cargos por XP"""
        roles = self.cog.get_roles(self.guild.id)
        
        embed = discord.Embed(
            title="🎭 Cargos por XP",
            description="Configure cargos que são dados automaticamente ao atingir certa quantidade de XP.",
            color=Colors.XP,
            timestamp=datetime.now()
        )
        
        if roles:
            roles_sorted = sorted(roles.items(), key=lambda x: int(x[1]))
            roles_text = ""
            
            for i, (rid, xp_req) in enumerate(roles_sorted, 1):
                role = self.guild.get_role(int(rid))
                if role:
                    level, _, _ = calculate_level(int(xp_req))
                    roles_text += f"`{i}.` {role.mention} — **{int(xp_req):,} XP** (~Lv.{level})\n"
            
            if roles_text:
                embed.add_field(
                    name=f"📋 Cargos Configurados ({len(roles_sorted)})",
                    value=roles_text[:1024],
                    inline=False
                )
            else:
                embed.add_field(
                    name="📋 Cargos Configurados",
                    value="*Nenhum cargo válido encontrado*",
                    inline=False
                )
        else:
            embed.add_field(
                name="📋 Cargos Configurados",
                value="*Nenhum cargo configurado*\n\nUse o botão **➕ Adicionar Cargo** para configurar!",
                inline=False
            )
        
        embed.add_field(
            name="ℹ️ Como Funciona",
            value=(
                "• Os membros recebem o cargo automaticamente ao atingir o XP\n"
                "• Configure se cargos acumulam na aba **Gerenciamento Geral**\n"
                "• Para adicionar, você precisa do **ID do cargo**\n"
                "• Clique com botão direito no cargo → Copiar ID"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use os botões e menu abaixo para gerenciar")
        
        return embed
    
    def _get_general_embed(self) -> discord.Embed:
        """Embed para aba de gerenciamento geral"""
        cfg = self.cog.get_xp_config(self.guild.id)
        roles = self.cog.get_roles(self.guild.id)
        
        embed = discord.Embed(
            title="⚙️ Gerenciamento Geral",
            description="Visão geral e ações de gerenciamento do sistema de XP.",
            color=Colors.XP,
            timestamp=datetime.now()
        )
        
        # System status
        if cfg["enabled"]:
            status = "🟢 **ATIVO**"
            xp_sources = []
            if cfg["message"] > 0:
                xp_sources.append(f"💬 `{cfg['message']}` XP/msg")
            if cfg["voice"] > 0:
                xp_sources.append(f"🎤 `{cfg['voice']}` XP/min")
            sources_text = " • ".join(xp_sources) if xp_sources else "Nenhuma fonte ativa"
        else:
            status = "🔴 **INATIVO**"
            sources_text = "Sistema não configurado"
        
        embed.add_field(
            name="📊 Status do Sistema",
            value=f"{status}\n{sources_text}",
            inline=False
        )
        
        # Accumulate roles option
        accumulate = cfg.get("accumulate_roles", True)
        accumulate_status = "🟢 **LIGADO**" if accumulate else "🔴 **DESLIGADO**"
        accumulate_desc = (
            "Usuários mantêm todos os cargos de níveis anteriores"
            if accumulate else
            "Usuários têm apenas o cargo do nível mais alto"
        )
        
        embed.add_field(
            name="📚 Acumular Cargos",
            value=f"{accumulate_status}\n└ {accumulate_desc}",
            inline=False
        )
        
        # Roles summary
        if roles:
            valid_roles = [self.guild.get_role(int(rid)) for rid in roles if self.guild.get_role(int(rid))]
            embed.add_field(
                name="🎭 Cargos Configurados",
                value=f"`{len(valid_roles)}` cargos ativos",
                inline=True
            )
            
            # XP range
            xp_values = [int(v) for v in roles.values()]
            min_xp = min(xp_values)
            max_xp = max(xp_values)
            embed.add_field(
                name="💎 Faixa de XP",
                value=f"`{min_xp:,}` - `{max_xp:,}` XP",
                inline=True
            )
        else:
            embed.add_field(
                name="🎭 Cargos Configurados",
                value="`0` cargos",
                inline=True
            )
        
        # Stats from database
        try:
            leaderboard = user_repo.get_leaderboard_values(self.guild.id, "xp", limit=100)
            total_users = len(leaderboard)
            total_xp = sum(xp for _, xp in leaderboard)
            
            embed.add_field(
                name="📈 Estatísticas",
                value=f"👥 `{total_users}` usuários com XP\n💎 `{format_xp(total_xp)}` XP total no servidor",
                inline=False
            )
        except:
            pass
        
        # Actions zone
        embed.add_field(
            name="🔧 Ações Disponíveis",
            value=(
                "• **Ligar/Desligar**: Ativa ou pausa o sistema de XP\n"
                "• **Acumular Cargos**: Alterna se cargos são cumulativos\n"
                "• **Resetar XP**: Zera o XP de usuários específicos\n"
                "• **Resetar Config**: Remove todas as configurações"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use os botões abaixo para gerenciar")
        
        return embed
    
    def _get_messages_embed(self) -> discord.Embed:
        """Embed para aba de notificações de cargo"""
        cfg = self.cog.get_xp_config(self.guild.id)
        roles_config = self.cog.get_roles(self.guild.id)
        
        embed = discord.Embed(
            title="💬 Notificações de Cargo",
            description="Configure se e onde notificar quando um usuário **ganhar um cargo de XP**.",
            color=Colors.XP,
            timestamp=datetime.now()
        )
        
        # Check if there are any XP roles configured
        if not roles_config:
            embed.add_field(
                name="⚠️ Nenhum Cargo Configurado",
                value="Configure cargos de XP na aba **🎭 Cargos por XP** primeiro!",
                inline=False
            )
            embed.set_footer(text="Configure cargos para usar notificações")
            return embed
        
        # Notification enabled/disabled
        notify_enabled = cfg.get("levelup_message", True)
        notify_status = "🟢 **LIGADO**" if notify_enabled else "🔴 **DESLIGADO**"
        
        embed.add_field(
            name="📢 Notificação de Cargo",
            value=f"{notify_status}\n└ {'Usuários são notificados ao ganhar um cargo de XP' if notify_enabled else 'Sem notificação ao ganhar cargo'}",
            inline=False
        )
        
        # Channel configuration
        notify_channel_id = cfg.get("levelup_channel", None)
        if notify_channel_id:
            channel = self.guild.get_channel(int(notify_channel_id))
            if channel:
                channel_text = f"📍 **{channel.mention}**\n└ Notificações enviadas neste canal"
            else:
                channel_text = "⚠️ **Canal não encontrado**\n└ Configure um novo canal"
        else:
            channel_text = "📍 **Mesmo canal da mensagem**\n└ Responde onde o usuário mandou a última mensagem"
        
        embed.add_field(
            name="📌 Canal das Notificações",
            value=channel_text,
            inline=False
        )
        
        # List configured roles
        roles_list = []
        for role_id_str, xp_required in sorted(roles_config.items(), key=lambda x: int(x[1])):
            role = self.guild.get_role(int(role_id_str))
            if role:
                roles_list.append(f"• {role.mention} → **{int(xp_required):,} XP**")
        
        if roles_list:
            embed.add_field(
                name="🎭 Cargos que Serão Notificados",
                value="\n".join(roles_list[:10]) + ("\n..." if len(roles_list) > 10 else ""),
                inline=False
            )
        
        # Preview
        example_role = list(roles_config.keys())[0] if roles_config else None
        role_name = "Novato"
        if example_role:
            role = self.guild.get_role(int(example_role))
            if role:
                role_name = role.name
        
        embed.add_field(
            name="👀 Prévia da Mensagem",
            value=f"```\n🎉 Parabéns @Usuario! Você ganhou o cargo {role_name}!\n```",
            inline=False
        )
        
        embed.set_footer(text="Use os botões abaixo para configurar")
        
        return embed
    
    @discord.ui.button(label="✏️ Editar XP", style=discord.ButtonStyle.primary, row=2)
    async def edit_xp_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode editar!", 
                ephemeral=True
            )
        
        cfg = self.cog.get_xp_config(self.guild.id)
        modal = XPAmountModal(
            self.cog, 
            self.guild.id,
            cfg.get("message", 1),
            cfg.get("voice", 2)
        )
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="➕ Adicionar Cargo", style=discord.ButtonStyle.success, row=2)
    async def add_role_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode editar!", 
                ephemeral=True
            )
        
        modal = AddXPRoleModal(self.cog, self.guild)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔄 Ligar / Desligar", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_system_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode editar!", 
                ephemeral=True
            )
        
        cfg = self.cog.get_xp_config(self.guild.id)
        
        if cfg["enabled"]:
            # Disable
            guild_repo.set_xp_enabled(self.guild.id, False)
            
            embed = discord.Embed(
                title="🔴 Sistema XP Desativado",
                description="O sistema de XP foi pausado. Os dados foram preservados.",
                color=Colors.WARNING
            )
        else:
            # Enable with default values
            self.cog.set_xp_config(self.guild.id, 1, 2)
            
            embed = discord.Embed(
                title="🟢 Sistema XP Ativado",
                description="O sistema de XP foi ativado com valores padrão (1 XP/msg, 2 XP/min).",
                color=Colors.SUCCESS
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Refresh main embed
        main_embed = self.get_tab_embed()
        await interaction.message.edit(embed=main_embed, view=self)
    
    @discord.ui.button(label="🗑️ Resetar Config", style=discord.ButtonStyle.danger, row=3)
    async def reset_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode editar!", 
                ephemeral=True
            )
        
        # Show confirmation view
        confirm_view = ResetConfirmView(self.cog, self.guild, self.user_id, self)
        embed = discord.Embed(
            title="⚠️ Confirmar Reset",
            description=(
                "Tem certeza que deseja resetar as configurações?\n\n"
                "**Isso irá remover:**\n"
                "• Configurações de XP por ação\n"
                "• Todos os cargos por XP\n\n"
                "*Os dados de XP dos usuários NÃO serão afetados*"
            ),
            color=Colors.WARNING
        )
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)

    @discord.ui.button(label="📚 Acumular Cargos", style=discord.ButtonStyle.primary, row=2)
    async def toggle_accumulate_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode editar!", 
                ephemeral=True
            )
        
        cfg = self.cog.get_xp_config(self.guild.id)
        current = cfg.get("accumulate_roles", True)
        new_value = not current
        
        self.cog.set_accumulate_roles(self.guild.id, new_value)
        
        if new_value:
            embed = discord.Embed(
                title="📚 Acumular Cargos: LIGADO",
                description=(
                    "Os usuários agora **mantêm todos os cargos** de níveis anteriores.\n\n"
                    "Exemplo: Um usuário com cargo Lv.3 também terá os cargos Lv.1 e Lv.2."
                ),
                color=Colors.SUCCESS
            )
        else:
            embed = discord.Embed(
                title="📚 Acumular Cargos: DESLIGADO",
                description=(
                    "Os usuários agora têm **apenas o cargo do nível mais alto**.\n\n"
                    "Exemplo: Um usuário com cargo Lv.3 NÃO terá os cargos Lv.1 e Lv.2."
                ),
                color=Colors.WARNING
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Refresh main embed
        main_embed = self.get_tab_embed()
        await interaction.message.edit(embed=main_embed, view=self)

    @discord.ui.button(label="🗑️ Resetar XP", style=discord.ButtonStyle.danger, row=3)
    async def reset_user_xp_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode editar!", 
                ephemeral=True
            )
        
        modal = ResetUserXPModal(self.cog, self.guild)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🔔 Ligar/Desligar Notificação", style=discord.ButtonStyle.primary, row=3)
    async def toggle_levelup_msg_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode editar!", 
                ephemeral=True
            )
        
        cfg = self.cog.get_xp_config(self.guild.id)
        current = cfg.get("levelup_message", True)
        new_value = not current
        
        self.cog.set_levelup_message(self.guild.id, new_value)
        
        if new_value:
            embed = discord.Embed(
                title="🔔 Notificação de Cargo: LIGADO",
                description="Usuários serão notificados ao ganhar um cargo de XP.",
                color=Colors.SUCCESS
            )
        else:
            embed = discord.Embed(
                title="🔕 Notificação de Cargo: DESLIGADO",
                description="Usuários **não** serão notificados ao ganhar cargo.",
                color=Colors.WARNING
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Refresh main embed
        main_embed = self.get_tab_embed()
        await interaction.message.edit(embed=main_embed, view=self)

    @discord.ui.button(label="📌 Configurar Canal", style=discord.ButtonStyle.secondary, row=3)
    async def set_levelup_channel_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode editar!", 
                ephemeral=True
            )
        
        # Show channel select view
        channel_view = LevelUpChannelView(self.cog, self.guild, self.user_id, self)
        embed = discord.Embed(
            title="📌 Configurar Canal de Notificação",
            description=(
                "Escolha onde as notificações de cargo serão enviadas:\n\n"
                "• **Mesmo Canal**: Responde onde o usuário enviou a última mensagem\n"
                "• **Canal Específico**: Selecione um canal do dropdown"
            ),
            color=Colors.INFO
        )
        await interaction.response.send_message(embed=embed, view=channel_view, ephemeral=True)


class LevelUpChannelSelect(Select):
    """Select menu para escolher o canal de level up"""
    
    def __init__(self, cog: 'XP', guild: discord.Guild):
        self.cog = cog
        self.guild = guild
        
        options = [
            discord.SelectOption(
                label="Mesmo canal da mensagem",
                description="Responde onde o usuário mandou a última msg",
                value="same",
                emoji="💬"
            )
        ]
        
        # Add text channels
        for channel in guild.text_channels[:24]:  # Max 25 options
            options.append(discord.SelectOption(
                label=f"#{channel.name}"[:100],
                value=str(channel.id),
                emoji="📌"
            ))
        
        super().__init__(
            placeholder="📌 Selecione o canal...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        view: LevelUpChannelView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode editar!", 
                ephemeral=True
            )
        
        selected = self.values[0]
        
        if selected == "same":
            self.cog.set_levelup_channel(self.guild.id, None)
            embed = discord.Embed(
                title="✅ Canal Configurado",
                description="Mensagens de level up serão enviadas no **mesmo canal** da última mensagem.",
                color=Colors.SUCCESS
            )
        else:
            channel_id = int(selected)
            channel = self.guild.get_channel(channel_id)
            self.cog.set_levelup_channel(self.guild.id, channel_id)
            embed = discord.Embed(
                title="✅ Canal Configurado",
                description=f"Mensagens de level up serão enviadas em {channel.mention}.",
                color=Colors.SUCCESS
            )
        
        await interaction.response.edit_message(embed=embed, view=None)


class LevelUpChannelView(View):
    """View para selecionar canal de level up"""
    
    def __init__(self, cog: 'XP', guild: discord.Guild, user_id: int, parent_view: XPConfigView):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild = guild
        self.user_id = user_id
        self.parent_view = parent_view
        
        self.add_item(LevelUpChannelSelect(cog, guild))



class ResetConfirmView(View):
    """View para confirmar reset das configurações"""
    
    def __init__(self, cog: 'XP', guild: discord.Guild, user_id: int, parent_view: XPConfigView):
        super().__init__(timeout=30)
        self.cog = cog
        self.guild = guild
        self.user_id = user_id
        self.parent_view = parent_view
    
    @discord.ui.button(label="✅ Confirmar Reset", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return
        
        guild_id = self.guild.id
        
        # Reset XP config to defaults
        guild_repo.set_xp_enabled(guild_id, False)
        guild_repo.set_xp_config(guild_id, message_xp=-1, voice_xp=-1)
        
        # Remove role config
        xp_role_repo.clear_all_roles(guild_id)
        
        embed = discord.Embed(
            title="✅ Configurações Resetadas",
            description="Todas as configurações de XP foram removidas.",
            color=Colors.SUCCESS
        )
        
        await interaction.response.edit_message(embed=embed, view=None)
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return
        
        embed = discord.Embed(title="❌ Cancelado", description="Operação cancelada", color=Colors.INFO)
        await interaction.response.edit_message(embed=embed, view=None)


# ======================== XP COG ========================

class XP(commands.Cog):
    """⭐ Sistema de XP e Níveis"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_xp_config(self, guild_id: int) -> dict:
        """Get XP configuration for the server from DB"""
        return guild_repo.get_xp_config(guild_id)

    def set_xp_config(self, guild_id: int, message_xp: Optional[int] = None, voice_xp: Optional[int] = None):
        """Set XP configuration for the server via DB"""
        current = guild_repo.get_xp_config(guild_id)
        msg = message_xp if message_xp is not None else current["message"]
        voice = voice_xp if voice_xp is not None else current["voice"]
        guild_repo.set_xp_config(guild_id, message_xp=msg, voice_xp=voice)
        if msg >= 0:
            guild_repo.set_xp_enabled(guild_id, True)

    def set_accumulate_roles(self, guild_id: int, accumulate: bool):
        """Set whether roles should accumulate"""
        guild_repo.set_xp_accumulate_roles(guild_id, accumulate)

    def set_levelup_message(self, guild_id: int, enabled: bool):
        """Set whether level up messages are enabled"""
        guild_repo.set_xp_levelup_message(guild_id, enabled)
    
    def set_levelup_channel(self, guild_id: int, channel_id: int = None):
        """Set the channel for role notifications (None = same channel)"""
        guild_repo.set_xp_levelup_channel(guild_id, channel_id)

    async def assign_role_to_eligible_users(self, guild: discord.Guild, role: discord.Role, xp_required: int) -> Tuple[int, int]:
        """
        Assign a role to all users who have enough XP.
        Returns: (success_count, failed_count)
        """
        cfg = self.get_xp_config(guild.id)
        accumulate = cfg.get("accumulate_roles", True)
        roles_config = self.get_roles(guild.id)
        
        # Get all users with XP in this guild
        leaderboard = user_repo.get_leaderboard_values(guild.id, "xp", limit=1000)
        
        success_count = 0
        failed_count = 0
        
        for user_id, user_xp in leaderboard:
            if user_xp < xp_required:
                continue
            
            member = guild.get_member(user_id)
            if not member:
                continue
            
            # Check if user already has the role
            if role in member.roles:
                continue
            
            # If accumulate is OFF, check if user has a higher role
            if not accumulate:
                has_higher_role = False
                for rid, xp_req in roles_config.items():
                    if int(xp_req) > xp_required:
                        existing_role = guild.get_role(int(rid))
                        if existing_role and existing_role in member.roles:
                            has_higher_role = True
                            break
                
                if has_higher_role:
                    continue
            
            try:
                await member.add_roles(role, reason="XP Role - Cargo adicionado retroativamente")
                success_count += 1
            except discord.Forbidden:
                failed_count += 1
            except Exception:
                failed_count += 1
        
        return success_count, failed_count

    def get_roles(self, guild_id: int) -> dict:
        """Get XP roles for the server"""
        return xp_role_repo.get_roles_dict(guild_id)

    def set_role(self, guild_id: int, role_id: int, xp_needed: int):
        """Set role for an XP level"""
        xp_role_repo.add_role(guild_id, role_id, xp_needed)

    def remove_role(self, guild_id: int, role_id: int) -> bool:
        """Remove an XP role"""
        return xp_role_repo.remove_role(guild_id, role_id)

    def get_role_for_xp(self, guild_id: int, xp: int) -> Optional[int]:
        """Get the appropriate role for an XP value"""
        roles = self.get_roles(guild_id)
        if not roles:
            return None
        roles_sorted = sorted(roles.items(), key=lambda x: int(x[1]))
        role_id = None
        for rid, xp_needed in roles_sorted:
            if xp >= int(xp_needed):
                role_id = int(rid)
            else:
                break
        return role_id

    def _create_xp_embed(self, member: discord.Member, xp: int, guild: discord.Guild) -> discord.Embed:
        """Create detailed XP embed for user with extended stats"""
        level, xp_current, xp_needed = calculate_level(xp)
        progress = create_progress_bar(xp_current, xp_needed, 12)
        progress_percent = (xp_current / xp_needed * 100) if xp_needed > 0 else 0
        
        # Get full user data from database
        user_data = user_repo.get_user(guild.id, member.id) or {}
        
        # Find position in ranking using db directly
        position = user_repo.get_user_rank(guild.id, member.id, "xp")
        
        embed = discord.Embed(
            title="",
            description=" ",
            color=Colors.XP,
            timestamp=datetime.now()
        )
        
        embed.set_author(
            name=member.display_name,
            icon_url=member.display_avatar.url
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        
        embed.add_field(name="─────〔 Perfil XP 〕─────", value="", inline=False)
        
        # Level field with visual
        level_info = f"```{level}```"
        embed.add_field(name="Nível Atual", value=level_info, inline=True)
        
        # Total XP field
        xp_info = f"```{format_xp(xp)}```"
        embed.add_field(name="XP Total", value=xp_info, inline=True)
        
        # Ranking field
        if position:
            rank_emoji = RANK_EMOJIS[position - 1] if position <= 10 else f"#{position}"
            rank_info = f"```{rank_emoji}```"
        else:
            rank_info = "```-```"
        embed.add_field(name="Posição", value=rank_info, inline=True)
        
        # Progress bar
        embed.add_field(
            name=f"📊 Progresso para Nível {level + 1}",
            value=f"{progress} **{progress_percent:.1f}%**\n"
                  f"`{format_xp(xp_current)}` / `{format_xp(xp_needed)}` XP",
            inline=False
        )
        
        # XP Sources breakdown
        xp_from_messages = user_data.get('xp_from_messages', 0)
        xp_from_voice = user_data.get('xp_from_voice', 0)
        xp_from_reactions = user_data.get('xp_from_reactions', 0)
        
        if xp_from_messages > 0 or xp_from_voice > 0 or xp_from_reactions > 0:
            sources_text = ""
            if xp_from_messages > 0:
                pct = (xp_from_messages / xp * 100) if xp > 0 else 0
                sources_text += f"💬 Mensagens: `{format_xp(xp_from_messages)}` ({pct:.1f}%)\n"
            if xp_from_voice > 0:
                pct = (xp_from_voice / xp * 100) if xp > 0 else 0
                sources_text += f"🎤 Voz: `{format_xp(xp_from_voice)}` ({pct:.1f}%)\n"
            if xp_from_reactions > 0:
                pct = (xp_from_reactions / xp * 100) if xp > 0 else 0
                sources_text += f"❤️ Reações: `{format_xp(xp_from_reactions)}` ({pct:.1f}%)"
            
            embed.add_field(
                name="📈 Origem do XP",
                value=sources_text.strip(),
                inline=True
            )
        
        # Activity that earned XP
        messages = user_data.get('messages', 0)
        voice_mins = user_data.get('voice_mins', 0)
        reactions = user_data.get('reactions_given', 0)
        
        activity_text = ""
        if messages > 0:
            activity_text += f"💬 `{messages:,}` mensagens\n"
        if voice_mins > 0:
            hours = voice_mins / 60
            activity_text += f"🎤 `{hours:.1f}h` em voz\n"
        if reactions > 0:
            activity_text += f"❤️ `{reactions:,}` reações"
        
        if activity_text:
            embed.add_field(
                name="📊 Atividade Total",
                value=activity_text.strip(),
                inline=True
            )
        
        # Streak info
        daily_streak = user_data.get('daily_streak', 0)
        if daily_streak > 0:
            streak_visual = "🔥" * min(daily_streak, 5)
            embed.add_field(
                name="🔥 Streak",
                value=f"`{daily_streak}` dias {streak_visual}",
                inline=True
            )
        
        # Available XP roles
        roles = self.get_roles(guild.id)
        if roles:
            roles_sorted = sorted(roles.items(), key=lambda x: int(x[1]))
            roles_text = ""
            current_role = None
            next_role = None
            
            for rid, xp_required in roles_sorted:
                role = guild.get_role(int(rid))
                if role:
                    if xp >= int(xp_required):
                        current_role = role
                        roles_text += f"✅ {role.mention} — `{format_xp(int(xp_required))} XP`\n"
                    else:
                        if next_role is None:
                            next_role = (role, int(xp_required))
                        roles_text += f"🔒 {role.mention} — `{format_xp(int(xp_required))} XP`\n"
            
            if roles_text:
                embed.add_field(
                    name="🎭 Cargos por XP",
                    value=roles_text[:1024],
                    inline=False
                )
            
            if next_role:
                xp_missing = next_role[1] - xp
                embed.set_footer(
                    text=f"Faltam {format_xp(xp_missing)} XP para {next_role[0].name}"
                )
        else:
            embed.set_footer(text="Nenhum cargo de XP configurado neste servidor")
        
        # Add info about XP/Level ratio and max level
        # Calculate approximate max level (100 XP = ~1 level simplified)
        # Actual formula: XP = 100 * level^1.5, so max_level ≈ (xp/100)^(2/3)
        max_level_approx = int((xp / 100) ** (2/3)) if xp > 0 else 0
        
        info_text = (
            f"ℹ️ **Informação XP/Level:**\n"
            f"• A cada ~100 XP você ganha 1 nível\n"
            f"• Seu level máximo atual: **{max_level_approx}**"
        )
        embed.insert_field_at(2, name="ℹ️ Informações", value=info_text, inline=False)
        
        return embed

    @commands.hybrid_command(
        name="xp", 
        aliases=["level", "rank", "nivel"],
        description="⭐ Veja seu XP, nível e posição no ranking"
    )
    async def xp_command(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """
        Shows XP and ranking of a user
        
        Examples:
        - /xp - Shows your own XP
        - /xp @user - Shows another user's XP
        """
        target = member or ctx.author
        xp_cfg = self.get_xp_config(ctx.guild.id)
        
        if not xp_cfg["enabled"]:
            embed = discord.Embed(
                title="⚠️ Sistema XP Desativado",
                description=(
                    "O sistema de XP não foi configurado neste servidor.\n\n"
                    "**📋 Para ativar:**\n"
                    "Um **administrador** deve usar:\n"
                    "```\n/xpconfig message_xp:1 voice_xp:2\n```"
                ),
                color=Colors.WARNING
            )
            embed.add_field(
                name="💡 Valores Recomendados",
                value=(
                    "• **Casual:** `message:3` `voice:1`\n"
                    "• **Balanceado:** `message:2` `voice:2`\n"
                    "• **Competitivo:** `message:1` `voice:3`"
                ),
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        user_data = user_repo.get_or_create_user(ctx.guild.id, target.id)
        user_xp = user_data.get("xp", 0)
        
        embed = self._create_xp_embed(target, user_xp, ctx.guild)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="ranking",
        aliases=["leaderboard", "top"],
        description="🏆 Veja o ranking de XP do servidor"
    )
    async def ranking_command(self, ctx: commands.Context):
        """Shows the server's XP ranking with pagination"""
        xp_cfg = self.get_xp_config(ctx.guild.id)
        
        if not xp_cfg["enabled"]:
            embed = discord.Embed(
                title="⚠️ Sistema XP Desativado",
                description="Configure o sistema de XP primeiro com `/xpconfig`",
                color=Colors.WARNING
            )
            await ctx.send(embed=embed)
            return
        
        view = LeaderboardView(self, ctx.guild.id, ctx.author.id)
        embed = await view.get_embed()
        await ctx.send(embed=embed, view=view)

    @commands.has_permissions(administrator=True)
    @commands.hybrid_command(
        name="xprole", 
        aliases=["addxprole"],
        description="🎭 Adiciona cargo que será dado ao atingir certo XP"
    )
    async def xprole(self, ctx: commands.Context, role: discord.Role, xp_required: int):
        """
        Adds a role that will be given automatically when reaching the specified XP
        
        Example: /xprole @Veteran 1000
        """
        if xp_required < 1:
            embed = discord.Embed(
                title="❌ Valor Inválido",
                description="O XP necessário deve ser **maior que 0**.",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        if role.position >= ctx.guild.me.top_role.position:
            embed = discord.Embed(
                title="❌ Permissão Insuficiente",
                description=f"O cargo {role.mention} está acima do meu cargo!\n"
                           "Mova meu cargo para cima para poder dar este cargo.",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        self.set_role(ctx.guild.id, role.id, xp_required)
        
        embed = discord.Embed(
            title="✅ Cargo de XP Configurado",
            color=Colors.SUCCESS,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="🎭 Cargo",
            value=role.mention,
            inline=True
        )
        
        embed.add_field(
            name="💎 XP Necessário",
            value=f"`{xp_required:,}`",
            inline=True
        )
        
        # Show all configured roles
        roles = self.get_roles(ctx.guild.id)
        if roles:
            roles_sorted = sorted(roles.items(), key=lambda x: int(x[1]))
            roles_text = ""
            for rid, xp_req in roles_sorted:
                r = ctx.guild.get_role(int(rid))
                if r:
                    roles_text += f"{r.mention} — `{int(xp_req):,} XP`\n"
            
            if roles_text:
                embed.add_field(
                    name="📋 Todos os Cargos",
                    value=roles_text[:1024],
                    inline=False
                )
        
        await ctx.send(embed=embed)

    @commands.has_permissions(administrator=True)
    @commands.hybrid_command(
        name="removexprole",
        description="🗑️ Remove um cargo de XP"
    )
    async def removexprole(self, ctx: commands.Context, role: discord.Role):
        """Remove a role from the XP system"""
        if self.remove_role(ctx.guild.id, role.id):
            embed = discord.Embed(
                title="✅ Cargo Removido",
                description=f"O cargo {role.mention} foi removido do sistema de XP.",
                color=Colors.SUCCESS
            )
        else:
            embed = discord.Embed(
                title="❌ Cargo Não Encontrado",
                description=f"O cargo {role.mention} não estava configurado.",
                color=Colors.USER_ERROR
            )
        
        await ctx.send(embed=embed)

    @commands.has_permissions(administrator=True)
    @commands.hybrid_command(
        name="xpconfig", 
        aliases=["setxp", "configxp"],
        description="⚙️ Abre o painel de configuração do sistema de XP"
    )
    async def xpconfig(self, ctx: commands.Context):
        """
        Opens the interactive XP configuration panel with 3 tabs:
        - XP per action (message, voice)
        - Roles by XP
        - General management
        """
        view = XPConfigView(self, ctx.guild, ctx.author.id)
        embed = view.get_tab_embed()
        await ctx.send(embed=embed, view=view)

    @commands.has_permissions(administrator=True)
    @commands.hybrid_command(
        name="xpset",
        description="⚡ Define rapidamente XP por mensagem e voz"
    )
    async def xpset(self, ctx: commands.Context, message_xp: int, voice_xp: int):
        """
        Quickly set XP values without the interactive panel
        
        Examples:
        - /xpset 1 2 (1 XP per message, 2 XP per voice minute)
        - /xpset 0 2 (disable message XP, keep voice)
        """
        # Validations
        if message_xp < 0:
            embed = discord.Embed(
                title="❌ Valor Inválido",
                description="O XP de mensagem não pode ser negativo.\nUse `0` para desativar.",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        if voice_xp < 0:
            embed = discord.Embed(
                title="❌ Valor Inválido",
                description="O XP de voice não pode ser negativo.\nUse `0` para desativar.",
                color=Colors.USER_ERROR
            )
            await ctx.send(embed=embed, ephemeral=True)
            return
        
        # Apply configuration
        self.set_xp_config(ctx.guild.id, message_xp, voice_xp)
        
        embed = discord.Embed(
            title="✅ Configuração Atualizada",
            color=Colors.SUCCESS,
            timestamp=datetime.now()
        )
        
        # Message info
        if message_xp > 0:
            msgs_needed = 10000 // message_xp
            msg_info = f"💬 **{message_xp} XP** por mensagem\n└ ~{msgs_needed:,} mensagens para 10.000 XP"
        else:
            msg_info = "💬 XP por mensagem: **DESATIVADO**"
        
        # Voice info
        if voice_xp > 0:
            mins_needed = 10000 // voice_xp
            hours = mins_needed // 60
            remaining_mins = mins_needed % 60
            voice_info = f"🎤 **{voice_xp} XP** por minuto em voice\n└ ~{hours}h {remaining_mins}min para 10.000 XP"
        else:
            voice_info = "🎤 XP por voice: **DESATIVADO**"
        
        embed.description = f"{msg_info}\n\n{voice_info}"
        
        embed.add_field(
            name="📌 Próximo Passo",
            value="Use `/xpconfig` para acessar o painel completo de configuração!",
            inline=False
        )
        
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(XP(bot))