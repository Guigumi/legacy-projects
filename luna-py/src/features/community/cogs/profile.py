"""
Cog de perfil — visualização de perfil individual com botões interativos.
"""

from __future__ import annotations

import datetime
import time
import io

import discord
from discord import app_commands
from discord.ext import commands

from core.utils.embed_builder import EmbedBuilder
from core.utils.formatters import fmt_voice
from core.utils.dev_edit import inject_dev_edit
from config.settings import BotEmojis, OWNER_ID

# Cache leve de fetch_user: user_id → (User, timestamp)
_FETCH_USER_CACHE: dict[int, tuple[discord.User, float]] = {}
_FETCH_USER_TTL = 300.0  # 5 minutos


def _get_hypesquad_emoji(member: discord.User | discord.Member) -> str | None:
    """Retorna emoji HypeSquad se o usuário tiver badge ativo."""
    if not getattr(member, "public_flags", None):
        return None

    if member.public_flags.hypesquad_bravery:
        return BotEmojis.COMMON_BRAVERY
    elif member.public_flags.hypesquad_brilliance:
        return BotEmojis.COMMON_BRILLANCE
    elif member.public_flags.hypesquad_balance:
        return BotEmojis.COMMON_BALANCE

    return None


class ProfileView(discord.ui.View):
    """View interativa com abas para navegar o perfil."""

    def __init__(
        self,
        data: dict,
        member: discord.User | discord.Member,
        author_id: int,
        card_bytes: bytes | None = None,
        is_gif: bool = False,
    ) -> None:
        super().__init__(timeout=120)
        self.data = data
        self.member = member
        self.author_id = author_id
        self.card_bytes = card_bytes
        self.is_gif = is_gif
        self.page = "card" if card_bytes else "avatar"
        self.message: discord.Message | None = None

        
        # Adicionar o botão HD Link
        self.add_item(discord.ui.Button(
            label="Avatar HD",
            style=discord.ButtonStyle.link,
            url=str(self.member.display_avatar.with_size(4096).url)
        ))
        self._update_styles()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    def _build_avatar_embed(self) -> discord.Embed:
        banner_url = self.member.banner.url if getattr(self.member, "banner", None) else None

        # Verificar badge HypeSquad
        hypesquad_emoji = _get_hypesquad_emoji(self.member)
        hypesquad_suffix = f" {hypesquad_emoji}" if hypesquad_emoji else ""

        builder = (
            EmbedBuilder.default()
            .author(
                name=self.member.display_name,
                icon_url=self.member.display_avatar.url,
            )
            .thumbnail(self.member.display_avatar.with_size(512).url)
            .field(f"{BotEmojis.COMMON_USER} Nome", f"`{str(self.member)}`{hypesquad_suffix}", inline=True)
            .field(f"{BotEmojis.COMMON_ID} ID", f"`{self.member.id}`", inline=True)
        )

        if banner_url:
            builder.image(banner_url)

        return builder.build()

    def _build_card_embed(self) -> discord.Embed:
        ext = "gif" if getattr(self, "is_gif", False) else "png"
        return (
            EmbedBuilder.default()
            .image(f"attachment://profile_card.{ext}")
            .build()
        )

    def _update_styles(self) -> None:
        self.card_btn.disabled = self.card_bytes is None
        self.card_btn.style = (
            discord.ButtonStyle.primary
            if self.page == "card"
            else discord.ButtonStyle.secondary
        )
        self.avatar_btn.style = (
            discord.ButtonStyle.primary
            if self.page == "avatar"
            else discord.ButtonStyle.secondary
        )

    @discord.ui.button(label="Card", style=discord.ButtonStyle.primary, emoji=BotEmojis.COMMON_PROFILE)
    async def card_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page = "card"
        self._update_styles()
        if self.card_bytes:
            file = discord.File(io.BytesIO(self.card_bytes), filename="profile_card.png")
            await interaction.response.edit_message(
                embed=self._build_card_embed(),
                attachments=[file],
                view=self
            )
        else:
            # Fallback seguro caso não tenha imagem em cache
            await interaction.response.edit_message(
                embed=self._build_avatar_embed(),
                attachments=[],
                view=self
            )

    @discord.ui.button(label="Avatar / Banner", style=discord.ButtonStyle.secondary, emoji=BotEmojis.COMMON_IMAGE)
    async def avatar_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page = "avatar"
        self._update_styles()
        await interaction.response.edit_message(
            embed=self._build_avatar_embed(),
            attachments=[],
            view=self
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            if not isinstance(item, discord.ui.Button) or item.style != discord.ButtonStyle.link:
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class ProfileCog(commands.Cog):
    """Comando de perfil de usuário."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _show_profile(
        self, interaction: discord.Interaction, target: discord.Member
    ) -> None:
        user_svc = self.bot.user_service
        data = await user_svc.get_profile(interaction.guild_id, target.id)
        
        if not data:
            embed = EmbedBuilder.error_user("Não encontrei dados para esse membro.").build()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Fetch completo para banner (cache)
        now = time.monotonic()
        cached = _FETCH_USER_CACHE.get(target.id)
        if cached and (now - cached[1]) < _FETCH_USER_TTL:
            target_with_banner = cached[0]
        else:
            try:
                fetched = await self.bot.fetch_user(target.id)
                _FETCH_USER_CACHE[target.id] = (fetched, now)
                target_with_banner = fetched
            except:
                target_with_banner = target

        # Formatar a data de entrada no servidor
        joined_dt = target.joined_at
        if joined_dt:
            joined_str = joined_dt.strftime("%d/%m/%Y")
        else:
            joined_str = target.created_at.strftime("%d/%m/%Y")

        # Tentar obter as informações de XP necessárias
        xp_current = data.xp - (data.xp_current_level or 0)
        xp_needed = (data.xp_next_level or 100) - (data.xp_current_level or 0)
        if xp_needed <= 0:
            xp_needed = 100

        # Tentar renderizar o Profile Card usando Pillow
        card_bytes = None
        banner_url = target_with_banner.banner.url if getattr(target_with_banner, "banner", None) else None
        theme = data.selected_theme or "default"
        from features.community.utils.xp_card_generator import BACKGROUNDS
        is_gif = False
        if theme in BACKGROUNDS:
            is_gif = BACKGROUNDS[theme]["bg_image"].endswith(".gif")

        try:
            from features.community.utils.xp_card_generator import generate_profile_card
            fp = await generate_profile_card(
                username=target.display_name,
                user_id=target.id,
                messages_sent=data.messages_sent,
                voice_seconds=data.voice_seconds,
                warnings=data.warnings,
                joined_date=joined_str,
                level=data.level,
                xp_current=xp_current,
                xp_needed=xp_needed,
                avatar_url=target.display_avatar.url,
                banner_url=banner_url,
                theme_name=theme,
                coins=data.coins,
            )

            card_bytes = fp.getvalue()
        except Exception:
            self.bot.logger.exception("Falha ao gerar profile card Pillow, usando fallback de texto")

        view = ProfileView(data, target_with_banner, interaction.user.id, card_bytes=card_bytes, is_gif=is_gif)
        view._update_styles()

        inject_dev_edit(
            view, bot=self.bot, table="user_data",
            pk_values={"guild_id": interaction.guild_id, "user_id": target.id},
            fields=[
                {"name": "messages_sent", "label": "Mensagens", "value": data["messages_sent"]},
                {"name": "voice_seconds", "label": "Voice (s)", "value": data["voice_seconds"]},
                {"name": "xp", "label": "XP", "value": data.get("xp", 0)},
                {"name": "level", "label": "Nível", "value": data.get("level", 1)},
                {"name": "warnings", "label": "Avisos", "value": data.get("warnings", 0)},
            ],
            modal_title=f"Editar {target.display_name}",
        )

        if card_bytes:
            ext = "gif" if is_gif else "png"
            file = discord.File(io.BytesIO(card_bytes), filename=f"profile_card.{ext}")
            embed = view._build_card_embed()
            await interaction.response.send_message(embed=embed, file=file, view=view)
        else:
            embed = view._build_avatar_embed()
            await interaction.response.send_message(embed=embed, view=view)

        view.message = await interaction.original_response()


    @commands.hybrid_command(
        name="profile", description="Veja seu perfil ou o de outro membro"
    )
    @app_commands.describe(member="O membro cujo perfil deseja ver")
    async def profile(
        self, ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        target = member or ctx.author
        if ctx.interaction:
            await self._show_profile(ctx.interaction, target)
        else:
            await self._legacy_profile(ctx, target)

    async def _legacy_profile(self, ctx: commands.Context, target: discord.Member) -> None:
        user_svc = self.bot.user_service
        data = await user_svc.get_profile(ctx.guild.id, target.id)
        if not data:
            await ctx.send(embed=EmbedBuilder.error_user("Dados não encontrados.").build())
            return
        
        now = time.monotonic()
        target_with_banner = target
        try:
            fetched = await self.bot.fetch_user(target.id)
            target_with_banner = fetched
        except:
            pass

        # Formatar a data de entrada no servidor
        joined_dt = target.joined_at
        if joined_dt:
            joined_str = joined_dt.strftime("%d/%m/%Y")
        else:
            joined_str = target.created_at.strftime("%d/%m/%Y")

        xp_current = data.xp - (data.xp_current_level or 0)
        xp_needed = (data.xp_next_level or 100) - (data.xp_current_level or 0)
        if xp_needed <= 0:
            xp_needed = 100

        card_bytes = None
        banner_url = target_with_banner.banner.url if getattr(target_with_banner, "banner", None) else None
        theme = data.selected_theme or "default"

        from features.community.utils.xp_card_generator import BACKGROUNDS
        is_gif = False
        if theme in BACKGROUNDS:
            is_gif = BACKGROUNDS[theme]["bg_image"].endswith(".gif")

        try:
            from features.community.utils.xp_card_generator import generate_profile_card
            fp = await generate_profile_card(
                username=target.display_name,
                user_id=target.id,
                messages_sent=data.messages_sent,
                voice_seconds=data.voice_seconds,
                warnings=data.warnings,
                joined_date=joined_str,
                level=data.level,
                xp_current=xp_current,
                xp_needed=xp_needed,
                avatar_url=target.display_avatar.url,
                banner_url=banner_url,
                theme_name=theme,
                coins=data.coins,
            )


            card_bytes = fp.getvalue()
        except Exception:
            self.bot.logger.exception("Falha ao gerar profile card Pillow, usando fallback de texto")

        view = ProfileView(data, target_with_banner, ctx.author.id, card_bytes=card_bytes, is_gif=is_gif)
        view._update_styles()
        
        inject_dev_edit(view, bot=self.bot, table="user_data",
            pk_values={"guild_id": ctx.guild.id, "user_id": target.id},
            fields=[
                {"name": "messages_sent", "label": "Mensagens", "value": data["messages_sent"]},
                {"name": "voice_seconds", "label": "Voice (s)", "value": data["voice_seconds"]},
                {"name": "xp", "label": "XP", "value": data.get("xp", 0)},
                {"name": "level", "label": "Nível", "value": data.get("level", 1)},
                {"name": "warnings", "label": "Avisos", "value": data.get("warnings", 0)},
            ],
            modal_title=f"Editar {target.display_name}",
        )

        if card_bytes:
            ext = "gif" if is_gif else "png"
            file = discord.File(io.BytesIO(card_bytes), filename=f"profile_card.{ext}")
            embed = view._build_card_embed()
            msg = await ctx.send(embed=embed, file=file, view=view)
        else:
            embed = view._build_avatar_embed()
            msg = await ctx.send(embed=embed, view=view)
            
        view.message = msg


# ── Context Menus (devem ser definidos no módulo, não na classe) ────────────

@app_commands.context_menu(name="Ver Perfil")
async def profile_context_menu(interaction: discord.Interaction, member: discord.Member) -> None:
    cog: ProfileCog | None = interaction.client.cogs.get("ProfileCog")  # type: ignore
    if cog:
        await cog._show_profile(interaction, member)


@app_commands.context_menu(name="Ver XP")
async def xp_context_menu(interaction: discord.Interaction, member: discord.Member) -> None:
    cog: ProfileCog | None = interaction.client.cogs.get("ProfileCog")  # type: ignore
    if cog:
        await cog._show_profile(interaction, member)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
    bot.tree.add_command(profile_context_menu)
    bot.tree.add_command(xp_context_menu)

