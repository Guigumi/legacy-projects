"""
Cog de limpeza de chat — comando interativo com confirmação.
Híbrido: funciona com /clear e !clear.
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotEmojis, Separators
from core.utils.embed_builder import EmbedBuilder
from core.enums import Feature
from core.events import BotEvent

logger = logging.getLogger(__name__)

# Discord API: bulk_delete só apaga mensagens com < 14 dias
# e no máximo 100 por chamada. Fazemos batch se necessário.
MAX_PURGE_PER_CALL = 100
MAX_PURGE_TOTAL = 1000


# ── Views ─────────────────────────────────────────────────────


class ConfirmPurgeView(discord.ui.View):
    """Confirmação para apagar N mensagens."""

    def __init__(
        self, admin_id: int, channel: discord.TextChannel, amount: int
    ) -> None:
        super().__init__(timeout=30)
        self.admin_id = admin_id
        self.channel = channel
        self.amount = amount

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger, emoji=BotEmojis.ACTION_REMOVE)
    async def confirm_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            embed=EmbedBuilder.alert("Apagando mensagens...").build(),
            view=None,
        )

        try:
            # Purge em batches (API limita 100 por chamada)
            total_deleted = 0
            remaining = self.amount
            while remaining > 0:
                batch = min(remaining, MAX_PURGE_PER_CALL)
                deleted = await self.channel.purge(limit=batch)
                if not deleted:
                    break
                total_deleted += len(deleted)
                remaining -= len(deleted)
                if len(deleted) < batch:
                    break  # Não há mais mensagens para apagar
            count = total_deleted

            desc = f"**{count}** mensagens apagadas."
            if count < self.amount:
                desc += (
                    f"\n{BotEmojis.STATUS_WARNING} Apenas {count} de {self.amount} foram removidas. "
                    "Mensagens com mais de **14 dias** não podem ser apagadas em massa."
                )

            result = (
                EmbedBuilder.success(desc)
                .footer("Esta mensagem será removida em 5s")
                .build()
            )
            msg = await self.channel.send(embed=result)
            await asyncio.sleep(5)
            try:
                await msg.delete()
            except discord.NotFound:
                pass

        except discord.Forbidden:
            await self.channel.send(
                embed=EmbedBuilder.error_user(
                    "Não tenho permissão para apagar mensagens neste canal."
                ).build(),
                delete_after=5,
            )
        except discord.HTTPException as e:
            logger.error(f"Erro ao apagar mensagens: {e}")
            await self.channel.send(
                embed=EmbedBuilder.error_internal(
                    "Erro ao apagar mensagens. Mensagens com mais de 14 dias não podem ser apagadas em massa."
                ).build(),
                delete_after=8,
            )

    @discord.ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.STATUS_DISABLED,
    )
    async def cancel_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = EmbedBuilder.default("Limpeza cancelada.").build()
        await interaction.response.edit_message(embed=embed, view=None)
        await asyncio.sleep(3)
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass


class ConfirmNukeView(discord.ui.View):
    """Dupla confirmação para apagar TUDO (clonar canal)."""

    def __init__(self, admin_id: int, channel: discord.TextChannel) -> None:
        super().__init__(timeout=30)
        self.admin_id = admin_id
        self.channel = channel
        self.confirmed_once = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    @discord.ui.button(
        label="Sim, apagar tudo",
        style=discord.ButtonStyle.danger,
        emoji=BotEmojis.STATUS_WARNING,
    )
    async def confirm_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not self.confirmed_once:
            # ── Primeira confirmação → pede a segunda ─────────
            self.confirmed_once = True
            button.label = "CONFIRMAR — Sem volta!"
            button.emoji = BotEmojis.ACTION_REMOVE
            button.style = discord.ButtonStyle.danger

            embed = (
                EmbedBuilder.alert(
                    f"**{BotEmojis.STATUS_WARNING} ATENÇÃO — Ação irreversível!**\n\n"
                    "Isso vai **clonar este canal** e **deletar o original** "
                    "com todas as mensagens.\n\n"
                    f"{Separators.STAR}\n\n"
                    "**Clique novamente para confirmar.**"
                )
                .footer("Permissões, tópico e categoria serão preservados")
                .build()
            )
            await interaction.response.edit_message(embed=embed, view=self)
            return

        # ── Segunda confirmação → executar nuke ───────────
        await interaction.response.edit_message(
            embed=EmbedBuilder.alert(f"{BotEmojis.STATUS_WARNING} **NUKE INICIADO!** O canal será clonado e deletado agora...").build(),
            view=None,
        )

        try:
            old_channel = self.channel
            position = old_channel.position

            # Registrar ação no event_bus antes de deletar (audit trail)
            bot = interaction.client
            event_bus = getattr(bot, "event_bus", None)
            if event_bus and old_channel.guild:
                await event_bus.emit(
                    old_channel.guild.id,
                    BotEvent.CONFIG_CHANGED,
                    {
                        "action": "channel_nuke",
                        "channel_name": old_channel.name,
                        "channel_id": old_channel.id,
                        "executed_by": interaction.user.id,
                    },
                )

            # Clonar: preserva nome, tópico, permissões, categoria, nsfw, slowmode
            new_channel = await old_channel.clone(
                reason=f"Clear All por {interaction.user} (ID: {interaction.user.id})",
            )

            # Mover para a mesma posição
            await new_channel.edit(position=position)

            # Deletar o canal original
            await old_channel.delete(
                reason=f"Clear All por {interaction.user} (ID: {interaction.user.id})",
            )

            # Mensagem de sucesso no novo canal
            embed = (
                EmbedBuilder.success("Canal limpo com sucesso!")
                .description(
                    f"{BotEmojis.COMMON_TASK_DONE} Canal limpo com sucesso!\n\n"
                    f"Executado por {interaction.user.mention}\n"
                    f"Todas as permissões e configurações foram preservadas."
                )
                .footer("Esta mensagem será removida em 10s")
                .build()
            )
            msg = await new_channel.send(embed=embed)
            await asyncio.sleep(10)
            try:
                await msg.delete()
            except discord.NotFound:
                pass

        except discord.Forbidden:
            try:
                await self.channel.send(
                    embed=EmbedBuilder.error_user(
                        "Não tenho permissão para clonar/deletar este canal.\n"
                        "Preciso de **Gerenciar Canais**."
                    ).build(),
                    delete_after=8,
                )
            except Exception:
                pass
        except discord.HTTPException as e:
            logger.error(f"Erro ao clonar canal: {e}")
            try:
                await self.channel.send(
                    embed=EmbedBuilder.error_internal(
                        "Erro ao clonar/deletar o canal. Se persistir, reporte ao suporte."
                    ).build(),
                    delete_after=8,
                )
            except Exception:
                pass

    @discord.ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.secondary,
        emoji=BotEmojis.STATUS_DISABLED,
    )
    async def cancel_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = EmbedBuilder.default("Limpeza cancelada.").build()
        await interaction.response.edit_message(embed=embed, view=None)
        await asyncio.sleep(3)
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass


class AmountModal(discord.ui.Modal, title="Quantidade de mensagens"):
    """Modal para o admin digitar a quantidade exata."""

    amount_input = discord.ui.TextInput(
        label="Quantas mensagens apagar?",
        placeholder="Ex: 42",
        min_length=1,
        max_length=4,
        required=True,
    )

    def __init__(self, admin_id: int, channel: discord.TextChannel) -> None:
        super().__init__()
        self.admin_id = admin_id
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.amount_input.value.strip()
        if not raw.isdigit() or int(raw) < 1:
            embed = EmbedBuilder.error_user("Digite um número válido (1–1000).").build()
            await interaction.response.send_message(embed=embed)
            return

        amount = min(int(raw), 1000)
        embed = (
            EmbedBuilder.alert(
                f"Tem certeza que deseja apagar **{amount}** mensagens?\n\n"
                f"Canal: {self.channel.mention}\n"
                "Mensagens com mais de **14 dias** não serão afetadas."
            )
            .footer("Ação irreversível • Tempo limite: 30s")
            .build()
        )
        view = ConfirmPurgeView(self.admin_id, self.channel, amount)
        await interaction.response.edit_message(embed=embed, view=view)


class ClearActionView(discord.ui.View):
    """View principal: escolher quantidade ou limpar tudo."""

    def __init__(self, admin_id: int, channel: discord.TextChannel) -> None:
        super().__init__(timeout=60)
        self.admin_id = admin_id
        self.channel = channel
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    @discord.ui.select(
        placeholder="Quantas mensagens apagar?",
        options=[
            discord.SelectOption(label="10 mensagens", value="10", emoji=BotEmojis.COMMON_MODERATION),
            discord.SelectOption(label="25 mensagens", value="25", emoji=BotEmojis.COMMON_MODERATION),
            discord.SelectOption(label="50 mensagens", value="50", emoji=BotEmojis.COMMON_MODERATION),
            discord.SelectOption(
                label="100 mensagens",
                value="100",
                emoji=BotEmojis.COMMON_MODERATION,
                description="Limite máximo por operação",
            ),
        ],
        row=0,
    )
    async def select_amount(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        amount = int(select.values[0])

        embed = (
            EmbedBuilder.alert(
                f"Tem certeza que deseja apagar **{amount}** mensagens?\n\n"
                f"Canal: {self.channel.mention}\n"
                "Mensagens com mais de **14 dias** não serão afetadas."
            )
            .footer("Ação irreversível • Tempo limite: 30s")
            .build()
        )
        view = ConfirmPurgeView(self.admin_id, self.channel, amount)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(
        label="Quantidade personalizada",
        style=discord.ButtonStyle.primary,
        emoji=BotEmojis.ACTION_EDIT,
        row=1,
    )
    async def custom_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        modal = AmountModal(self.admin_id, self.channel)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Apagar TUDO",
        style=discord.ButtonStyle.danger,
        emoji=BotEmojis.ACTION_REMOVE,
        row=1,
    )
    async def nuke_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = (
            EmbedBuilder.alert(
                "**Você está prestes a apagar TODAS as mensagens deste canal.**\n\n"
                "O bot vai **clonar o canal** (preservando nome, permissões, "
                "tópico e categoria) e **deletar o original**.\n\n"
                f"{Separators.STAR}\n\n"
                "Deseja continuar?"
            )
            .footer("Ação irreversível • Requer dupla confirmação")
            .build()
        )
        view = ConfirmNukeView(self.admin_id, self.channel)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


# ── Cog ───────────────────────────────────────────────────────


class ClearCog(commands.Cog):
    """Comando de limpeza de chat para administradores."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="clear",
        description="Limpar mensagens do canal",
        aliases=["purge", "limpar"],
    )
    @app_commands.describe(
        amount="Quantidade de mensagens para apagar (1–1000). Omita para abrir o painel."
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, amount: int | None = None) -> None:
        """Painel interativo para limpar mensagens do canal."""
        # Verificar feature de moderação
        enabled = await self.bot.guild_service.is_feature_enabled(
            ctx.guild.id,
            Feature.MODERATION,
        )
        if not enabled:
            embed = EmbedBuilder.error_user(
                "A funcionalidade de moderação está desativada neste servidor."
            ).build()
            await ctx.send(embed=embed)
            return

        # Se o comando foi via prefixo, deletar a invocação
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

        # ── Atalho: !clear <N> → confirmação direta ──────────
        if amount is not None:
            if amount < 1:
                embed = EmbedBuilder.error_user(
                    "A quantidade deve ser pelo menos **1**."
                ).build()
                await ctx.send(embed=embed, delete_after=4)
                return

            amount = min(amount, MAX_PURGE_TOTAL)

            embed = (
                EmbedBuilder.alert(
                    f"Tem certeza que deseja apagar **{amount}** mensagens?\n\n"
                    f"Canal: {ctx.channel.mention}\n"
                    "Mensagens com mais de **14 dias** não serão afetadas."
                )
                .footer("Ação irreversível • Tempo limite: 30s")
                .build()
            )
            view = ConfirmPurgeView(ctx.author.id, ctx.channel, amount)
            await ctx.send(embed=embed, view=view)
            return

        # ── Painel interativo ─────────────────────────────────
        embed = (
            EmbedBuilder.default()
            .section("Limpeza de Chat")
            .description(
                "Escolha quantas mensagens deseja apagar, "
                "ou clique em **Apagar TUDO** para limpar o canal inteiro.\n\n"
                " **Quantidade rápida** — Selecione no menu\n"
                f"{BotEmojis.ACTION_EDIT} **Personalizado** — Digite a quantidade exata (até 1000)\n"
                " **Apagar TUDO** — Clona o canal e deleta o original\n\n"
                "Ou use direto: `!clear 50`"
            )
            .footer("Apenas mensagens com menos de 14 dias podem ser apagadas em massa")
            .build()
        )
        view = ClearActionView(ctx.author.id, ctx.channel)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ClearCog(bot))
