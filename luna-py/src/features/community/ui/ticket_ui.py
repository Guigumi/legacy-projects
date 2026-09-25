from __future__ import annotations

import asyncio
import io
import logging
import discord
from discord import ui

from config.settings import BotEmojis
from core.utils.embed_builder import EmbedBuilder

logger = logging.getLogger(__name__)


class TicketPanelOpenView(ui.View):
    """View persistente colocada no canal de suporte para permitir que usuários abram tickets."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(
        label="Abrir Ticket",
        style=discord.ButtonStyle.success,
        custom_id="ticket_open_button",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        
        ticket_service = interaction.client.ticket_service
        guild_id = interaction.guild_id
        user_id = interaction.user.id

        # 1. Verificar configuração do servidor
        config = await ticket_service.get_config(guild_id)
        if not config:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "O sistema de tickets não está configurado neste servidor."
                ).build(),
                ephemeral=True,
            )
            return

        # 2. Verificar se o usuário já possui um ticket ativo
        active_ticket = await ticket_service.get_active_ticket_by_user(guild_id, user_id)
        if active_ticket:
            channel = interaction.guild.get_channel(active_ticket["channel_id"])
            if channel:
                await interaction.followup.send(
                    embed=EmbedBuilder.error_user(
                        f"Você já possui um ticket aberto em {channel.mention}."
                    ).build(),
                    ephemeral=True,
                )
                return
            else:
                # O canal foi deletado manualmente, então fechamos o registro órfão
                await ticket_service.close_ticket(active_ticket["channel_id"], interaction.client.user.id)

        # 3. Buscar categoria
        category = interaction.guild.get_channel(config["category_id"])
        if not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "A categoria configurada para os tickets não foi encontrada. Contate a Staff."
                ).build(),
                ephemeral=True,
            )
            return

        # 4. Obter número sequencial do ticket
        num = await ticket_service.get_next_ticket_number(guild_id)

        # 5. Definir permissões do canal
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
        }

        support_role = interaction.guild.get_role(config["support_role_id"])
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        # 6. Criar canal do ticket
        try:
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{num:04d}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket #{num:04d} - Autor: {interaction.user.name} ({user_id})",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "O bot não possui permissão para criar canais na categoria de tickets."
                ).build(),
                ephemeral=True,
            )
            return
        except Exception:
            logger.exception("Falha ao criar canal de ticket")
            await interaction.followup.send(
                embed=EmbedBuilder.error_internal().build(),
                ephemeral=True,
            )
            return

        # 7. Registrar ticket no banco de dados
        await ticket_service.create_ticket(guild_id, channel.id, user_id)

        # 8. Enviar mensagem de boas-vindas no canal do ticket
        embed = (
            EmbedBuilder.default(
                f"{BotEmojis.COMMON_TICKET} Ticket #{num:04d}",
                f"Olá {interaction.user.mention}, seja bem-vindo ao suporte!\n"
                "Descreva a sua dúvida ou problema detalhadamente. Um membro da equipe "
                f"({support_role.mention if support_role else 'Staff'}) ajudará você em breve.\n\n"
                "Use os botões abaixo para gerenciar este ticket.",
            )
            .timestamp()
            .build()
        )

        control_view = TicketControlView()
        await channel.send(
            content=f"{interaction.user.mention} | {support_role.mention if support_role else ''}",
            embed=embed,
            view=control_view,
        )

        await interaction.followup.send(
            embed=EmbedBuilder.success(
                f"Seu ticket foi aberto com sucesso em {channel.mention}!"
            ).build(),
            ephemeral=True,
        )


class TicketControlView(ui.View):
    """View contendo botões de controle dentro de um canal de ticket ativo."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(
        label="Assumir",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_claim_button",
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        
        ticket_service = interaction.client.ticket_service
        guild_id = interaction.guild_id
        user = interaction.user

        # 1. Verificar configuração
        config = await ticket_service.get_config(guild_id)
        if not config:
            return

        # 2. Verificar permissões (Staff ou Admin)
        support_role = interaction.guild.get_role(config["support_role_id"])
        is_staff = (support_role in user.roles) if support_role else False
        is_admin = user.guild_permissions.administrator

        if not (is_staff or is_admin):
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "Apenas a equipe de suporte pode assumir este ticket."
                ).build(),
                ephemeral=True,
            )
            return

        # 3. Verificar estado atual do ticket
        ticket = await ticket_service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "Este canal não está registrado como um ticket ativo."
                ).build(),
                ephemeral=True,
            )
            return

        if ticket["status"] == "claimed":
            claimant = interaction.guild.get_member(ticket["claimant_id"])
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    f"Este ticket já foi assumido por {claimant.mention if claimant else 'outro staff'}."
                ).build(),
                ephemeral=True,
            )
            return

        # 4. Atualizar banco e tópicos
        await ticket_service.claim_ticket(interaction.channel_id, user.id)
        
        try:
            new_topic = f"{interaction.channel.topic} | Assumido por {user.name}"
            await interaction.channel.edit(topic=new_topic)
        except discord.DiscordException:
            logger.warning("Falha ao atualizar tópico do canal de ticket %s", interaction.channel_id)

        # 5. Atualizar botões na view
        for item in self.children:
            if isinstance(item, ui.Button) and item.custom_id == "ticket_claim_button":
                item.disabled = True
                item.label = "Assumido"
                item.style = discord.ButtonStyle.secondary

        await interaction.message.edit(view=self)

        # 6. Notificar canal
        embed = (
            EmbedBuilder.success(
                f"Este ticket agora está sendo atendido por {user.mention}."
            )
            .timestamp()
            .build()
        )
        await interaction.channel.send(embed=embed)

    @ui.button(
        label="Fechar",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close_button",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button) -> None:
        # Abre view de confirmação apenas para quem clicou
        confirm_view = TicketCloseConfirmView()
        await interaction.response.send_message(
            embed=EmbedBuilder.alert(
                "Você tem certeza que deseja fechar este ticket? Esta ação não pode ser desfeita."
            ).build(),
            view=confirm_view,
            ephemeral=True,
        )


class TicketCloseConfirmView(ui.View):
    """View ephemeral de confirmação para fechamento de ticket."""

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @ui.button(
        label="Confirmar Fechamento",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_confirm_close_button",
    )
    async def confirm_close(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        
        ticket_service = interaction.client.ticket_service
        channel = interaction.channel
        guild = interaction.guild
        user = interaction.user

        # 1. Obter dados do ticket antes de fechar
        ticket = await ticket_service.get_ticket_by_channel(channel.id)
        if not ticket:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "Informações do ticket não encontradas ou ticket já fechado."
                ).build(),
                ephemeral=True,
            )
            return

        # 2. Registrar fechamento no banco de dados
        await ticket_service.close_ticket(channel.id, user.id)

        # 3. Notificar no canal sobre a deleção iminente
        await channel.send(
            embed=EmbedBuilder.alert(
                "Este ticket foi fechado. Este canal será deletado em 5 segundos."
            ).build()
        )

        # 4. Gerar transcrição das mensagens
        transcript = []
        try:
            async for msg in channel.history(limit=1000, oldest_first=True):
                time_str = msg.created_at.strftime("%d/%m/%Y %H:%M:%S")
                content = msg.clean_content
                if msg.attachments:
                    att_list = ", ".join(a.filename for a in msg.attachments)
                    content += f" [Anexos: {att_list}]"
                transcript.append(f"[{time_str}] {msg.author.name} ({msg.author.id}): {content}")
            
            transcript_text = "\n".join(transcript)
        except Exception:
            logger.exception("Falha ao gerar transcrição do ticket %s", channel.id)
            transcript_text = "Falha ao gerar a transcrição deste ticket."

        # 5. Enviar logs (se configurado)
        config = await ticket_service.get_config(interaction.guild_id)
        if config and config["log_channel_id"]:
            log_channel = guild.get_channel(config["log_channel_id"])
            if isinstance(log_channel, discord.TextChannel):
                creator = guild.get_member(ticket["creator_id"])
                claimant = guild.get_member(ticket["claimant_id"]) if ticket.get("claimant_id") else None
                creator_id = ticket["creator_id"]
                creator_mention = creator.mention if creator else f"ID: {creator_id}"
                claimant_mention = claimant.mention if claimant else "Ninguém"
                created_at_val = ticket["created_at"]

                embed = (
                    EmbedBuilder.default(
                        title=f"{BotEmojis.COMMON_TICKET} Ticket Fechado",
                        description=f"**Canal:** `#{channel.name}`\n"
                        f"**Criador:** {creator_mention}\n"
                        f"**Assumido por:** {claimant_mention}\n"
                        f"**Fechado por:** {user.mention}\n"
                        f"**Aberto em:** `{created_at_val}`\n",
                    )
                    .timestamp()
                    .build()
                )

                try:
                    fp = io.BytesIO(transcript_text.encode("utf-8"))
                    file = discord.File(fp, filename=f"transcript-{channel.name}.txt")
                    await log_channel.send(embed=embed, file=file)
                except Exception:
                    logger.exception("Falha ao enviar arquivo de transcrição para o canal de logs")
                    # Tenta enviar sem o arquivo se falhar
                    await log_channel.send(embed=embed)

        # 6. Aguardar e deletar o canal
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket fechado por {user.name}")
        except discord.DiscordException:
            logger.exception("Falha ao deletar canal de ticket %s", channel.id)

    @ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_cancel_close_button",
    )
    async def cancel_close(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(
            embed=EmbedBuilder.success("Fechamento cancelado.").build(),
            view=None,
        )


class TicketSetupControlView(ui.View):
    """View contendo o botão para criar o sistema do zero."""

    def __init__(self) -> None:
        super().__init__(timeout=300)

    @ui.button(
        label="Criar do zero",
        style=discord.ButtonStyle.success,
        custom_id="ticket_setup_create_from_scratch",
        emoji=BotEmojis.ACTION_CREATE,
    )
    async def create_from_scratch(self, interaction: discord.Interaction, button: ui.Button) -> None:
        modal = TicketSetupModal()
        await interaction.response.send_modal(modal)


class TicketSetupModal(ui.Modal, title="Criar Sistema de Tickets"):
    category_name = ui.TextInput(
        label="Nome da Categoria",
        placeholder="Ex: Suporte",
        required=True,
        max_length=100,
    )
    channel_name = ui.TextInput(
        label="Nome do Canal de Abertura",
        placeholder="Ex: abrir-ticket",
        required=True,
        max_length=100,
    )
    moderator_role = ui.TextInput(
        label="Cargo de Moderador (Nome ou ID)",
        placeholder="Ex: Moderador / 123456789...",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # 1. Validar cargo
        role_input = self.moderator_role.value.strip()
        role = None
        if role_input.isdigit():
            role = guild.get_role(int(role_input))
        if not role:
            role = discord.utils.get(guild.roles, name=role_input)
            if not role:
                for r in guild.roles:
                    if r.name.lower() == role_input.lower():
                        role = r
                        break

        if not role:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    f"Não encontrei o cargo de moderador '{role_input}'. "
                    "Verifique se o nome está idêntico ou use o ID numérico do cargo."
                ).build(),
                ephemeral=True,
            )
            return

        # 2. Criar Categoria
        try:
            category = await guild.create_category(
                name=self.category_name.value.strip(),
                reason="Sistema de tickets criado automaticamente do zero."
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "O bot não possui a permissão de 'Gerenciar Canais' para criar a categoria."
                ).build(),
                ephemeral=True,
            )
            return

        # 3. Criar canal de logs de tickets
        log_overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }

        try:
            log_channel = await guild.create_text_channel(
                name="logs-tickets",
                category=category,
                overwrites=log_overwrites,
                reason="Canal de logs do sistema de tickets."
            )
        except discord.DiscordException:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "Falha ao criar o canal de logs. Verifique minhas permissões."
                ).build(),
                ephemeral=True,
            )
            return

        # 4. Criar canal de abertura de tickets (painel)
        panel_overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        try:
            panel_channel = await guild.create_text_channel(
                name=self.channel_name.value.strip(),
                category=category,
                overwrites=panel_overwrites,
                reason="Canal do painel do sistema de tickets."
            )
        except discord.DiscordException:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "Falha ao criar o canal de abertura de tickets. Verifique minhas permissões."
                ).build(),
                ephemeral=True,
            )
            return

        # 5. Salvar configuração no banco
        ticket_service = interaction.client.ticket_service
        await ticket_service.save_config(
            guild.id,
            category.id,
            role.id,
            log_channel.id
        )

        # 6. Enviar painel persistente no canal criado
        embed = (
            EmbedBuilder.default(
                title=f"{BotEmojis.COMMON_TICKET} Central de Suporte",
                description="Precisa de ajuda com alguma dúvida, denúncia ou suporte geral?\n\n"
                "Clique no botão abaixo para abrir um atendimento privado com a equipe de suporte.",
            )
            .timestamp()
            .build()
        )

        panel_view = TicketPanelOpenView()
        await panel_channel.send(embed=embed, view=panel_view)

        # 7. Confirmar conclusão
        await interaction.followup.send(
            embed=EmbedBuilder.success(
                f"Sistema de tickets criado com sucesso do zero!\n\n"
                f"**Categoria:** {category.mention}\n"
                f"**Canal de Abertura:** {panel_channel.mention}\n"
                f"**Canal de Logs:** {log_channel.mention}\n"
                f"**Cargo Responsável:** {role.mention}"
            ).build(),
            ephemeral=True
        )

