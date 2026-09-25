"""Cog de desenvolvimento — listener `undead` para o Owner e gate de dev mode."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from config.settings import OWNER_ID, Separators, BotEmojis
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder

logger = logging.getLogger(__name__)


class DevPanel(discord.ui.View):
    """Painel dev com alternância de modo Dev para o owner."""

    def __init__(self, bot: LunaBot, dev_mode: bool, callback_toggle):
        super().__init__(timeout=300)
        self.bot = bot
        self.dev_mode = dev_mode
        self.callback_toggle = callback_toggle

        if not dev_mode:
            self.add_item(discord.ui.Button(label="Ativar modo Dev", style=discord.ButtonStyle.success, custom_id="dev_toggle_on"))
        else:
            self.add_item(discord.ui.Button(label="Desativar modo Dev", style=discord.ButtonStyle.danger, custom_id="dev_toggle_off"))
            self.add_item(discord.ui.Button(label="Cog Reload", style=discord.ButtonStyle.secondary, custom_id="dev_cog_reload"))
            self.add_item(discord.ui.Button(label="Server Stats", style=discord.ButtonStyle.secondary, custom_id="dev_server_stats"))
            self.add_item(discord.ui.Button(label="Blacklist", style=discord.ButtonStyle.danger, custom_id="dev_blacklist"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == OWNER_ID

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def on_item_interaction(self, interaction: discord.Interaction):
        custom_id = None
        if hasattr(interaction, "data") and interaction.data:
            custom_id = interaction.data.get("custom_id")

        if not custom_id:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("Botão inválido.").build(),
                ephemeral=True,
            )
            return

        # Para comandos mais pesados, usamos defer
        needs_defer = custom_id in ("dev_cog_reload", "dev_toggle_on", "dev_toggle_off")
        if needs_defer:
            await interaction.response.defer(ephemeral=True)

        if custom_id == "dev_toggle_on":
            await self.callback_toggle(interaction, True)
        elif custom_id == "dev_toggle_off":
            await self.callback_toggle(interaction, False)

        elif custom_id == "dev_cog_reload":
            # Aqui simulamos o reload ou chamamos o comando de reload se houver
            embed = EmbedBuilder.success("Reinicialização de Cogs agendada.").build()
            await interaction.followup.send(embed=embed, ephemeral=True)
        elif custom_id == "dev_server_stats":
            guild = interaction.guild
            if guild:
                members = len(guild.members)
                channels = len(guild.channels)
                embed = (
                    EmbedBuilder.default("Status do Servidor")
                    .stat("Membros", str(members))
                    .stat("Canais", str(channels))
                    .stat("ID", str(guild.id))
                    .build()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        elif custom_id == "dev_blacklist":
            await interaction.response.send_message(
                embed=EmbedBuilder.alert("Módulo de Blacklist em desenvolvimento.").build(),
                ephemeral=True,
            )



class UndeadCog(commands.Cog):
    """Listener 'undead' para acesso rápido a funções de desenvolvimento."""

    def __init__(self, bot: LunaBot):
        self.bot = bot
        self._dev_mode = False

    async def _toggle_dev_mode(self, interaction: discord.Interaction, enable: bool):
        self._dev_mode = enable
        setattr(self.bot, "_dev_mode", enable)
        await self._send_dev_panel(interaction.channel, interaction)

    async def _send_dev_panel(self, channel, interaction: discord.Interaction | None = None):
        status = (
            f"{BotEmojis.STATUS_ENABLED} **ATIVO**"
            if self._dev_mode
            else f"{BotEmojis.STATUS_DISABLED} **INATIVO**"
        )
        embed = (
            EmbedBuilder.default()
            .author(name="Luna Dev Panel", icon_url=self.bot.user.display_avatar.url)
            .description(
                f"**Modo Dev:** {status}\n\n"
                f"{Separators.ARROW_R} **Edição de dados inline** (habilitado em Dev Mode)\n"
                f"{Separators.ARROW_R} **Recarregamento de módulos**\n"
                f"{Separators.ARROW_R} **Gerenciamento de restrições**\n"
                f"{Separators.ARROW_R} **Debug de performance**"
            )
            .footer("Apenas o Owner pode visualizar e interagir")
            .build()
        )
        view = DevPanel(self.bot, self._dev_mode, self._toggle_dev_mode)

        # Monkeypatch para lidar com todos os botões
        async def interaction_handler(btn_interaction: discord.Interaction):
            await view.on_item_interaction(btn_interaction)

        for item in view.children:
            item.callback = interaction_handler

        if interaction:
            # Se já deferimos ou enviamos, usamos followup ou edit
            try:
                if interaction.response.is_done():
                    await interaction.followup.edit_message(message_id="@original", embed=embed, view=view)
                else:
                    await interaction.response.edit_message(embed=embed, view=view)
            except Exception:
                await channel.send(embed=embed, view=view, delete_after=300)
        else:
            await channel.send(embed=embed, view=view, delete_after=300.0)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.author.id != OWNER_ID
            or message.content.lower() != 'undead'
            or not message.guild
            or message.author.bot
        ):
            return
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            logger.warning(f"Não foi possível deletar a mensagem de ativação do undead em {message.channel.id}")
        await self._send_dev_panel(message.channel)


async def setup(bot: LunaBot):
    await bot.add_cog(UndeadCog(bot))
