from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import Colors, BotEmojis
from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder


# ── Modal ─────────────────────────────────────────────────────


class StarboardConfigModal(discord.ui.Modal, title="Configurar Starboard"):
    canal_id = discord.ui.TextInput(
        label="ID do Canal (cole o ID do canal)",
        placeholder="Ex: 1234567890123456789",
        min_length=17,
        max_length=20,
    )
    emoji = discord.ui.TextInput(
        label="Emoji de destaque",
        placeholder="Ex: ⭐  (deixe vazio para usar ⭐)",
        required=False,
        max_length=60,
    )
    minimo = discord.ui.TextInput(
        label="Mínimo de reações",
        placeholder="Ex: 3",
        max_length=3,
    )

    def __init__(self, parent_view: "StarboardConfigView", config: dict | None) -> None:
        super().__init__()
        self.parent_view = parent_view
        if config:
            self.emoji.default = config.get("emoji", "⭐")
            self.minimo.default = str(config.get("min_stars", 3))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Validar canal
        try:
            channel_id = int(self.canal_id.value.strip())
        except ValueError:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("ID de canal inválido. Copie o ID numérico do canal.").build(),
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user(
                    "Canal não encontrado neste servidor. Verifique o ID e tente novamente."
                ).build(),
                ephemeral=True,
            )
            return

        # Validar mínimo
        try:
            minimo = int(self.minimo.value.strip())
            if minimo < 1:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("O mínimo de reações deve ser um número inteiro de 1 ou mais.").build(),
                ephemeral=True,
            )
            return

        emoji_val = self.emoji.value.strip() or "⭐"

        await self.parent_view.service.save_config(
            interaction.guild_id, channel_id, emoji_val, minimo, enabled=1
        )
        await self.parent_view.refresh(
            interaction, success=f"Starboard configurado! Canal: {channel.mention} | Emoji: {emoji_val} | Mínimo: {minimo}"
        )


# ── View ──────────────────────────────────────────────────────


class StarboardConfigView(discord.ui.View):
    """Painel interativo de configuração do Starboard."""

    def __init__(self, service, guild: discord.Guild, admin_id: int) -> None:
        super().__init__(timeout=300)
        self.service = service
        self.guild = guild
        self.admin_id = admin_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("Apenas quem usou o comando pode interagir.").build(),
                ephemeral=True,
            )
            return False
        return True

    async def _build_embed(self) -> discord.Embed:
        config = await self.service.get_config(self.guild.id)
        if not config:
            return (
                EmbedBuilder.default("Starboard — Configuração")
                .description(
                    "O Starboard ainda não está configurado neste servidor.\n\n"
                    "Use **Configurar** para definir o canal, emoji e mínimo de reações."
                )
                .build()
            )

        enabled = config.get("enabled", 0)
        status = (
            f"{BotEmojis.STATUS_ENABLED} Ativo"
            if enabled
            else f"{BotEmojis.STATUS_DISABLED} Desativado"
        )
        channel = self.guild.get_channel(config["channel_id"])
        channel_str = channel.mention if channel else "*Canal excluído*"

        return (
            EmbedBuilder.default("Starboard — Configuração")
            .description(
                f"**Status:** {status}\n"
                f"**Canal:** {channel_str}\n"
                f"**Emoji:** {config['emoji']}\n"
                f"**Mínimo de reações:** {config['min_stars']}"
            )
            .footer("Use o menu abaixo para alterar as configurações")
            .build()
        )

    async def refresh(
        self,
        interaction: discord.Interaction,
        success: str | None = None,
    ) -> None:
        embed = await self._build_embed()
        content = f"{BotEmojis.COMMON_SPARKLES} {success}" if success else None
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    @discord.ui.select(
        placeholder="O que deseja fazer?",
        options=[
            discord.SelectOption(
                label="Configurar",
                value="config",
                emoji=BotEmojis.ACTION_SETTINGS,
                description="Definir canal, emoji e mínimo de reações",
            ),
            discord.SelectOption(
                label="Ver Status",
                value="status",
                emoji=BotEmojis.COMMON_LIST,
                description="Exibe as configurações atuais",
            ),
            discord.SelectOption(
                label="Ativar",
                value="enable",
                emoji=BotEmojis.STATUS_ENABLED,
                description="Ativa o Starboard neste servidor",
            ),
            discord.SelectOption(
                label="Desativar",
                value="disable",
                emoji=BotEmojis.STATUS_DISABLED,
                description="Desativa o Starboard sem apagar as configurações",
            ),
        ],
        row=0,
    )
    async def action_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        action = select.values[0]
        config = await self.service.get_config(interaction.guild_id)

        if action == "config":
            await interaction.response.send_modal(StarboardConfigModal(self, config))

        elif action == "status":
            await self.refresh(interaction)

        elif action == "enable":
            if not config:
                await interaction.response.send_message(
                    embed=EmbedBuilder.error_user(
                        "Configure o Starboard primeiro usando a opção **Configurar**."
                    ).build(),
                    ephemeral=True,
                )
                return
            if config.get("enabled"):
                await interaction.response.send_message(
                    embed=EmbedBuilder.error_user("O Starboard já está ativo.").build(),
                    ephemeral=True,
                )
                return
            await self.service.save_config(
                interaction.guild_id,
                config["channel_id"],
                config["emoji"],
                config["min_stars"],
                enabled=1,
            )
            await self.refresh(interaction, success="Starboard ativado com sucesso!")

        elif action == "disable":
            if not config or not config.get("enabled"):
                await interaction.response.send_message(
                    embed=EmbedBuilder.error_user("O Starboard já está desativado.").build(),
                    ephemeral=True,
                )
                return
            await self.service.disable_starboard(interaction.guild_id)
            await self.refresh(interaction, success="Starboard desativado.")

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass


# ── Cog ───────────────────────────────────────────────────────


class StarboardCog(commands.Cog, name="Starboard"):
    """Sistema de Starboard (Destaques do servidor)."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service = bot.container.starboard_service

    # ── Comando único ─────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(
        name="starboard",
        description="Painel de configuração do Starboard (mural de destaques).",
    )
    async def starboard_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        view = StarboardConfigView(self.service, interaction.guild, interaction.user.id)
        embed = await view._build_embed()
        msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        view.message = msg

    # ── Listeners de Reações ──────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id or payload.user_id == self.bot.user.id:
            return
        await self._handle_reaction_change(payload, is_add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if not payload.guild_id or payload.user_id == self.bot.user.id:
            return
        await self._handle_reaction_change(payload, is_add=False)

    async def _handle_reaction_change(
        self, payload: discord.RawReactionActionEvent, is_add: bool
    ) -> None:
        channel = self.bot.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden):
            return

        target_reaction = None
        for reaction in message.reactions:
            if str(reaction.emoji) == str(payload.emoji):
                target_reaction = reaction
                break

        raw_count = target_reaction.count if target_reaction else 0

        author_reacted = False
        if target_reaction:
            try:
                async for user in target_reaction.users():
                    if user.id == message.author.id:
                        author_reacted = True
                        break
            except Exception:
                pass

        effective_count = raw_count
        if author_reacted:
            effective_count = max(0, raw_count - 1)

        res = await self.service.process_reaction(
            guild_id=payload.guild_id,
            message_id=payload.message_id,
            author_id=message.author.id,
            reactor_id=payload.user_id,
            reaction_emoji=str(payload.emoji),
            reaction_count=effective_count,
        )

        action = res.get("action")
        if action in ("none", "self_star"):
            return

        starboard_chan_id = res.get("channel_id")
        starboard_channel = self.bot.get_channel(starboard_chan_id)
        if not isinstance(starboard_channel, discord.TextChannel):
            return

        emoji = res.get("emoji", "⭐")
        count = res.get("count", 0)

        if action == "create":
            embed = self._build_starboard_embed(message)
            content = f"{emoji} **{count}** | {channel.mention} | ID: {message.id}"
            try:
                starboard_msg = await starboard_channel.send(content=content, embed=embed)
                await self.service.register_starred_message(
                    message.id,
                    starboard_msg.id,
                    payload.guild_id,
                    starboard_chan_id,
                    count,
                )
            except discord.Forbidden:
                self.bot.logger.warning(
                    "Sem permissão para enviar no canal Starboard do servidor %s",
                    payload.guild_id,
                )

        elif action == "update":
            starboard_msg_id = res.get("starboard_message_id")
            try:
                starboard_msg = await starboard_channel.fetch_message(starboard_msg_id)
                content = f"{emoji} **{count}** | {channel.mention} | ID: {message.id}"
                await starboard_msg.edit(content=content)
                await self.service.update_starred_count(message.id, count)
            except discord.NotFound:
                await self.service.remove_starred_message(message.id)
            except discord.Forbidden:
                pass

        elif action == "delete":
            starboard_msg_id = res.get("starboard_message_id")
            try:
                starboard_msg = await starboard_channel.fetch_message(starboard_msg_id)
                await starboard_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
            finally:
                await self.service.remove_starred_message(message.id)

    def _build_starboard_embed(self, message: discord.Message) -> discord.Embed:
        """Monta um embed limpo e bonito para a postagem no Starboard."""
        embed = (
            EmbedBuilder.default()
            .description(message.content)
            .author(message.author.display_name, message.author.display_avatar.url)
            .footer(f"Enviado em #{message.channel.name}")
        )

        embed.field(
            name="Mensagem Original",
            value=f"[Clique aqui para ir para a mensagem]({message.jump_url})",
        )

        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    embed.image(attachment.url)
                    break

        return embed.build()


async def setup(bot: LunaBot) -> None:
    await bot.add_cog(StarboardCog(bot))
