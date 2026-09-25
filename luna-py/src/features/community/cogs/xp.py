"""
Cog de XP — visualização do progresso de XP, nível e próximo cargo.
Comando: !xp ou /xp
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import BotEmojis, Separators, OWNER_ID
from core.utils.embed_builder import EmbedBuilder
from core.utils.dev_edit import inject_dev_edit
from features.community.utils.xp_card_generator import (
    generate_rank_card,
    generate_ranks_tree,
)



def _progress_bar(current: int, total: int, length: int = 16) -> str:
    """Gera barra de progresso visual."""
    if total <= 0:
        return "█" * length
    filled = int(length * current / total)
    filled = min(filled, length)
    empty = length - filled
    return "█" * filled + "░" * empty


# ── View QOL ──────────────────────────────────────────────────


class XPView(discord.ui.View):
    """Botões rápidos após !xp."""

    def __init__(
        self,
        bot: commands.Bot,
        author_id: int,
        target: discord.Member,
        initial_embed: discord.Embed,
        *,
        timeout: float = 120,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.target = target
        self.message: discord.Message | None = None
        self.initial_embed = initial_embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode interagir."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    async def _disable_all(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(
        label="Leaderboard", emoji=BotEmojis.COMMON_LIST, style=discord.ButtonStyle.primary, row=0
    )
    async def btn_lb(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        from features.community.cogs.leaderboard import LeaderboardView
        view = LeaderboardView(self.bot, interaction.guild, self.author_id)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(
        label="Perfil",
        emoji=BotEmojis.COMMON_USER,
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def btn_profile(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        from features.community.cogs.profile import ProfileView
        
        user_svc = self.bot.user_service
        data = await user_svc.get_profile(interaction.guild.id, self.target.id)
        if not data:
            return
            
        view = ProfileView(data, self.target, self.author_id)
        view._set_avatar_url()
        view._update_styles()
        embed = view._build_avatar_embed()
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()




class ThemeHubSelect(discord.ui.Select):
    def __init__(self, themes_list: list[dict], current_id: str):
        options = []
        for t in themes_list:
            if t["type"] == "base":
                label = f"{t['name']} (Nível {t['level']}+)"
            else:
                label = f"{t['name']} (Premium)"
            options.append(discord.SelectOption(
                label=label,
                value=t["id"],
                default=(t["id"] == current_id),
                description="Tema gratuito de Nível" if t["type"] == "base" else "Fundo de Loja (5.000 moedas)"
            ))
        super().__init__(placeholder="Selecione um tema para ver a prévia...", options=options, row=3)

    async def callback(self, interaction: discord.Interaction):
        await self.view.change_theme_by_id(interaction, self.values[0])


class ThemeHubView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        author_id: int,
        guild_id: int,
        profile_data: any,
        joined_str: str,
        avatar_url: str,
        banner_url: str | None = None,
    ):
        super().__init__(timeout=180)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id
        self.profile_data = profile_data
        self.joined_str = joined_str
        self.avatar_url = avatar_url
        self.banner_url = banner_url
        self.message: discord.Message | None = None

        # Dados de moedas e comprados
        self.coins = profile_data.coins
        self.unlocked = [x.strip() for x in profile_data.unlocked_backgrounds.split(",") if x.strip()]

        # Lista de todos os temas do bot
        self.all_themes = [
            {"id": "default", "name": "Clássico", "type": "base", "level": 0},
            {"id": "discord", "name": "Discord UI", "type": "base", "level": 5},
            {"id": "nature", "name": "Natureza", "type": "base", "level": 10},
            {"id": "ocean", "name": "Oceano", "type": "base", "level": 15},
            {"id": "amethyst", "name": "Ametista", "type": "base", "level": 30},
            {"id": "autumn", "name": "Outono", "type": "base", "level": 40},
            {"id": "fern", "name": "Fern", "type": "premium", "price": 5000},
            {"id": "galaxy", "name": "Galaxy", "type": "premium", "price": 5000},
            {"id": "hutao", "name": "Hu Tao", "type": "premium", "price": 5000},
            {"id": "kasaneteto", "name": "Kasane Teto", "type": "premium", "price": 5000},
            {"id": "luckystar", "name": "Lucky Star", "type": "premium", "price": 5000},
            {"id": "mikuteto", "name": "Miku & Teto", "type": "premium", "price": 5000},
            {"id": "robin", "name": "Robin", "type": "premium", "price": 5000},
            # {"id": "agnestachyon", "name": "Agnes Tachyon", "type": "premium", "price": 25000},
        ]


        # Estado do filtro
        self.filter_mode = "all"
        self.filtered_themes = self.all_themes.copy()
        
        # Encontra índice inicial baseado no tema equipado
        equipped_theme = profile_data.selected_theme or "default"
        self.current_index = 0
        for i, t in enumerate(self.all_themes):
            if t["id"] == equipped_theme:
                self.current_index = i
                break

        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            embed = EmbedBuilder.error_user(
                "Apenas quem usou o comando pode navegar no Hub de Temas."
            ).build()
            await interaction.response.send_message(embed=embed, delete_after=5.0)
            return False
        return True

    def get_current_theme(self) -> dict:
        if 0 <= self.current_index < len(self.filtered_themes):
            return self.filtered_themes[self.current_index]
        return self.filtered_themes[0] if self.filtered_themes else self.all_themes[0]

    def update_components(self):
        # Remove dropdown antigo
        for item in list(self.children):
            if isinstance(item, ThemeHubSelect):
                self.remove_item(item)

        current_theme = self.get_current_theme()

        # Adiciona dropdown atualizado
        self.add_item(ThemeHubSelect(self.filtered_themes, current_theme["id"]))

        # Estilo dos botões de abas/filtros
        self.btn_all.style = discord.ButtonStyle.primary if self.filter_mode == "all" else discord.ButtonStyle.secondary
        self.btn_shop.style = discord.ButtonStyle.primary if self.filter_mode == "shop" else discord.ButtonStyle.secondary
        self.btn_owned.style = discord.ButtonStyle.primary if self.filter_mode == "owned" else discord.ButtonStyle.secondary

        is_premium = current_theme["type"] == "premium"
        is_unlocked = current_theme["id"] in self.unlocked

        # Configurar botão de comprar
        if is_premium and not is_unlocked:
            self.btn_buy.disabled = False
            self.btn_buy.label = f"Comprar ({current_theme['price']} moedas)"
            self.btn_buy.style = discord.ButtonStyle.success
        else:
            self.btn_buy.disabled = True
            self.btn_buy.label = "Comprar"
            self.btn_buy.style = discord.ButtonStyle.secondary

        # Configurar botão de equipar
        if is_premium:
            self.btn_equip.disabled = not is_unlocked
        else:
            self.btn_equip.disabled = self.profile_data.level < current_theme["level"]

        # Se já for o equipado
        if self.profile_data.selected_theme == current_theme["id"]:
            self.btn_equip.disabled = True
            self.btn_equip.label = "Equipado"
            self.btn_equip.style = discord.ButtonStyle.secondary
        else:
            self.btn_equip.label = "Equipar Tema"
            self.btn_equip.style = discord.ButtonStyle.primary

    def apply_filter(self, mode: str):
        self.filter_mode = mode
        if mode == "all":
            self.filtered_themes = self.all_themes.copy()
        elif mode == "shop":
            self.filtered_themes = [t for t in self.all_themes if t["type"] == "premium"]
        elif mode == "owned":
            self.filtered_themes = [
                t for t in self.all_themes 
                if (t["type"] == "base" and self.profile_data.level >= t["level"])
                or (t["type"] == "premium" and t["id"] in self.unlocked)
            ]

        if not self.filtered_themes:
            self.filtered_themes = [self.all_themes[0]]

        self.current_index = 0
        self.update_components()

    async def change_theme_by_id(self, interaction: discord.Interaction, theme_id: str):
        for idx, t in enumerate(self.filtered_themes):
            if t["id"] == theme_id:
                self.current_index = idx
                break
        await self.render_and_update(interaction)

    async def render_and_update(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        current_theme = self.get_current_theme()
        
        # Tenta renderizar o preview em memória
        try:
            from features.community.utils.xp_card_generator import BACKGROUNDS
            is_gif = False
            if current_theme["id"] in BACKGROUNDS:
                is_gif = BACKGROUNDS[current_theme["id"]]["bg_image"].endswith(".gif")

            xp_svc = self.bot.xp_config_service
            config = await xp_svc.get_config(self.guild_id)
            xp_per_level = config.get("xp_per_level", 100)
            
            xp_current_level = xp_svc.xp_for_level(self.profile_data.level, xp_per_level)
            xp_next_level = xp_svc.xp_for_level(self.profile_data.level + 1, xp_per_level)
            
            xp_in_level = self.profile_data.xp - xp_current_level
            xp_needed = xp_next_level - xp_current_level

            from features.community.utils.xp_card_generator import generate_profile_card
            fp = await generate_profile_card(
                username=self.profile_data.get("username", interaction.user.display_name),
                user_id=self.author_id,
                messages_sent=self.profile_data.messages_sent,
                voice_seconds=self.profile_data.voice_seconds,
                warnings=self.profile_data.warnings,
                joined_date=self.joined_str,
                level=self.profile_data.level,
                xp_current=xp_in_level,
                xp_needed=xp_needed,
                avatar_url=self.avatar_url,
                banner_url=self.banner_url,
                theme_name=current_theme["id"],
                coins=self.coins,
            )
            import io
            ext = "gif" if is_gif else "png"
            file = discord.File(io.BytesIO(fp.getvalue()), filename=f"theme_preview.{ext}")
        except Exception:
            self.bot.logger.exception("Falha ao gerar preview do hub")
            file = None

        self.update_components()

        is_premium = current_theme["type"] == "premium"
        is_unlocked = current_theme["id"] in self.unlocked

        if is_premium:
            status = "✅ Adquirido" if is_unlocked else f"🪙 Custo: **{current_theme['price']} moedas**"
        else:
            status = f"🔓 Desbloqueio: Nível {current_theme['level']}"

        status_equipped = " (Equipado)" if self.profile_data.selected_theme == current_theme["id"] else ""

        desc = (
            f"💰 Seu Saldo: **{self.coins:,} moedas**\n\n".replace(",", ".") +
            f"✨ **Tema**: {current_theme['name']} (`{current_theme['id']}`)\n"
            f"ℹ️ **Status**: {status}{status_equipped}\n\n"
            f"Use as setinhas `◀`/`▶` ou o dropdown abaixo para navegar pelos temas da loja e do seu inventário!"
        )

        embed = (
            EmbedBuilder.default()
            .title("🎨 Hub de Temas de Perfil")
            .description(desc)
        )
        if file:
            ext = "gif" if is_gif else "png"
            embed.image(f"attachment://theme_preview.{ext}")
            await interaction.followup.edit_message(
                message_id=self.message.id,
                embed=embed.build(),
                attachments=[file],
                view=self
            )
        else:
            await interaction.followup.edit_message(
                message_id=self.message.id,
                embed=embed.build(),
                attachments=[],
                view=self
            )


    @discord.ui.button(label="Todos", style=discord.ButtonStyle.primary, row=0)
    async def btn_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.apply_filter("all")
        await self.render_and_update(interaction)

    @discord.ui.button(label="Premium", style=discord.ButtonStyle.secondary, row=0)
    async def btn_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.apply_filter("shop")
        await self.render_and_update(interaction)

    @discord.ui.button(label="Obtidos", style=discord.ButtonStyle.secondary, row=0)
    async def btn_owned(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.apply_filter("owned")
        await self.render_and_update(interaction)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=2)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = (self.current_index - 1) % len(self.filtered_themes)
        await self.render_and_update(interaction)

    @discord.ui.button(label="Comprar", style=discord.ButtonStyle.success, row=2)
    async def btn_buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_theme = self.get_current_theme()
        is_dev = getattr(self.bot, "_dev_mode", False)
        price = 0 if is_dev else current_theme["price"]

        user_svc = self.bot.user_service
        try:
            new_coins = await user_svc.buy_background(self.guild_id, self.author_id, current_theme["id"], price)
            self.coins = new_coins
            self.unlocked.append(current_theme["id"])
            self.profile_data.unlocked_backgrounds = ",".join(self.unlocked)
            self.profile_data.coins = new_coins
            
            # Equipar automaticamente ao comprar
            await user_svc.set_user_theme(self.guild_id, self.author_id, current_theme["id"])
            self.profile_data.selected_theme = current_theme["id"]
            
            self.apply_filter(self.filter_mode)
            await self.render_and_update(interaction)

            await interaction.followup.send(
                embed=EmbedBuilder.success(f"Você comprou e equipou o tema **{current_theme['name']}**!").build(),
                ephemeral=True
            )
        except ValueError as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=EmbedBuilder.error_user(str(e)).build(),
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    embed=EmbedBuilder.error_user(str(e)).build(),
                    ephemeral=True
                )

    @discord.ui.button(label="Equipar Tema", style=discord.ButtonStyle.primary, row=2)
    async def btn_equip(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_theme = self.get_current_theme()
        user_svc = self.bot.user_service
        
        await user_svc.set_user_theme(self.guild_id, self.author_id, current_theme["id"])
        self.profile_data.selected_theme = current_theme["id"]
        
        await self.render_and_update(interaction)
        
        await interaction.followup.send(
            embed=EmbedBuilder.success(f"Tema alterado com sucesso para **{current_theme['name']}**!").build(),
            ephemeral=True
        )

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=2)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = (self.current_index + 1) % len(self.filtered_themes)
        await self.render_and_update(interaction)

    async def on_timeout(self) -> None:
        for item in self.children:
            if not isinstance(item, discord.ui.Button) or item.style != discord.ButtonStyle.link:
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class XPCog(commands.Cog):

    """Visualização de progresso de XP."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        from core.events import BotEvent
        
        if hasattr(self.bot, "event_bus"):
            self.bot.event_bus.subscribe(BotEvent.USER_LEVELED_UP, self._on_level_up)

    async def _on_level_up(self, guild_id: int, event_type, data: dict) -> None:
        """Envia mensagem de level up conforme configuração do servidor."""
        if not hasattr(self.bot, "xp_config_service"):
            return

        user_id = data.get("user_id")
        new_level = data.get("new_level")
        channel_id = data.get("channel_id")
        if not user_id or not new_level:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        member = guild.get_member(user_id)
        if not member:
            return

        config = await self.bot.xp_config_service.get_config(guild_id)
        mode = config.get("level_up_mode", "current")
        
        if mode == "disabled":
            return
            
        target_channel_id = None
        if mode == "specific":
            target_channel_id = config.get("level_up_channel_id")
        elif mode == "current":
            target_channel_id = channel_id
            
        if not target_channel_id:
            return

        channel = guild.get_channel(target_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return
            
        msg_text = config.get("level_up_message")
        if not msg_text:
            msg_text = "Parabéns {@user}! Você evoluiu para o **Nível {level}**!"
            
        msg_title = config.get("level_up_title") or f"{BotEmojis.COMMON_LVL_UP} Novo Nível Alcançado!"

        old_level = data.get("old_level", 0)
        earned_roles = []
        if old_level and new_level and new_level > old_level:
            # Optimization: Avoid N+1 queries by fetching all roles in the level range
            # in a single batch (via service which may use cache).
            new_roles = await self.bot.xp_config_service.get_roles_for_level_range(
                guild_id, old_level + 1, new_level
            )
            earned_roles = [f"<@&{lr['role_id']}>" for lr in new_roles]

        roles_mentions = " ".join(earned_roles)
        
        # Helper pra fazer os replaces repetitivos em qualquer string
        def apply_tags(text: str) -> str:
            text = text.replace("{@user}", member.mention)
            text = text.replace("{user}", member.display_name)
            text = text.replace("{level}", str(new_level))
            text = text.replace("{level_new}", str(new_level))
            text = text.replace("{level_old}", str(old_level))
            text = text.replace("{xp}", str(data.get("xp", 0)))
            return text

        msg_title = apply_tags(msg_title)
        msg_text = apply_tags(msg_text)

        if "{roles}" in msg_text:
            msg_text = msg_text.replace("{roles}", roles_mentions)
            
        if "{roles}" in msg_title:
            msg_title = msg_title.replace("{roles}", "") # Evita cargos quebrando o titulo limit 256.

        embed = (
            EmbedBuilder.default()
            .author(
                name=member.display_name,
                icon_url=member.display_avatar.url,
            )
            .title(msg_title)
            .description(msg_text)
            .build()
        )
        try:
            await channel.send(content=member.mention, embed=embed)
        except discord.HTTPException:
            pass

    @commands.hybrid_command(
        name="xp", description="Veja seu XP, nível e próximo cargo"
    )
    @app_commands.describe(member="O membro cujo XP deseja ver")
    async def xp_cmd(
        self, ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        target = member or ctx.author
        user_svc = self.bot.user_service
        xp_svc = self.bot.xp_config_service

        # Buscar dados do usuário
        data = await user_svc.get_profile(ctx.guild.id, target.id)
        if not data:
            embed = EmbedBuilder.error_user(
                "Não encontrei dados para esse membro."
            ).build()
            await ctx.send(embed=embed)
            return

        # Buscar config de XP do servidor
        config = await xp_svc.get_config(ctx.guild.id)
        xp_per_level = config.get("xp_per_level", 100)

        current_xp = data["xp"]
        current_level = data["level"]
        next_level = current_level + 1

        # XP necessário para o nível atual e próximo
        xp_current_level = xp_svc.xp_for_level(current_level, xp_per_level)
        xp_next_level = xp_svc.xp_for_level(next_level, xp_per_level)

        # Progresso dentro do nível atual
        xp_in_level = current_xp - xp_current_level
        xp_needed = xp_next_level - xp_current_level
        xp_remaining = max(0, xp_next_level - current_xp)

        # Buscar cargos por nível
        level_roles = await xp_svc.get_level_roles(ctx.guild.id)

        # Próximo cargo (o mais próximo acima do nível atual)
        next_role_info = None
        for lr in level_roles:
            if lr["level"] > current_level:
                role = ctx.guild.get_role(lr["role_id"])
                if role:
                    next_role_info = {
                        "role": role,
                        "level": lr["level"],
                        "xp_needed": xp_svc.xp_for_level(lr["level"], xp_per_level)
                        - current_xp,
                    }
                    break

        # Cargo atual (o mais alto que já alcançou)
        current_role_info = None
        for lr in reversed(level_roles):
            if lr["level"] <= current_level:
                role = ctx.guild.get_role(lr["role_id"])
                if role:
                    current_role_info = {"role": role, "level": lr["level"]}
                    break

        # Boost ativo
        boost_roles = await xp_svc.get_boost_roles(ctx.guild.id)
        active_boosts = []
        for br in boost_roles:
            role = ctx.guild.get_role(br["role_id"])
            if role and role in target.roles:
                active_boosts.append(f"{role.mention} — **{br['multiplier']}x**")

        # Defer em comandos híbridos
        await ctx.defer()

        # ── Tentar renderizar a imagem Pillow ────────────────────
        try:
            rank = await user_svc.get_user_rank(ctx.guild.id, target.id)
            theme = data.selected_theme or "default"

            # Gera a imagem na memória
            fp = await generate_rank_card(
                username=target.display_name,
                level=current_level,
                xp_current=xp_in_level,
                xp_needed=xp_needed,
                rank=rank,
                avatar_url=target.display_avatar.url,
                theme_name=theme,
            )
            file = discord.File(fp, filename="rank.png")

            # Embed contendo a imagem gerada
            embed = (
                EmbedBuilder.default()
                .image("attachment://rank.png")
                .build()
            )
            view = XPView(self.bot, ctx.author.id, target, initial_embed=embed)

            # Injetar editor de dev se o usuário for o owner
            inject_dev_edit(
                view,
                bot=self.bot,
                table="user_data",
                pk_values={"guild_id": ctx.guild.id, "user_id": target.id},
                fields=[
                    {"name": "xp", "label": "XP", "value": current_xp},
                    {"name": "level", "label": "Nível", "value": current_level},
                ],
                modal_title=f"XP: {target.display_name}",
            )

            msg = await ctx.send(file=file, embed=embed, view=view)
            view.message = msg
            return

        except Exception:
            self.bot.logger.exception("Falha ao gerar rank card Pillow, usando fallback de texto")

        # ── Fallback: Montar embed de texto clássico ────────────
        bar = _progress_bar(xp_in_level, xp_needed)
        percent = min(100, int((xp_in_level / xp_needed) * 100)) if xp_needed > 0 else 100

        description = (
            f"**{Separators.title('Nível & XP')}**\n\n"
            f" 📈 **Nível {current_level}**\n"
            f"```\n"
            f"{bar} {percent}%\n"
            f"```\n"
            f"🌟 **{current_xp:,}** / **{xp_next_level:,}** XP\n"
            f"Faltam **{xp_remaining:,}** XP para o nível **{next_level}**\n"
        )

        if current_role_info:
            description += (
                f"\n**{Separators.title('Cargo Atual')}**\n\n"
                f" 🏆 {current_role_info['role'].mention} "
                f"*(obtido no nível {current_role_info['level']})*\n"
            )

        if next_role_info:
            levels_away = next_role_info["level"] - current_level
            description += (
                f"\n**{Separators.title('Próximo Cargo')}**\n\n"
                f"{BotEmojis.COMMON_LVL_UP} {next_role_info['role'].mention} — **Nível {next_role_info['level']}**\n"
                f"Faltam **{max(0, next_role_info['xp_needed']):,}** XP "
                f"({levels_away} {'nível' if levels_away == 1 else 'níveis'})\n"
            )
        elif level_roles and not next_role_info:
            description += (
                f"\n**{Separators.title('Próximo Cargo')}**\n\n"
                f" 👑 *Você já alcançou todos os cargos disponíveis!*\n"
            )
        else:
            description += (
                f"\n**{Separators.title('Próximo Cargo')}**\n\n"
                f"*Nenhum cargo por nível configurado neste servidor.*\n"
            )

        if active_boosts:
            description += (
                f"\n**{Separators.title('Boosts Ativos')}**\n\n"
                + "\n".join(f" 🚀 {b}" for b in active_boosts)
                + "\n"
            )

        embed = (
            EmbedBuilder.default()
            .author(
                name=f"📊 {target.display_name} — Progresso de XP",
                icon_url=target.display_avatar.url,
            )
            .thumbnail(target.display_avatar.url)
            .description(description)
            .build()
        )

        view = XPView(self.bot, ctx.author.id, target, initial_embed=embed)

        inject_dev_edit(
            view,
            bot=self.bot,
            table="user_data",
            pk_values={"guild_id": ctx.guild.id, "user_id": target.id},
            fields=[
                {"name": "xp", "label": "XP", "value": current_xp},
                {"name": "level", "label": "Nível", "value": current_level},
            ],
            modal_title=f"XP: {target.display_name}",
        )

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(
        name="daily", description="Reivindique suas moedas diárias!"
    )
    async def daily_cmd(self, ctx: commands.Context) -> None:
        user_svc = self.bot.user_service
        await ctx.defer()
        
        success, res, streak, coins = await user_svc.claim_daily(ctx.guild.id, ctx.author.id)
        if success:
            embed = EmbedBuilder.success(
                f"Você reivindicou suas moedas diárias!\n\n"
                f"{BotEmojis.COMMON_MONEY} Ganhou: **{res}** moedas (Streak: **{streak}** dias, **+{(streak - 1) * 100}** bônus)\n"
                f"{BotEmojis.COMMON_MONEY} Novo saldo: **{coins:,}** moedas."
            ).build()
            await ctx.send(embed=embed)
        else:
            # res is seconds remaining
            import datetime
            time_left = datetime.timedelta(seconds=int(res))
            # Format time left cleanly
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"
            embed = EmbedBuilder.error_user(
                f"Você já reivindicou seu daily hoje!\n"
                f"Aguarde mais **{time_str}** para reivindicar novamente."
            ).build()
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="theme", description="Abre o Hub de Temas para comprar, equipar e gerenciar planos de fundo"
    )
    async def theme_cmd(self, ctx: commands.Context) -> None:
        await ctx.defer()
        user_svc = self.bot.user_service
        xp_svc = self.bot.xp_config_service
        
        data = await user_svc.get_profile(ctx.guild.id, ctx.author.id)
        if not data:
            await ctx.send(
                embed=EmbedBuilder.error_user("Não encontrei suas informações.").build(),
                ephemeral=True
            )
            return

        # Obter dados de XP e nível do autor para o preview inicial
        config = await xp_svc.get_config(ctx.guild.id)
        xp_per_level = config.get("xp_per_level", 100)
        
        current_xp = data.xp
        current_level = data.level
        xp_current_level = xp_svc.xp_for_level(current_level, xp_per_level)
        xp_next_level = xp_svc.xp_for_level(current_level + 1, xp_per_level)
        
        xp_in_level = current_xp - xp_current_level
        xp_needed = xp_next_level - xp_current_level

        # Tentar obter banner
        banner_url = None
        try:
            fetched_user = await self.bot.fetch_user(ctx.author.id)
            if fetched_user.banner:
                banner_url = fetched_user.banner.url
        except Exception:
            pass

        # Formatar a data de entrada no servidor
        joined_dt = ctx.author.joined_at if isinstance(ctx.author, discord.Member) else None
        if joined_dt:
            joined_str = joined_dt.strftime("%d/%m/%Y")
        else:
            joined_str = ctx.author.created_at.strftime("%d/%m/%Y")

        # Gerar o preview inicial
        theme_initial = data.selected_theme or "default"
        from features.community.utils.xp_card_generator import BACKGROUNDS
        is_gif = False
        if theme_initial in BACKGROUNDS:
            is_gif = BACKGROUNDS[theme_initial]["bg_image"].endswith(".gif")
        
        try:
            from features.community.utils.xp_card_generator import generate_profile_card
            fp = await generate_profile_card(
                username=ctx.author.display_name,
                user_id=ctx.author.id,
                messages_sent=data.messages_sent,
                voice_seconds=data.voice_seconds,
                warnings=data.warnings,
                joined_date=joined_str,
                level=data.level,
                xp_current=xp_in_level,
                xp_needed=xp_needed,
                avatar_url=ctx.author.display_avatar.url,
                banner_url=banner_url,
                theme_name=theme_initial,
                coins=data.coins,
            )
            import io
            ext = "gif" if is_gif else "png"
            file = discord.File(io.BytesIO(fp.getvalue()), filename=f"theme_preview.{ext}")
        except Exception:
            self.bot.logger.exception("Falha ao gerar preview inicial")
            file = None

        view = ThemeHubView(
            bot=self.bot,
            author_id=ctx.author.id,
            guild_id=ctx.guild.id,
            profile_data=data,
            joined_str=joined_str,
            avatar_url=ctx.author.display_avatar.url,
            banner_url=banner_url,
        )

        current_theme = view.get_current_theme()
        is_premium = current_theme["type"] == "premium"
        is_unlocked = current_theme["id"] in view.unlocked

        if is_premium:
            status = "✅ Adquirido" if is_unlocked else f"🪙 Custo: **{current_theme['price']} moedas**"
        else:
            status = f"🔓 Desbloqueio: Nível {current_theme['level']}"

        status_equipped = " (Equipado)" if data.selected_theme == current_theme["id"] else ""

        desc = (
            f"💰 Seu Saldo: **{data.coins:,} moedas**\n\n".replace(",", ".") +
            f"✨ **Tema**: {current_theme['name']} (`{current_theme['id']}`)\n"
            f"ℹ️ **Status**: {status}{status_equipped}\n\n"
            f"Use as setinhas `◀`/`▶` ou o dropdown abaixo para navegar pelos temas da loja e do seu inventário!"
        )

        embed = (
            EmbedBuilder.default()
            .title("🎨 Hub de Temas de Perfil")
            .description(desc)
        )
        if file:
            ext = "gif" if is_gif else "png"
            embed.image(f"attachment://theme_preview.{ext}")
            msg = await ctx.send(embed=embed.build(), file=file, view=view)
        else:
            msg = await ctx.send(embed=embed.build(), view=view)

            
        view.message = msg


    @commands.hybrid_command(
        name="ranks", description="Veja a trilha de cargos e progressão do servidor"
    )
    async def ranks_cmd(self, ctx: commands.Context) -> None:
        await ctx.defer()
        xp_svc = self.bot.xp_config_service
        user_svc = self.bot.user_service
        
        # Buscar cargos configurados
        level_roles = await xp_svc.get_level_roles(ctx.guild.id)
        if not level_roles:
            embed = EmbedBuilder.default(
                "Trilha de Cargos",
                "Nenhum cargo por nível está configurado neste servidor."
            ).build()
            await ctx.send(embed=embed)
            return
            
        # Obter dados do autor
        profile_data = await user_svc.get_profile(ctx.guild.id, ctx.author.id)
        user_level = profile_data.level if profile_data else 1
        
        # Preparar dados de cargos para o gerador Pillow
        roles_to_draw = []
        highest_unlocked_level = -1
        for lr in level_roles:
            role = ctx.guild.get_role(lr["role_id"])
            if role:
                has_role = role in ctx.author.roles if isinstance(ctx.author, discord.Member) else False
                is_unlocked = user_level >= lr["level"]
                roles_to_draw.append({
                    "level": lr["level"],
                    "role_name": role.name,
                    "is_unlocked": is_unlocked,
                    "has_role": has_role
                })
                if is_unlocked:
                    highest_unlocked_level = max(highest_unlocked_level, lr["level"])
                    
        # Definir qual é o "atual" (o mais alto desbloqueado)
        for r in roles_to_draw:
            r["is_current"] = (r["level"] == highest_unlocked_level)
            
        try:
            fp = generate_ranks_tree(
                guild_name=ctx.guild.name,
                roles_list=roles_to_draw,
                user_name=ctx.author.display_name,
                user_level=user_level
            )
            file = discord.File(fp, filename="ranks.png")
            embed = (
                EmbedBuilder.default()
                .image("attachment://ranks.png")
                .build()
            )
            await ctx.send(file=file, embed=embed)
            return
        except Exception:
            self.bot.logger.exception("Falha ao gerar árvore de cargos Pillow, usando fallback de texto")
            
        # Fallback de texto
        description = "**Progressão de Cargos:**\n\n"
        for lr in level_roles:
            role = ctx.guild.get_role(lr["role_id"])
            if role:
                status = "✅ Desbloqueado" if user_level >= lr["level"] else "🔒 Bloqueado"
                description += f"• **Nível {lr['level']}** → {role.mention} ({status})\n"
        
        embed = (
            EmbedBuilder.default()
            .title(f"Trilha de Cargos — {ctx.guild.name}")
            .description(description)
            .build()
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(XPCog(bot))

