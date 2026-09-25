from __future__ import annotations

import discord
from discord import ui
from config.settings import BotEmojis
from core.utils.embed_builder import EmbedBuilder
from core.enums import AutoRoleMode
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.bot import LunaBot

def _can_manage_role(guild: discord.Guild, role: discord.Role) -> bool:
    return guild.me.top_role > role and not role.managed and role != guild.default_role

def _fmt_duration(seconds: int) -> str:
    if seconds < 60: return f"{seconds}s"
    if seconds < 3600: return f"{seconds // 60}min"
    hours, mins = divmod(seconds, 3600)
    mins //= 60
    return f"{hours}h {mins}min" if mins else f"{hours}h"

class InstantModal(ui.Modal, title="AutoRole — Instant"):
    role_id = ui.TextInput(label="ID do Cargo", placeholder="Ex: 1234...", required=True, max_length=20)
    async def on_submit(self, interaction: discord.Interaction) -> None:
        try: rid = int(self.role_id.value.strip())
        except: return await interaction.response.send_message("ID inválido.", ephemeral=True)
        role = interaction.guild.get_role(rid)
        if not role or not _can_manage_role(interaction.guild, role):
            return await interaction.response.send_message("Cargo inválido ou sem permissão.", ephemeral=True)
        ar_id = await interaction.client.autorole_service.create_autorole(interaction.guild.id, role.id, AutoRoleMode.INSTANT, interaction.user.id)
        await interaction.response.send_message(embed=EmbedBuilder.success(f"AutoRole criado! `#{ar_id}`").field("Cargo", role.mention).build())

class TimerModal(ui.Modal, title="AutoRole — Timer"):
    role_id = ui.TextInput(label="ID do Cargo", required=True, max_length=20)
    delay = ui.TextInput(label="Tempo (segundos)", placeholder="Ex: 300", required=True, max_length=7)
    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            rid = int(self.role_id.value.strip())
            seconds = int(self.delay.value.strip())
        except: return await interaction.response.send_message("Entrada inválida.", ephemeral=True)
        role = interaction.guild.get_role(rid)
        if not role or not _can_manage_role(interaction.guild, role):
            return await interaction.response.send_message("Cargo inválido.", ephemeral=True)
        ar_id = await interaction.client.autorole_service.create_autorole(interaction.guild.id, role.id, AutoRoleMode.TIMER, interaction.user.id, delay_seconds=seconds)
        await interaction.response.send_message(embed=EmbedBuilder.success(f"AutoRole criado! `#{ar_id}`").field("Cargo", role.mention).field("Delay", _fmt_duration(seconds)).build())

class ButtonModal(ui.Modal, title="AutoRole — Botão"):
    role_id = ui.TextInput(label="ID do Cargo", required=True)
    channel_id = ui.TextInput(label="ID do Canal", required=True)
    embed_title = ui.TextInput(label="Título", default="Pegue seu cargo!")
    embed_text = ui.TextInput(label="Texto", style=discord.TextStyle.paragraph, required=False)
    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            rid, cid = int(self.role_id.value.strip()), int(self.channel_id.value.strip())
        except: return await interaction.response.send_message("IDs inválidos.", ephemeral=True)
        role, channel = interaction.guild.get_role(rid), interaction.guild.get_channel(cid)
        if not role or not isinstance(channel, discord.TextChannel) or not _can_manage_role(interaction.guild, role):
            return await interaction.response.send_message("Configuração inválida.", ephemeral=True)
        svc = interaction.client.autorole_service
        ar_id = await svc.create_autorole(interaction.guild.id, role.id, AutoRoleMode.BUTTON, interaction.user.id, channel_id=channel.id, embed_title=self.embed_title.value, embed_text=self.embed_text.value)
        view = PersistentAutoRoleButton(interaction.client, ar_id, role.id)
        msg = await channel.send(embed=EmbedBuilder.default().title(self.embed_title.value).description(self.embed_text.value or f"Clique abaixo para {role.mention}").build(), view=view)
        await svc.update_message_id(ar_id, msg.id)
        await interaction.response.send_message(f"AutoRole `#{ar_id}` criado em {channel.mention}")

class ReactionModal(ui.Modal, title="AutoRole — Reação"):
    role_id = ui.TextInput(label="ID do Cargo", required=True)
    channel_id = ui.TextInput(label="ID do Canal", required=True)
    emoji = ui.TextInput(label="Emoji", default=BotEmojis.STATUS_ENABLED)
    embed_title = ui.TextInput(label="Título", default="Pegue seu cargo!")
    embed_text = ui.TextInput(label="Texto", style=discord.TextStyle.paragraph, required=False)
    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            rid, cid = int(self.role_id.value.strip()), int(self.channel_id.value.strip())
        except: return await interaction.response.send_message("IDs inválidos.", ephemeral=True)
        role, channel = interaction.guild.get_role(rid), interaction.guild.get_channel(cid)
        if not role or not isinstance(channel, discord.TextChannel) or not _can_manage_role(interaction.guild, role):
            return await interaction.response.send_message("Configuração inválida.", ephemeral=True)
        svc = interaction.client.autorole_service
        ar_id = await svc.create_autorole(interaction.guild.id, role.id, AutoRoleMode.REACTION, interaction.user.id, channel_id=channel.id, embed_title=self.embed_title.value, embed_text=self.embed_text.value, emoji=self.emoji.value)
        msg = await channel.send(embed=EmbedBuilder.default().title(self.embed_title.value).description(self.embed_text.value or f"Reaja para {role.mention}").build())
        try: await msg.add_reaction(self.emoji.value)
        except: pass
        await svc.update_message_id(ar_id, msg.id)
        await interaction.response.send_message(f"AutoRole `#{ar_id}` criado em {channel.mention}")

class ModeSelectView(ui.View):
    def __init__(self, admin_id: int) -> None:
        super().__init__(timeout=120)
        self.admin_id = admin_id
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.admin_id
    @ui.select(placeholder="Modo...", options=[
        discord.SelectOption(label="Instant", value="instant", emoji=BotEmojis.AUTOROLE_INSTANT),
        discord.SelectOption(label="Timer", value="timer", emoji=BotEmojis.AUTOROLE_TIMER),
        discord.SelectOption(label="Botão", value="button", emoji=BotEmojis.AUTOROLE_BUTTON),
        discord.SelectOption(label="Reação", value="reaction", emoji=BotEmojis.AUTOROLE_REACTION),
    ])
    async def mode_select(self, interaction: discord.Interaction, select: ui.Select) -> None:
        modals = {"instant": InstantModal, "timer": TimerModal, "button": ButtonModal, "reaction": ReactionModal}
        await interaction.response.send_modal(modals[select.values[0]]())

class AutoRoleManagerView(ui.View):
    def __init__(self, bot: LunaBot, guild_id: int, admin_id: int) -> None:
        super().__init__(timeout=180)
        self.bot, self.guild_id, self.admin_id = bot, guild_id, admin_id
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.admin_id
    @ui.button(label="Criar", style=discord.ButtonStyle.success, emoji=BotEmojis.ACTION_CREATE)
    async def create_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message(embed=EmbedBuilder.default().title("Novo AutoRole").description("Escolha o modo:").build(), view=ModeSelectView(self.admin_id), ephemeral=True)
    @ui.button(label="Atualizar", style=discord.ButtonStyle.secondary, emoji=BotEmojis.ACTION_REFRESH)
    async def refresh_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        from features.admin.cogs.autorole import _build_list_embed
        await interaction.response.edit_message(embed=await _build_list_embed(self.bot, interaction.guild), view=self)

class AutoRoleManageItemView(ui.View):
    def __init__(self, bot: LunaBot, entries: list[dict], admin_id: int) -> None:
        super().__init__(timeout=120)
        self.bot, self.admin_id = bot, admin_id
        options = [discord.SelectOption(label=f"#{e['id']} — {e['mode'].title()}", value=str(e['id']), description=f"Role: {e['role_id']}") for e in entries[:25]]
        self.manage_select.options = options
    @ui.select(placeholder="Gerenciar...")
    async def manage_select(self, interaction: discord.Interaction, select: ui.Select) -> None:
        ar_id = int(select.values[0])
        ar = await self.bot.autorole_repo.get_autorole(ar_id)
        if not ar: return await interaction.response.send_message("Não encontrado.", ephemeral=True)
        role = interaction.guild.get_role(ar['role_id'])
        embed = EmbedBuilder.default().section(f"AutoRole #{ar_id}").stat("Cargo", role.mention if role else ar['role_id']).stat("Modo", ar['mode']).stat("Status", "Ativo" if ar['enabled'] else "Inativo").build()
        await interaction.response.send_message(embed=embed, view=SingleAutoRoleView(self.bot, ar_id, self.admin_id), ephemeral=True)

class SingleAutoRoleView(ui.View):
    def __init__(self, bot: LunaBot, autorole_id: int, admin_id: int) -> None:
        super().__init__(timeout=60)
        self.bot, self.autorole_id, self.admin_id = bot, autorole_id, admin_id
    @ui.button(label="Toggle", style=discord.ButtonStyle.primary, emoji=BotEmojis.ACTION_TOGGLE)
    async def toggle_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        ar = await self.bot.autorole_repo.get_autorole(self.autorole_id)
        if ar:
            new_state = not ar['enabled']
            await self.bot.autorole_service.toggle_autorole(self.autorole_id, new_state)
            await interaction.response.send_message(f"AutoRole {'ativado' if new_state else 'desativado'}.", ephemeral=True)
    @ui.button(label="Remover", style=discord.ButtonStyle.danger, emoji=BotEmojis.ACTION_REMOVE)
    async def remove_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self.bot.autorole_service.delete_autorole(self.autorole_id)
        await interaction.response.send_message("Removido.", ephemeral=True)

class PersistentAutoRoleButton(ui.View):
    def __init__(self, bot: LunaBot, autorole_id: int, role_id: int) -> None:
        super().__init__(timeout=None)
        self.bot, self.autorole_id, self.role_id = bot, autorole_id, role_id
        btn = ui.Button(label="Pegar cargo", style=discord.ButtonStyle.primary, emoji=BotEmojis.AUTOROLE_PICK_ROLE, custom_id=f"autorole_button:{autorole_id}")
        btn.callback = self.take_role
        self.add_item(btn)
    async def take_role(self, interaction: discord.Interaction) -> None:
        role = interaction.guild.get_role(self.role_id)
        if not role: return await interaction.response.send_message("Cargo não encontrado.", ephemeral=True)
        member = interaction.user
        if role in member.roles:
            await member.remove_roles(role, reason="AutoRole")
            await interaction.response.send_message(f"Cargo {role.mention} removido.", ephemeral=True)
        else:
            await member.add_roles(role, reason="AutoRole")
            await self.bot.autorole_service.record_role_given(interaction.guild_id, member.id, role.id)
            await interaction.response.send_message(f"Cargo {role.mention} adicionado!", ephemeral=True)
