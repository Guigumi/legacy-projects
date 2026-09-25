"""
Cog de configuração do AutoRole — interface interativa para admins.
Fluxo: autorole → lista + botão "Criar" → menu de modo → modal com campos → criado.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotEmojis
from core.utils.embed_builder import EmbedBuilder
from core.enums import AutoRoleMode
from features.admin.ui.autorole_ui import (
    AutoRoleManagerView,
    AutoRoleManageItemView,
    _can_manage_role,
    _fmt_duration
)

MODE_ICONS = {
    "instant": BotEmojis.AUTOROLE_INSTANT,
    "timer": BotEmojis.AUTOROLE_TIMER,
    "button": BotEmojis.AUTOROLE_BUTTON,
    "reaction": BotEmojis.AUTOROLE_REACTION,
}

async def _build_list_embed(bot: commands.Bot, guild: discord.Guild) -> discord.Embed:
    """Constrói o embed da lista de autoroles."""
    svc = bot.autorole_service
    entries = await svc.get_all(guild.id)

    if not entries:
        return (
            EmbedBuilder.default()
            .section("AutoRole")
            .description(
                "Nenhum autorole configurado ainda.\n\n"
                f"Clique em **{BotEmojis.ACTION_CREATE} Criar AutoRole** para começar!"
            )
            .footer("AutoRole — gerenciamento de cargos automáticos")
            .build()
        )

    lines = []
    for e in entries:
        role = guild.get_role(e["role_id"])
        role_name = role.mention if role else f"*(ID: {e['role_id']})*"
        status = BotEmojis.STATUS_ENABLED if e["enabled"] else BotEmojis.STATUS_DISABLED
        icon = MODE_ICONS.get(e["mode"], "•")
        mode = e["mode"].title()

        extra = ""
        if e["mode"] == "timer":
            extra = f" ({_fmt_duration(e['delay_seconds'])})"
        elif e["mode"] in ("button", "reaction"):
            ch = guild.get_channel(e["channel_id"]) if e["channel_id"] else None
            extra = f" em {ch.mention}" if ch else ""

        lines.append(f"{status} `#{e['id']}` {icon} **{mode}**{extra} → {role_name}")

    return (
        EmbedBuilder.default()
        .section("AutoRole — Configurações")
        .description("\n".join(lines))
        .footer("Criar • Atualizar • Selecione abaixo para gerenciar")
        .build()
    )


class AutoRoleSetupCog(commands.Cog):
    """Comandos de configuração do AutoRole — interface interativa."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(
        name="autorole", description="Configurar cargo automático", fallback="list"
    )
    @commands.has_permissions(administrator=True)
    async def autorole_group(self, ctx: commands.Context) -> None:
        """Painel interativo de gerenciamento de AutoRole."""
        embed = await _build_list_embed(self.bot, ctx.guild)
        entries = await self.bot.autorole_service.get_all(ctx.guild.id)

        view = AutoRoleManagerView(self.bot, ctx.guild.id, ctx.author.id)

        if entries:
            manage_view = AutoRoleManageItemView(self.bot, entries, ctx.author.id)
            for item in manage_view.children:
                item.row = 1
                view.add_item(item)

        await ctx.send(embed=embed, view=view)

    @autorole_group.command(
        name="instant", description="Cargo dado imediatamente ao entrar"
    )
    @app_commands.describe(role="Cargo a ser dado automaticamente")
    @commands.has_permissions(administrator=True)
    async def instant(self, ctx: commands.Context, role: discord.Role) -> None:
        if not _can_manage_role(ctx.guild, role):
            await ctx.send(embed=EmbedBuilder.error_user(f"Não consigo gerenciar {role.mention}.").build())
            return

        ar_id = await self.bot.autorole_service.create_autorole(ctx.guild.id, role.id, AutoRoleMode.INSTANT, ctx.author.id)
        await ctx.send(embed=EmbedBuilder.success(f"AutoRole criado! `#{ar_id}`").field("Cargo", role.mention).build())

    @autorole_group.command(
        name="timer", description="Cargo dado após um tempo de espera"
    )
    @app_commands.describe(role="Cargo a ser dado", seconds="Tempo em segundos")
    @commands.has_permissions(administrator=True)
    async def timer(
        self, ctx: commands.Context, role: discord.Role, seconds: int
    ) -> None:
        if not _can_manage_role(ctx.guild, role):
            await ctx.send(embed=EmbedBuilder.error_user(f"Não consigo gerenciar {role.mention}.").build())
            return
        if seconds < 5 or seconds > 604800:
            await ctx.send(embed=EmbedBuilder.error_user("Tempo deve ser entre 5s e 7 dias.").build())
            return

        ar_id = await self.bot.autorole_service.create_autorole(ctx.guild.id, role.id, AutoRoleMode.TIMER, ctx.author.id, delay_seconds=seconds)
        await ctx.send(embed=EmbedBuilder.success(f"AutoRole criado! `#{ar_id}`").field("Cargo", role.mention).field("Delay", _fmt_duration(seconds)).build())

    @autorole_group.command(
        name="toggle", description="Ativar ou desativar um autorole"
    )
    @app_commands.describe(autorole_id="ID do autorole")
    @commands.has_permissions(administrator=True)
    async def toggle(self, ctx: commands.Context, autorole_id: int) -> None:
        ar = await self.bot.autorole_repo.get_autorole(autorole_id)
        if not ar or ar["guild_id"] != ctx.guild.id:
            await ctx.send(embed=EmbedBuilder.error_user("AutoRole não encontrado.").build())
            return
        new_state = not ar["enabled"]
        await self.bot.autorole_service.toggle_autorole(autorole_id, new_state)
        await ctx.send(embed=EmbedBuilder.success(f"AutoRole `#{autorole_id}` foi {'ativado' if new_state else 'desativado'}.").build())

    @autorole_group.command(
        name="remove", description="Remover uma configuração de autorole"
    )
    @app_commands.describe(autorole_id="ID do autorole")
    @commands.has_permissions(administrator=True)
    async def remove(self, ctx: commands.Context, autorole_id: int) -> None:
        ar = await self.bot.autorole_repo.get_autorole(autorole_id)
        if not ar or ar["guild_id"] != ctx.guild.id:
            await ctx.send(embed=EmbedBuilder.error_user("AutoRole não encontrado.").build())
            return
        await self.bot.autorole_service.delete_autorole(autorole_id)
        await ctx.send(embed=EmbedBuilder.success(f"AutoRole `#{autorole_id}` removido.").build())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoRoleSetupCog(bot))
