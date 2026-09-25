from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotEmojis
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from features.community.ui.ticket_ui import (
    TicketPanelOpenView,
    TicketControlView,
    TicketCloseConfirmView,
    TicketSetupControlView,
)

logger = logging.getLogger(__name__)


class TicketCog(commands.Cog, name="Ticket"):
    """Cog que gerencia a interface e os comandos do sistema de tickets."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service = bot.ticket_service

    async def cog_load(self) -> None:
        """Registra as views persistentes para funcionamento contínuo após restarts."""
        self.bot.add_view(TicketPanelOpenView())
        self.bot.add_view(TicketControlView())

    @commands.command(name="ticket-setup")
    @commands.has_permissions(manage_guild=True)
    async def ticket_setup_prefix(self, ctx: commands.Context) -> None:
        """Inicia o painel de configuração do sistema de tickets."""
        embed = (
            EmbedBuilder.default(
                title=f"{BotEmojis.ACTION_SETTINGS} Configuração do Sistema de Tickets",
                description="Escolha uma das opções abaixo para configurar o suporte por tickets neste servidor.\n\n"
                f"**{BotEmojis.ACTION_CREATE} Criar do zero**: O bot criará automaticamente a categoria, o canal de abertura (painel) e o canal de logs com as permissões corretas para o cargo informado.\n"
                f"**Manual**: Configure de forma personalizada usando o comando de barra `/ticket setup`."
            )
            .timestamp()
            .build()
        )
        view = TicketSetupControlView()
        await ctx.send(embed=embed, view=view)

    ticket = app_commands.Group(name="ticket", description="Comandos do sistema de tickets")

    @ticket.command(name="setup", description="Configura o painel e os canais de ticket no servidor")
    @app_commands.describe(
        categoria="Categoria onde os canais de suporte serão criados",
        cargo_suporte="Cargo da equipe de suporte que atenderá os tickets",
        canal_logs="Canal de texto opcional onde os históricos e logs serão salvos",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        categoria: discord.CategoryChannel,
        cargo_suporte: discord.Role,
        canal_logs: discord.TextChannel | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # 1. Salvar configuração no banco
        await self.service.save_config(
            interaction.guild_id,
            categoria.id,
            cargo_suporte.id,
            canal_logs.id if canal_logs else None,
        )

        # 2. Construir e enviar o painel interativo de suporte
        embed = (
            EmbedBuilder.default(
                title=f"{BotEmojis.COMMON_TICKET} Central de Suporte",
                description="Precisa de ajuda com alguma dúvida, denúncia ou suporte geral?\n\n"
                "Clique no botão abaixo para abrir um atendimento privado com a equipe de suporte.",
            )
            .timestamp()
            .build()
        )

        view = TicketPanelOpenView()
        await interaction.channel.send(embed=embed, view=view)

        await interaction.followup.send(
            embed=EmbedBuilder.success(
                f"Sistema de tickets configurado com sucesso!\n"
                f"**Categoria:** {categoria.mention}\n"
                f"**Cargo Suporte:** {cargo_suporte.mention}\n"
                f"**Logs:** {canal_logs.mention if canal_logs else 'Desativados'}"
            ).build(),
            ephemeral=True,
        )

    @ticket.command(name="close", description="Fecha e deleta o ticket de suporte atual")
    async def close(self, interaction: discord.Interaction) -> None:
        ticket = await self.service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user(
                    "Este canal não está registrado como um ticket ativo."
                ).build(),
                ephemeral=True,
            )
            return

        confirm_view = TicketCloseConfirmView()
        await interaction.response.send_message(
            embed=EmbedBuilder.alert(
                "Você tem certeza que deseja fechar este ticket? Esta ação excluirá este canal."
            ).build(),
            view=confirm_view,
            ephemeral=True,
        )

    @ticket.command(name="claim", description="Assume o atendimento do ticket de suporte atual")
    async def claim(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        # 1. Verificar configuração
        config = await self.service.get_config(interaction.guild_id)
        if not config:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "O sistema de tickets não está configurado."
                ).build(),
                ephemeral=True,
            )
            return

        # 2. Verificar permissões
        support_role = interaction.guild.get_role(config["support_role_id"])
        is_staff = (support_role in interaction.user.roles) if support_role else False
        is_admin = interaction.user.guild_permissions.administrator

        if not (is_staff or is_admin):
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    "Apenas a equipe de suporte pode assumir este ticket."
                ).build(),
                ephemeral=True,
            )
            return

        # 3. Verificar estado do ticket
        ticket = await self.service.get_ticket_by_channel(interaction.channel_id)
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

        # 4. Atualizar banco e canal
        await self.service.claim_ticket(interaction.channel_id, interaction.user.id)
        
        try:
            new_topic = f"{interaction.channel.topic} | Assumido por {interaction.user.name}"
            await interaction.channel.edit(topic=new_topic)
        except discord.DiscordException:
            pass

        embed = (
            EmbedBuilder.success(
                f"Este ticket agora está sendo atendido por {interaction.user.mention}."
            )
            .timestamp()
            .build()
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: LunaBot) -> None:
    await bot.add_cog(TicketCog(bot))
