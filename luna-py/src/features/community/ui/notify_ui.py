from __future__ import annotations

import discord
from discord import ui
from config.settings import BotEmojis, Separators
from core.utils.embed_builder import EmbedBuilder
from features.community.utils.notify_utils import (
    _unix,
    _parse_scheduled_iso,
    _build_notification_manage_embed,
    _parse_optional_remind_minutes,
    _resolve_future_notify_datetime,
    _format_notification_time
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from features.community.cogs.notify import NotifyCog

class NotifyModal(ui.Modal, title="Nova Notificação"):
    """Modal para preencher data, hora, título e descrição."""

    notify_title = ui.TextInput(
        label="Título",
        placeholder="Ex: Reunião da equipe",
        max_length=100,
        required=True,
    )
    notify_date = ui.TextInput(
        label="Data (DD/MM) ou duração (1h, 30m, 2h30m)",
        placeholder="17/02  ou  1h30m",
        max_length=20,
        required=True,
    )
    notify_time = ui.TextInput(
        label="Hora (HH:MM) — Horário de Brasília (se data)",
        placeholder="14:30  (deixe vazio se usou duração)",
        max_length=5,
        required=False,
    )
    notify_description = ui.TextInput(
        label="Descrição (opcional)",
        placeholder="Detalhes sobre o evento...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )
    remind_minutes = ui.TextInput(
        label="Lembrar X minutos antes (0 = desligado)",
        placeholder="15",
        max_length=5,
        required=False,
        default="0",
    )

    def __init__(self, cog: NotifyCog, channel_id: int) -> None:
        super().__init__()
        self.cog = cog
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        date_input = self.notify_date.value.strip()
        time_input = (self.notify_time.value or "").strip()

        dt_brt = await _resolve_future_notify_datetime(
            interaction,
            date_input,
            time_input,
        )
        if dt_brt is None:
            return

        remind_before = _parse_optional_remind_minutes(self.remind_minutes.value)

        notif_id = await self.cog.bot.notification_service.create_notification(
            guild_id=interaction.guild.id,
            channel_id=self.channel_id,
            creator_id=interaction.user.id,
            title=self.notify_title.value.strip(),
            scheduled_at=dt_brt.isoformat(),
            description=self.notify_description.value.strip() or None,
            remind_before=remind_before,
        )

        embed = _build_notification_manage_embed(
            title=self.notify_title.value.strip(),
            description=self.notify_description.value.strip() or None,
            scheduled_at=dt_brt,
            remind_before=remind_before,
            notif_id=notif_id,
            user=interaction.user,
        )
        view = self.cog.build_manage_view(notif_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

class EditNotifyModal(ui.Modal, title="Editar Notificação"):
    """Modal para editar uma notificação existente."""

    title_input = ui.TextInput(
        label="Título",
        placeholder="Ex: Reunião da equipe",
        max_length=100,
        required=True,
    )
    date_input = ui.TextInput(
        label="Data (DD/MM/AAAA)",
        placeholder="Ex: 17/02/2026",
        max_length=10,
        required=True,
    )
    time_input = ui.TextInput(
        label="Hora (HH:MM) — Horário de Brasília",
        placeholder="Ex: 14:30",
        max_length=5,
        required=True,
    )
    description_input = ui.TextInput(
        label="Descrição (opcional)",
        placeholder="Detalhes sobre o evento...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )
    remind_minutes = ui.TextInput(
        label="Lembrar X minutos antes (0 = desligado)",
        placeholder="15",
        max_length=5,
        required=False,
    )

    def __init__(self, cog: NotifyCog, notif: dict) -> None:
        super().__init__()
        self.cog = cog
        self.notif_id = notif["id"]

        # Preencher campos com os valores atuais
        self.title_input.default = notif.get("title", "")
        scheduled = _parse_scheduled_iso(notif["scheduled_at"])
        self.date_input.default = scheduled.strftime("%d/%m/%Y")
        self.time_input.default = scheduled.strftime("%H:%M")
        self.description_input.default = notif.get("description") or ""
        self.remind_minutes.default = str(notif.get("remind_before", 0) or 0)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        date_input = self.date_input.value.strip()
        time_input = self.time_input.value.strip()

        dt_brt = await _resolve_future_notify_datetime(
            interaction,
            date_input,
            time_input,
        )
        if dt_brt is None:
            return

        remind_before = _parse_optional_remind_minutes(self.remind_minutes.value)

        await self.cog.bot.notification_service.update_notification(
            self.notif_id,
            title=self.title_input.value.strip(),
            scheduled_at=dt_brt.isoformat(),
            description=self.description_input.value.strip() or None,
            remind_before=remind_before,
        )

        embed = _build_notification_manage_embed(
            title=self.title_input.value.strip(),
            description=self.description_input.value.strip() or None,
            scheduled_at=dt_brt,
            remind_before=remind_before,
            notif_id=self.notif_id,
            user=interaction.user,
        )
        view = self.cog.build_manage_view(self.notif_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

class NotifyManageView(ui.View):
    """Botões de gerenciamento após criar/visualizar uma notificação."""

    def __init__(self, cog: NotifyCog, notif_id: int, owner_id: int) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.notif_id = notif_id
        self.owner_id = owner_id

    @ui.button(
        label="Adicionar Membros",
        style=discord.ButtonStyle.primary,
        emoji=BotEmojis.COMMON_MEMBER_ADD,
    )
    async def add_members_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.defer()
            return
        await interaction.response.edit_message(
            embed=EmbedBuilder.default(
                f"{BotEmojis.COMMON_USERS} Adicionar Membros",
                "Selecione os membros que deseja mencionar quando a notificação disparar.",
            ).build(),
            view=MemberSelectView(self.cog, self.notif_id, self.owner_id),
        )

    @ui.button(
        label="Alternar Lembrete",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.ACTION_EDIT,
    )
    async def toggle_remind_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.defer()
            return
        await interaction.response.send_modal(RemindModal(self.cog, self.notif_id))

    @ui.button(
        label="Editar",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.ACTION_EDIT,
    )
    async def edit_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.defer()
            return

        svc = self.cog.bot.notification_service
        notif = await svc.get_notification(self.notif_id)
        if not notif:
            embed = EmbedBuilder.error_user("Notificação não encontrada.").build()
            await interaction.response.edit_message(embed=embed, view=self)
            return

        await interaction.response.send_modal(EditNotifyModal(self.cog, notif))

    @ui.button(
        label="Sair da Menção",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.COMMON_NO_NOTIFICATIONS,
    )
    async def opt_out_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        """Qualquer membro mencionado pode pedir para sair."""
        svc = self.cog.bot.notification_service
        notif = await svc.get_notification(self.notif_id)
        if not notif:
            embed = EmbedBuilder.error_user("Notificação não encontrada.").build()
            await interaction.response.edit_message(embed=embed, view=self)
            return

        if interaction.user.id == notif["creator_id"]:
            embed = (
                EmbedBuilder.error_user(
                    "Você é o criador — não pode sair da sua própria notificação.\n"
                    "Use **Cancelar** se quiser removê-la."
                )
                .build()
            )
            await interaction.response.edit_message(embed=embed, view=self)
            return

        result = await svc.opt_out(self.notif_id, interaction.user.id)
        if result:
            embed = (
                EmbedBuilder.success("Você **não será mencionado** nesta notificação.")
                .build()
            )
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            embed = (
                EmbedBuilder.error_user(
                    "Você não está na lista de membros desta notificação."
                )
                .build()
            )
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Ver Detalhes", style=discord.ButtonStyle.secondary, emoji=BotEmojis.COMMON_INFO)
    async def details_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        svc = self.cog.bot.notification_service
        notif = await svc.get_notification(self.notif_id)
        if not notif:
            embed = EmbedBuilder.error_user("Notificação não encontrada.").build()
            await interaction.response.edit_message(embed=embed, view=self)
            return

        members = await svc.get_members(self.notif_id)
        ts = _unix(_parse_scheduled_iso(notif["scheduled_at"]))

        desc = f"<t:{ts}:F> (<t:{ts}:R>)"
        if notif.get("description"):
            desc += f"\n{notif['description']}"

        remind = notif.get("remind_before", 0)
        if remind > 0:
            desc += f"\n{BotEmojis.COMMON_WATCH} Lembrete: {remind} min antes"

        mention_lines: list[str] = []
        if members:
            active = [m for m in members if not m["opted_out"]]
            opted = [m for m in members if m["opted_out"]]
            if active:
                mention_lines.append(
                    f"{BotEmojis.COMMON_USERS} Membros ({len(active)}): "
                    + ", ".join(f"<@{m['user_id']}>" for m in active)
                )
            if opted:
                mention_lines.append(
                    f" Saíram ({len(opted)}): "
                    + ", ".join(f"<@{m['user_id']}>" for m in opted)
                )

        if mention_lines:
            desc += f"\n\n{Separators.STAR}\n" + "\n".join(mention_lines)

        desc += f"\n`ID: #{notif['id']}`"

        creator = (
            interaction.guild.get_member(notif["creator_id"])
            if interaction.guild
            else None
        )
        creator_name = creator.display_name if creator else f"ID {notif['creator_id']}"
        creator_avatar = creator.display_avatar.url if creator else None

        embed = (
            EmbedBuilder.default()
            .title(notif["title"])
            .description(desc)
            .author(creator_name, creator_avatar)
            .build()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.danger,
        emoji=BotEmojis.STATUS_DISABLED,
    )
    async def cancel_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.defer()
            return

        svc = self.cog.bot.notification_service
        await svc.delete_notification(self.notif_id)
        embed = EmbedBuilder.default(
            "Notificação cancelada.", f"A notificação `#{self.notif_id}` foi removida."
        ).build()
        await interaction.response.edit_message(embed=embed, view=None)

class MemberSelectView(ui.View):
    """View com seletor de membros do servidor."""

    def __init__(self, cog: NotifyCog, notif_id: int, owner_id: int) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.notif_id = notif_id
        self.owner_id = owner_id

    @ui.select(
        cls=ui.UserSelect,
        placeholder="Selecione membros para mencionar...",
        min_values=1,
        max_values=10,
    )
    async def member_select(
        self, interaction: discord.Interaction, select: ui.UserSelect
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.defer()
            return

        svc = self.cog.bot.notification_service
        added = []
        for member in select.values:
            if member.bot:
                continue
            await svc.add_member(self.notif_id, member.id)
            added.append(member.mention)

        if added:
            embed = EmbedBuilder.success(
                f"Membros adicionados: {', '.join(added)}\n\n"
                f"Eles serão mencionados quando a notificação disparar.\n"
                f"Cada membro pode usar o botão **Sair da Menção** se preferir."
            ).build()
        else:
            embed = EmbedBuilder.error_user(
                "Nenhum membro válido selecionado (bots são ignorados)."
            ).build()

        await interaction.response.edit_message(embed=embed, view=None)

class RemindModal(ui.Modal, title="Alterar Lembrete Prévio"):
    """Modal para alterar minutos de lembrete prévio."""

    minutes = ui.TextInput(
        label="Minutos antes (0 = desligar)",
        placeholder="15",
        max_length=5,
        required=True,
        default="0",
    )

    def __init__(self, cog: NotifyCog, notif_id: int) -> None:
        super().__init__()
        self.cog = cog
        self.notif_id = notif_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            mins = int(self.minutes.value.strip())
            if mins < 0:
                mins = 0
        except ValueError:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user(
                    "Digite um número válido de minutos."
                ).build(),
            )
            return

        svc = self.cog.bot.notification_service
        await svc.update_remind_before(self.notif_id, mins)

        if mins == 0:
            msg = "Lembrete prévio **desligado**."
        else:
            msg = f"Lembrete prévio configurado para **{mins} minuto(s)** antes."

        await interaction.response.send_message(
            embed=EmbedBuilder.success(msg).build(),
        )

class NotifyListView(ui.View):
    """View que mostra a lista de notificações e permite gerenciar cada uma."""

    def __init__(self, cog: NotifyCog, notifications: list[dict], user_id: int) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.notifications = notifications
        self.user_id = user_id

        if notifications:
            options = []
            for n in notifications[:25]:
                label = n["title"][:100]
                options.append(
                    discord.SelectOption(
                        label=label,
                        value=str(n["id"]),
                        description=f"ID #{n['id']}",
                    )
                )
            self.add_item(NotifySelectMenu(cog, options, user_id))

class NotifySelectMenu(ui.Select):
    """Menu de seleção para escolher uma notificação da lista."""

    def __init__(
        self, cog: NotifyCog, options: list[discord.SelectOption], user_id: int
    ) -> None:
        super().__init__(
            placeholder="Selecione uma notificação para gerenciar...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction) -> None:
        notif_id = int(self.values[0])
        svc = self.cog.bot.notification_service
        notif = await svc.get_notification(notif_id)
        if not notif:
            await interaction.response.defer()
            return

        ts = _unix(_parse_scheduled_iso(notif["scheduled_at"]))
        desc = f"**{notif['title']}**\n\n <t:{ts}:F> (<t:{ts}:R>)\n"
        if notif.get("description"):
            desc += f" {notif['description']}\n"

        remind = notif.get("remind_before", 0)
        desc += f"{BotEmojis.COMMON_WATCH} Lembrete: **{'desligado' if remind == 0 else f'{remind} min'}**\n"
        desc += f"`ID: #{notif['id']}`"

        embed = EmbedBuilder.default(f"{BotEmojis.COMMON_NOTIFICATIONS} Notificação", desc).build()
        view = NotifyManageView(self.cog, notif_id, notif["creator_id"])
        await interaction.response.edit_message(embed=embed, view=view)

class NotifyStartView(ui.View):
    """Botão para abrir o modal de criação (prefix commands)."""

    def __init__(self, cog: NotifyCog, channel_id: int, owner_id: int) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.channel_id = channel_id
        self.owner_id = owner_id

    @ui.button(label="Criar Notificação", style=discord.ButtonStyle.success, emoji=BotEmojis.ACTION_CREATE)
    async def create_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.defer()
            return
        await interaction.response.send_modal(NotifyModal(self.cog, self.channel_id))

    @ui.button(
        label="Listar notificações", style=discord.ButtonStyle.primary, emoji=BotEmojis.COMMON_LIST
    )
    async def list_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.defer()
            return

        svc = self.cog.bot.notification_service
        notifs = await svc.get_by_creator(interaction.guild.id, interaction.user.id)
        if not notifs:
            embed = EmbedBuilder.default(
                f"{BotEmojis.COMMON_NOTIFICATIONS} Minhas Notificações",
                "Você não tem notificações agendadas neste servidor.",
            ).build()
            await interaction.response.edit_message(embed=embed, view=None)
            return

        lines = []
        for n in notifs[:25]:
            ts = _unix(_parse_scheduled_iso(n["scheduled_at"]))
            remind = n.get("remind_before", 0)
            remind_txt = f" • {BotEmojis.COMMON_WATCH} {remind}min" if remind > 0 else ""
            lines.append(f"`#{n['id']}` **{n['title']}** — <t:{ts}:R>{remind_txt}")

        desc = "\n".join(lines)
        embed = (
            EmbedBuilder.default(f"{BotEmojis.COMMON_NOTIFICATIONS} Minhas Notificações", desc)
            .footer("Selecione uma para gerenciar")
            .build()
        )
        view = NotifyListView(self.cog, notifs[:25], interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=view)

class NotifyHubView(ui.View):
    """Hub simples para criar, listar e gerenciar notificações."""

    def __init__(self, cog: NotifyCog, channel_id: int, owner_id: int) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.channel_id = channel_id
        self.owner_id = owner_id

    @ui.button(label="Criar nova", style=discord.ButtonStyle.success, emoji=BotEmojis.ACTION_CREATE)
    async def create_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.defer()
            return
        await interaction.response.send_modal(NotifyModal(self.cog, self.channel_id))

    @ui.button(
        label="Minhas notificações", style=discord.ButtonStyle.primary, emoji=BotEmojis.COMMON_USERS
    )
    async def list_btn(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.defer()
            return

        svc = self.cog.bot.notification_service
        notifs = await svc.get_by_creator(interaction.guild.id, interaction.user.id)
        if not notifs:
            embed = EmbedBuilder.default(
                f"{BotEmojis.COMMON_NOTIFICATIONS} Minhas Notificações",
                "Você não tem notificações agendadas neste servidor.",
            ).build()
            await interaction.response.edit_message(embed=embed, view=None)
            return

        lines = []
        for n in notifs[:25]:
            ts = _unix(_parse_scheduled_iso(n["scheduled_at"]))
            remind = n.get("remind_before", 0)
            remind_txt = f" • {BotEmojis.COMMON_WATCH} {remind}min" if remind > 0 else ""
            lines.append(f"`#{n['id']}` **{n['title']}** — <t:{ts}:R>{remind_txt}")

        desc = "\n".join(lines)
        embed = (
            EmbedBuilder.default(f"{BotEmojis.COMMON_NOTIFICATIONS} Minhas Notificações", desc)
            .footer("Selecione uma para gerenciar")
            .build()
        )
        view = NotifyListView(self.cog, notifs[:25], interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=view)
