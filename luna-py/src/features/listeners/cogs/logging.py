"""
Cog de logging — camada fina de listeners.
Escuta eventos do Discord e do EventBus e delega ao LoggingService.
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from core.events import BotEvent
from core.enums import LOG_CATEGORY_META, LogCategory
from config.settings import BotEmojis

logger = logging.getLogger(__name__)

# ── View de configuração ──────────────────────────────────────


class LogConfigView(discord.ui.View):
    """Painel interativo para configurar categorias de log."""

    def __init__(
        self,
        bot: LunaBot,
        guild_id: int,
        author_id: int,
        disabled_cats: set[str],
        log_channel_id: int | None,
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id
        self.author_id = author_id
        self.disabled_cats = disabled_cats
        self.log_channel_id = log_channel_id
        self._build_select()

    def _build_select(self) -> None:
        """Monta o select menu com o estado atual."""
        for item in list(self.children):
            if isinstance(item, discord.ui.Select):
                self.remove_item(item)

        select = discord.ui.Select(
            placeholder="Selecione categorias para alternar...",
            min_values=1,
            max_values=len(LogCategory),
            row=0,
        )

        for cat in LogCategory:
            emoji, label = LOG_CATEGORY_META[cat]
            enabled = cat.value not in self.disabled_cats
            select.add_option(
                label=label,
                value=cat.value,
                emoji=emoji,
                description=(
                    f"{BotEmojis.BOX_CHECK} Ativada"
                    if enabled
                    else f"{BotEmojis.BOX_OFF} Desativada"
                ),
            )

        select.callback = self._on_select
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    def _build_embed(self) -> discord.Embed:
        """Constrói o embed com o status atual."""
        lines: list[str] = []
        for cat in LogCategory:
            emoji, label = LOG_CATEGORY_META[cat]
            enabled = cat.value not in self.disabled_cats
            status = BotEmojis.BOX_CHECK if enabled else BotEmojis.BOX_OFF
            lines.append(f"{status} {emoji} **{label}**")

        if self.log_channel_id:
            channel_info = f"{BotEmojis.COMMON_LIST} Canal de logs: <#{self.log_channel_id}>"
        else:
            channel_info = (
                f"{BotEmojis.BOX_NONE} Nenhum canal de logs definido. "
                "Use `!log #canal`"
            )

        return (
            EmbedBuilder.default()
            .author(name="Configuração de Logs")
            .description(
                f"{channel_info}\n\n"
                "Selecione as categorias abaixo para **ativar/desativar**.\n"
                "Cada categoria controla um tipo de evento no canal de logs.\n\n"
                + "\n".join(lines)
            )
            .footer("Clique nas categorias no menu para alternar")
            .build()
        )

    async def _on_select(self, interaction: discord.Interaction) -> None:
        selected = interaction.data["values"]
        guild_svc = self.bot.guild_service

        for cat_value in selected:
            if cat_value in self.disabled_cats:
                await guild_svc.toggle_log_category(
                    self.guild_id,
                    cat_value,
                    True,
                    interaction.user.id,
                )
                self.disabled_cats.discard(cat_value)
            else:
                await guild_svc.toggle_log_category(
                    self.guild_id,
                    cat_value,
                    False,
                    interaction.user.id,
                )
                self.disabled_cats.add(cat_value)

        self._build_select()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class LoggingCog(commands.Cog):
    """Listeners que delegam toda a lógica ao LoggingService."""

    # Eventos internos que este cog efetivamente loga
    _LOGGED_EVENTS = frozenset({
        BotEvent.CONFIG_CHANGED,
        BotEvent.FEATURE_TOGGLED,
        BotEvent.WARNING_ISSUED,
        BotEvent.USER_LEVELED_UP,
        BotEvent.AUTOROLE_GIVEN,
        BotEvent.AUTOROLE_CONFIG,
        BotEvent.NOTIFICATION_CREATED,
    })

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service = bot.logging_service
        for event_type in self._LOGGED_EVENTS:
            self.bot.event_bus.subscribe(event_type, self._on_internal_event)

        self._old_tree_on_error = bot.tree.on_error
        bot.tree.on_error = self.on_app_command_error

    def cog_unload(self) -> None:
        for event_type in self._LOGGED_EVENTS:
            try:
                self.bot.event_bus.unsubscribe(event_type, self._on_internal_event)
            except ValueError:
                pass
        self.bot.tree.on_error = self._old_tree_on_error

    # ── EventBus ──────────────────────────────────────────────

    async def _on_internal_event(
        self,
        guild_id: int,
        event_type: BotEvent,
        data: dict[str, Any],
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        await self.service.log_internal_event(guild, event_type, data)

    # ── Mensagens ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        await self.service.log_message_delete(message)

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return
        await self.service.log_message_edit(before, after)

    # ── Voz ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        await self.service.log_voice_update(member, before, after)

    # ── Membros ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        await self.service.log_member_join(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        await self.service.log_member_remove(member)

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        if before.bot:
            return
        await self.service.log_member_update(before, after)

    # ── Canais ────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self.service.log_channel_create(channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self.service.log_channel_delete(channel)

    # ── Cargos ────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self.service.log_role_create(role)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self.service.log_role_delete(role)

    # ── Ban / Unban ───────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        await self.service.log_member_ban(guild, user)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        await self.service.log_member_unban(guild, user)

    # ── Comandos de configuração ──────────────────────────────

    @commands.hybrid_command(
        name="log",
        description="Configurar canal e categorias de logs",
        aliases=["logchannel", "logs"],
    )
    @app_commands.describe(channel="Canal para logs (omita para abrir o painel)")
    @commands.has_permissions(administrator=True)
    async def logchannel_cmd(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | None = None,
    ) -> None:
        guild_svc = self.bot.guild_service

        # Se passou canal, define e confirma
        if channel is not None:
            await guild_svc.update_config(
                ctx.guild.id,
                changed_by=ctx.author.id,
                log_channel=channel.id,
            )
            embed = (
                EmbedBuilder.success(f"Canal de logs definido para {channel.mention}")
                .description(
                    "Use `!log` (sem canal) para configurar quais categorias enviar."
                )
                .build()
            )
            await ctx.send(embed=embed)
            return

        # Sem canal → abrir painel de categorias
        config = await guild_svc.get_config(ctx.guild.id)
        log_channel_id = config.get("log_channel") if config else None
        disabled = set(await guild_svc.get_disabled_log_categories(ctx.guild.id))

        view = LogConfigView(
            self.bot,
            ctx.guild.id,
            ctx.author.id,
            disabled,
            log_channel_id,
        )
        msg = await ctx.send(embed=view._build_embed(), view=view)
        view.message = msg

    @commands.hybrid_command(
        name="log-weekly",
        description="Gera e envia o resumo semanal agora (apenas para teste/manual)",
    )
    @commands.has_permissions(administrator=True)
    async def log_weekly_cmd(self, ctx: commands.Context) -> None:
        await ctx.defer(ephemeral=True)
        await self.bot.weekly_log_service.send_weekly_log(ctx.guild)
        await ctx.send("Resumo semanal enviado para o canal de logs.", ephemeral=True)

    # ── Command execution logging listeners ───────────────────

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: discord.app_commands.Command | discord.app_commands.ContextMenu,
    ) -> None:
        duration_ms = (discord.utils.utcnow() - interaction.created_at).total_seconds() * 1000
        logger.info(
            "Comando executado",
            extra={
                "command": command.qualified_name,
                "guild_id": interaction.guild_id,
                "user_id": interaction.user.id,
                "duration_ms": round(duration_ms, 2),
                "status": "success",
            }
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        duration_ms = (discord.utils.utcnow() - interaction.created_at).total_seconds() * 1000
        command_name = interaction.command.qualified_name if interaction.command else "?"
        
        logger.error(
            "Erro na execução do comando",
            exc_info=error,
            extra={
                "command": command_name,
                "guild_id": interaction.guild_id,
                "user_id": interaction.user.id,
                "duration_ms": round(duration_ms, 2),
                "status": "error",
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        )
        
        try:
            if isinstance(error, discord.app_commands.CommandOnCooldown):
                message = f"Relaxe! Tente novamente em {error.retry_after:.0f}s."
            elif isinstance(error, discord.app_commands.MissingPermissions):
                message = "Este é um comando de **administrador**.\nVocê não tem permissão para executá-lo."
            elif isinstance(error, discord.app_commands.BotMissingPermissions):
                perms = ", ".join(error.missing_permissions)
                message = f"Preciso das seguintes permissões: **{perms}**"
            else:
                message = "Ocorreu um erro inesperado ao executar este comando."
                
            embed = EmbedBuilder.error_user(message).build()
            
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context) -> None:
        duration_ms = (discord.utils.utcnow() - ctx.message.created_at).total_seconds() * 1000
        command_name = ctx.command.qualified_name if ctx.command else "?"
        logger.info(
            "Comando executado",
            extra={
                "command": command_name,
                "guild_id": ctx.guild.id if ctx.guild else None,
                "user_id": ctx.author.id,
                "duration_ms": round(duration_ms, 2),
                "status": "success",
            }
        )

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
            
        duration_ms = (discord.utils.utcnow() - ctx.message.created_at).total_seconds() * 1000
        command_name = ctx.command.qualified_name if ctx.command else "?"
        
        logger.error(
            "Erro na execução do comando",
            exc_info=error,
            extra={
                "command": command_name,
                "guild_id": ctx.guild.id if ctx.guild else None,
                "user_id": ctx.author.id,
                "duration_ms": round(duration_ms, 2),
                "status": "error",
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LoggingCog(bot))
