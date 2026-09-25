from __future__ import annotations
import datetime
import json
import logging
import os
import time
from typing import Any, Callable, Coroutine, Optional
import discord
from discord.ext import commands
from config.settings import BotEmojis, Colors
from core.bot import LunaBot
from core.enums import Feature
from core.utils.embed_builder import EmbedBuilder
from features.fun.services.minecraft_service import MinecraftService
from features.fun.repositories.minecraft_repository import MinecraftRepository

logger = logging.getLogger(__name__)

AVATAR_URL = "https://mc-heads.net/avatar/{username}/64"
SERVER_ICON = "https://mc-heads.net/avatar/MHF_Steve/64"


# ═══════════════════════════════════════════════════════════════
# Modais
# ═══════════════════════════════════════════════════════════════


class ConsoleCommandModal(discord.ui.Modal, title="Comando do Console"):
    """Modal para digitar comandos do console."""

    comando = discord.ui.TextInput(
        label="Comando",
        placeholder="op nome / say mensagem / gamemode creative nome",
        max_length=256,
    )

    def __init__(
        self,
        service: MinecraftService,
        audit_callback: Optional[Callable[[discord.Interaction, str], Coroutine]] = None,
    ) -> None:
        super().__init__()
        self.service = service
        self._audit_callback = audit_callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cmd = self.comando.value.strip()
        if not cmd:
            return
        if not self.service.is_running():
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("O servidor está offline.").build(), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        success, response = await self.service.send_command_with_response(cmd)
        if success:
            if self._audit_callback:
                await self._audit_callback(interaction, cmd)
            clean_resp = response.strip() if response else "Comando executado com sucesso (sem retorno)."
            if len(clean_resp) > 1900:
                clean_resp = clean_resp[:1900] + "\n[...]"
            await interaction.followup.send(
                embed=EmbedBuilder.success(f"Comando enviado: `{cmd}`")
                .field("Saída do Console", f"```txt\n{clean_resp}\n```")
                .build(),
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                embed=EmbedBuilder.error_internal(f"Falha ao enviar comando: {response}").build(), ephemeral=True
            )


class WhitelistMemberModal(discord.ui.Modal):
    """Modal para adicionar ou remover um membro da whitelist."""

    def __init__(self, service: MinecraftService, action: str) -> None:
        titulo = "Adicionar na Whitelist" if action == "add" else "Remover da Whitelist"
        super().__init__(title=titulo)
        self.service = service
        self.action = action
        self.jogador = discord.ui.TextInput(
            label="Nickname do Jogador",
            placeholder="Nome exato no jogo...",
            min_length=3,
            max_length=16,
        )
        self.add_item(self.jogador)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not self.service.is_running():
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("O servidor está offline.").build(), ephemeral=True
            )
            return
        nick = self.jogador.value.strip()
        cmd = f"whitelist {self.action} {nick}"
        success = await self.service.send_command(cmd)
        if success:
            word = "adicionado(a) à" if self.action == "add" else "removido(a) da"
            await interaction.response.send_message(
                embed=EmbedBuilder.success(f"**{nick}** foi {word} whitelist!").build(), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_internal("Falha ao enviar comando.").build(), ephemeral=True
            )


class VincularNickModal(discord.ui.Modal, title="Vincular Nick do Minecraft"):
    """Modal para vincular o nick do Minecraft à conta do Discord."""

    nick = discord.ui.TextInput(
        label="Seu Nick exato no Minecraft (Java)",
        placeholder="Ex: Steve123",
        min_length=3,
        max_length=16,
    )

    def __init__(self, cog: "MinecraftCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        import re
        nick = self.nick.value.strip()
        if not re.match(r"^[a-zA-Z0-9_]{3,16}$", nick):
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user(
                    "Nickname inválido! Use apenas letras, números e sublinhados (3–16 caracteres)."
                ).build(),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        svc = self.cog.service

        existing_owner = await svc.get_player_by_nickname(interaction.guild_id, nick)
        if existing_owner and existing_owner != interaction.user.id:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user(
                    f"O nick `{nick}` já está vinculado a outro membro deste servidor."
                ).build(),
                ephemeral=True,
            )
            return

        await svc.link_player(interaction.guild_id, interaction.user.id, nick)
        msg = f"Você vinculou o nick **{nick}** à sua conta!"
        if svc.is_running():
            success = await svc.ensure_whitelist(nick, add=True)
            if success:
                msg += "\n\n✅ **Você foi adicionado à whitelist automaticamente!** Já pode entrar."
            else:
                msg += "\n\n⚠️ O servidor não conseguiu atualizar a whitelist automaticamente. Peça a um admin."
        else:
            msg += "\n\n*(O servidor está offline. Você será adicionado à whitelist quando ele ligar.)*"

        await interaction.followup.send(
            embed=EmbedBuilder.success(msg).build(), ephemeral=True
        )


class SetupChannelView(discord.ui.View):
    """View com ChannelSelect para vincular o canal de chat do Minecraft."""

    def __init__(self, cog: "MinecraftCog") -> None:
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Selecione o canal de chat do Minecraft...",
    )
    async def channel_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ) -> None:
        channel = select.values[0]
        await self.cog.guild_service.update_config(
            interaction.guild_id, interaction.user.id, minecraft_channel=channel.id
        )
        self.cog.service.register_minecraft_guild(interaction.guild_id)
        self.cog._webhook_cache.clear()
        await self.cog.service.set_webhook_url(interaction.guild_id, None, None)
        await interaction.response.send_message(
            embed=EmbedBuilder.success(f"Canal de chat do Minecraft vinculado a {channel.mention}!").build(),
            ephemeral=True,
        )
        self.stop()


class DesvincularModal(discord.ui.Modal, title="Desvincular Membro"):
    """Modal para um admin remover o vínculo de Minecraft de um membro."""

    membro_id = discord.ui.TextInput(
        label="ID ou @menção do membro (apenas ID numérico)",
        placeholder="Ex: 123456789012345678",
        min_length=17,
        max_length=20,
    )

    def __init__(self, cog: "MinecraftCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            member_id = int(self.membro_id.value.strip().strip("<@!>"))
        except ValueError:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("ID inválido. Insira apenas o número do ID do membro.").build(),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        svc = self.cog.service
        old_nick = await svc.unlink_player(interaction.guild_id, member_id)

        if old_nick:
            if svc.is_running():
                await svc.ensure_whitelist(old_nick, add=False)
            member = interaction.guild.get_member(member_id)
            mention = member.mention if member else f"`{member_id}`"
            await interaction.followup.send(
                embed=EmbedBuilder.success(
                    f"Vínculo de {mention} removido (Nick: `{old_nick}`)."
                    "\nEle também foi removido da whitelist."
                ).build(),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user("Este membro não possui nenhum nick vinculado.").build(),
                ephemeral=True,
            )


class RamSelectView(discord.ui.View):
    """Dropdown para selecionar a RAM do servidor com valores seguros pré-definidos."""

    _RAM_OPTIONS: list[tuple[str, str, str]] = [
        ("1 GB  — Leve",   "1024",  "🟢"),
        ("2 GB  — Padrão", "2048",  "🟢"),
        ("3 GB  — Padrão", "3072",  "🟡"),
        ("4 GB  — Bom",    "4096",  "🟡"),
        ("6 GB  — Robusto","6144",  "🟠"),
        ("8 GB  — Máximo", "8192",  "🔴"),
    ]

    def __init__(self, service: MinecraftService) -> None:
        super().__init__(timeout=60)
        self.service = service
        self._select = discord.ui.Select(
            placeholder="Selecione a quantidade de RAM...",
            options=[
                discord.SelectOption(label=label, value=value, emoji=emoji)
                for label, value, emoji in self._RAM_OPTIONS
            ],
        )
        self._select.callback = self._on_select
        self.add_item(self._select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        ram_mb = int(self._select.values[0])
        try:
            await self.service.set_ram(ram_mb)
            await interaction.response.send_message(
                embed=EmbedBuilder.success(
                    f"Salvo! O servidor iniciará com **{ram_mb} MB** ({ram_mb // 1024} GB) na próxima vez."
                ).build(),
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_internal(f"Erro ao salvar: {exc}").build(), ephemeral=True
            )
        self.stop()


# ═══════════════════════════════════════════════════════════════
# Sub-views
# ═══════════════════════════════════════════════════════════════


class WhitelistActionView(discord.ui.View):
    """Menu de ações para gerenciar a whitelist."""

    def __init__(self, service: MinecraftService) -> None:
        super().__init__(timeout=60)
        self.service = service

    @discord.ui.select(
        placeholder="Selecione uma ação de whitelist...",
        options=[
            discord.SelectOption(label="Adicionar membro", value="add", emoji=BotEmojis.ACTION_CREATE),
            discord.SelectOption(label="Remover membro", value="remove", emoji=BotEmojis.ACTION_REMOVE),
            discord.SelectOption(label="Ligar whitelist", value="on", emoji=BotEmojis.COMMON_LOCK),
            discord.SelectOption(label="Desligar whitelist", value="off", emoji=BotEmojis.COMMON_UNLOCK),
        ],
        row=0,
    )
    async def action_select(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        action = select.values[0]
        if action in ("add", "remove"):
            await interaction.response.send_modal(WhitelistMemberModal(self.service, action))
        else:
            if not self.service.is_running():
                await interaction.response.send_message(
                    embed=EmbedBuilder.error_user("O servidor está offline.").build(), ephemeral=True
                )
                return
            await self.service.send_command(f"whitelist {action}")
            label = "ligada" if action == "on" else "desligada"
            await interaction.response.send_message(
                embed=EmbedBuilder.success(f"Whitelist **{label}** com sucesso!").build(), ephemeral=True
            )


class BackupSelectMenu(discord.ui.Select):
    """Dropdown para escolher backup a restaurar."""

    def __init__(self, service: MinecraftService, backups: list[str]) -> None:
        self.service = service
        options = [discord.SelectOption(label=b, value=b) for b in backups[:25]]
        super().__init__(placeholder="Selecione um backup...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        backup = self.values[0]
        embed = (
            EmbedBuilder.default(
                "Confirmar Restauração",
                f"Você tem certeza que quer restaurar `{backup}`?\n\n"
                "**O mundo atual será completamente substituído.**\n"
                "O servidor deve estar desligado.",
            )
            .color(Colors.ALERT)
            .build()
        )
        view = RestoreConfirmView(self.service, backup)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class RestoreConfirmView(discord.ui.View):
    """Confirmação dupla para restaurar backup."""

    def __init__(self, service: MinecraftService, backup_name: str) -> None:
        super().__init__(timeout=30)
        self.service = service
        self.backup_name = backup_name

    @discord.ui.button(label="Confirmar Restauração", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.service.is_running():
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("Desligue o servidor antes de restaurar.").build(), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        success = await self.service.restore_backup(self.backup_name)
        if success:
            await interaction.followup.send(
                embed=EmbedBuilder.success(f"Backup `{self.backup_name}` restaurado!").build(), ephemeral=True
            )
        else:
            await interaction.followup.send(
                embed=EmbedBuilder.error_internal("Falha ao restaurar o backup.").build(), ephemeral=True
            )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=EmbedBuilder.default("Cancelado", "Nenhuma alteração foi feita.").build(), ephemeral=True
        )
        self.stop()


class WipeConfirmView(discord.ui.View):
    """Confirmação extrema para apagar o mundo inteiro."""

    def __init__(self, service: MinecraftService) -> None:
        super().__init__(timeout=60)
        self.service = service

    @discord.ui.button(label="SIM, DESTRUIR O MUNDO AGORA", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.service.is_running():
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("Desligue o servidor primeiro.").build(), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        success = await self.service.wipe_world()
        if success:
            await interaction.followup.send(
                embed=EmbedBuilder.success(
                    "Mundo apagado!\n*(Um backup emergencial foi salvo automaticamente.)*"
                ).build(),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                embed=EmbedBuilder.error_internal("Falha ao apagar o mundo.").build(), ephemeral=True
            )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Operação cancelada.", ephemeral=True)
        self.stop()


# ═══════════════════════════════════════════════════════════════
# 1. Painel Público — /minecraft
# ═══════════════════════════════════════════════════════════════


class MinecraftPublicView(discord.ui.View):
    """Painel público: Ligar, Jogadores, Plugins, Tutorial."""

    # Cooldown por usuário: 30s para status/jogadores, 5min para ligar servidor
    _COOLDOWN_STATUS = 30.0
    _COOLDOWN_START  = 300.0

    def __init__(self, cog: "MinecraftCog") -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.service = cog.service
        self._cooldowns: dict[int, dict[str, float]] = {}
        self.start_btn.emoji = discord.PartialEmoji.from_str(BotEmojis.STATUS_LIVE)
        self.players_btn.emoji = discord.PartialEmoji.from_str(BotEmojis.COMMON_USERS)
        self.plugins_btn.emoji = discord.PartialEmoji.from_str(BotEmojis.COMMON_TOOLS)
        self.tutorial_btn.emoji = discord.PartialEmoji.from_str(BotEmojis.COMMON_BOOK)
        self.vincular_btn.emoji = discord.PartialEmoji.from_str(BotEmojis.COMMON_CLIP)

    def _check_cooldown(self, user_id: int, key: str, seconds: float) -> Optional[float]:
        """Retorna o tempo restante de cooldown (em segundos) ou None se liberado."""
        user_cd = self._cooldowns.setdefault(user_id, {})
        last = user_cd.get(key, 0.0)
        remaining = seconds - (time.monotonic() - last)
        if remaining > 0:
            return remaining
        user_cd[key] = time.monotonic()
        return None

    @discord.ui.button(label="Ligar Servidor", style=discord.ButtonStyle.success, row=0)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        remaining = self._check_cooldown(interaction.user.id, "start", self._COOLDOWN_START)
        if remaining is not None:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user(
                    f"Aguarde **{remaining:.0f}s** antes de tentar ligar o servidor novamente."
                ).build(),
                ephemeral=True,
            )
            return

        if self.service.is_running():
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("O servidor já está ligado!").build(), ephemeral=True
            )
            return

        await interaction.response.defer()

        ram = await self.service.get_ram()

        installed = await self.service.install_server()
        if not installed:
            await interaction.edit_original_response(
                embed=EmbedBuilder.error_internal("Falha ao preparar os arquivos do servidor.").build(),
                view=None
            )
            return

        started = await self.service.start_server(ram_mb=ram)
        if started:
            embed = await self.cog._build_public_embed()
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.edit_original_response(
                embed=EmbedBuilder.error_internal("Falha ao iniciar o servidor.").build(),
                view=None
            )

    @discord.ui.button(label="Jogadores", style=discord.ButtonStyle.secondary, row=0)
    async def players_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        remaining = self._check_cooldown(interaction.user.id, "players", self._COOLDOWN_STATUS)
        if remaining is not None:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user(
                    f"Aguarde **{remaining:.0f}s** antes de consultar jogadores novamente."
                ).build(),
                ephemeral=True,
            )
            return

        if not self.service.is_running():
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("O servidor está offline.").build(), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        players = await self.service.get_players()
        is_online, count, _, _ = await self.service.get_status()

        if players:
            player_list = "\n".join(f"• `{p}`" for p in players)
            desc = f"**{count} jogador(es) online:**\n{player_list}"
        elif count > 0:
            desc = f"**{count} jogador(es) online.**\n*Lista ainda indisponível.*"
        else:
            desc = "Nenhum jogador online no momento."

        embed = EmbedBuilder.default("Jogadores Online", desc).color(Colors.GAMES).build()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Plugins", style=discord.ButtonStyle.secondary, row=0)
    async def plugins_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        plugins = await self.service.list_plugins()
        if plugins:
            plugin_list = "\n".join(f"• `{p}`" for p in plugins)
            desc = f"**{len(plugins)} plugin(s) instalado(s):**\n{plugin_list}"
        else:
            desc = "Nenhum plugin instalado."
        embed = EmbedBuilder.default("Plugins do Servidor", desc).color(Colors.GAMES).build()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Tutorial", style=discord.ButtonStyle.primary, row=0)
    async def tutorial_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        ip = await self.service.get_public_ip()

        embed = (
            EmbedBuilder.default(
                "Como Jogar no Servidor",
                "Siga as instruções abaixo para se conectar!\n\n"
                "⚠️ **Nota Importante:** Este servidor suporta **APENAS Java Edition (PC)**. Conexões via Bedrock (Celular/Consoles) **não** são suportadas."
            )
            .color(Colors.GAMES)
            .field(
                f"{BotEmojis.DEVICE_PC} Java Edition (PC)",
                f"1. Clique em **Multiplayer** e **Adicionar Servidor**.\n"
                f"2. Endereço: `{ip}:{self.service.mc_port}`",
                inline=False
            )
            .field(
                f"{BotEmojis.COMMON_LOCK} Segurança & Whitelist",
                f"Este servidor usa uma **Whitelist Obrigatória**.\n"
                f"Para conseguir entrar, você **DEVE** vincular seu Discord ao seu Nick do Minecraft:\n\n"
                f"→ Clique em **Vincular Nick** abaixo, ou use o botão no painel principal.",
                inline=False
            )
            .field(
                f"{BotEmojis.STATUS_DISABLED} Problemas ao entrar?",
                f"→ **Offline:** Use `/minecraft` e clique em **Ligar Servidor**.\n"
                f"→ **Whitelist:** Peça a um moderador para te adicionar à whitelist.\n"
                f"→ **Outros:** Envie uma mensagem para @ylectez para suporte.",
                inline=False
            )
            .footer(text=f"Versão suportada: {self.service.current_version}")
            .build()
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Vincular Nick", style=discord.ButtonStyle.secondary, row=1)
    async def vincular_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(VincularNickModal(self.cog))


# ═══════════════════════════════════════════════════════════════
# 2. Painel de Administrador — /mineconfig
# ═══════════════════════════════════════════════════════════════


class MineConfigView(discord.ui.View):
    """Painel ADM do Minecraft. Botões de owner são adicionados dinamicamente."""

    def __init__(self, cog: "MinecraftCog", is_owner: bool = False) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.service = cog.service
        self.is_owner = is_owner

        self.chat_btn.emoji = discord.PartialEmoji.from_str(BotEmojis.COMMON_CHAT)
        self.whitelist_btn.emoji = discord.PartialEmoji.from_str(BotEmojis.COMMON_USERS)
        self.backup_btn.emoji = discord.PartialEmoji.from_str(BotEmojis.COMMON_DOWNLOAD)
        self.console_btn.emoji = discord.PartialEmoji.from_str(BotEmojis.ACTION_SETTINGS)

        # Botão de desvincular sempre visível para admins
        desvinc_btn = discord.ui.Button(
            label="Desvincular Membro",
            style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji.from_str(BotEmojis.ACTION_REMOVE),
            row=1,
        )
        desvinc_btn.callback = self._desvinc_callback
        self.add_item(desvinc_btn)

        if is_owner:
            self._add_owner_buttons()

    def _add_owner_buttons(self) -> None:
        """Injeta os botões exclusivos de owner na Row 1."""
        stop_btn = discord.ui.Button(
            label="Desligar",
            style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji.from_str(BotEmojis.STATUS_STOPPED),
            row=1,
        )
        stop_btn.callback = self._stop_callback
        self.add_item(stop_btn)

        restore_btn = discord.ui.Button(
            label="Restaurar Backup",
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji.from_str(BotEmojis.ACTION_REFRESH),
            row=1,
        )
        restore_btn.callback = self._restore_callback
        self.add_item(restore_btn)

        ram_btn = discord.ui.Button(
            label="RAM",
            style=discord.ButtonStyle.primary,
            emoji=discord.PartialEmoji.from_str(BotEmojis.ACTION_SETTINGS),
            row=1,
        )
        ram_btn.callback = self._ram_callback
        self.add_item(ram_btn)

        wipe_btn = discord.ui.Button(
            label="WIPE MUNDO",
            style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji.from_str(BotEmojis.COMMON_REPORT),
            row=1,
        )
        wipe_btn.callback = self._wipe_callback
        self.add_item(wipe_btn)

    # ── Botões fixos (Staff) ──────────────────────────────────

    @discord.ui.button(label="Vincular Chat", style=discord.ButtonStyle.secondary, row=0)
    async def chat_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        embed = (
            EmbedBuilder.default(
                "Vincular Canal de Chat",
                "Selecione abaixo o canal de texto que receberá as mensagens do Minecraft.\n\n"
                "Mensagens enviadas nesse canal serão redirecionadas para o jogo em tempo real, e vice-versa.",
            )
            .build()
        )
        view = SetupChannelView(self.cog)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Whitelist", style=discord.ButtonStyle.primary, row=0)
    async def whitelist_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        view = WhitelistActionView(self.service)
        embed = EmbedBuilder.default(
            "Gerenciar Whitelist",
            "Selecione a ação desejada abaixo.",
        ).build()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Backup", style=discord.ButtonStyle.success, row=0)
    async def backup_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        backup_name = await self.service.create_backup()
        if backup_name:
            await interaction.followup.send(
                embed=EmbedBuilder.success(f"Backup criado: `{backup_name}`").build(), ephemeral=True
            )
        else:
            await interaction.followup.send(
                embed=EmbedBuilder.error_internal("Falha ao criar backup. O mundo existe?").build(), ephemeral=True
            )

    async def _desvinc_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(DesvincularModal(self.cog))

    @discord.ui.button(label="Console", style=discord.ButtonStyle.secondary, row=0)
    async def console_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        async def _audit(inter: discord.Interaction, cmd: str) -> None:
            await self.cog._log_audit(inter.guild_id, inter.user, cmd)
        await interaction.response.send_modal(ConsoleCommandModal(self.service, audit_callback=_audit))

    # ── Callbacks de owner (injetados dinamicamente) ──────────

    async def _stop_callback(self, interaction: discord.Interaction) -> None:
        if not self.service.is_running():
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("O servidor já está desligado.").build(), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        stopped = await self.service.stop_server()
        if stopped:
            await interaction.followup.send(
                embed=EmbedBuilder.success("Servidor desligado com sucesso.").build(), ephemeral=True
            )
            embed = await self.cog._build_config_embed()
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.followup.send(
                embed=EmbedBuilder.error_internal("Falha ao desligar o servidor.").build(), ephemeral=True
            )

    async def _restore_callback(self, interaction: discord.Interaction) -> None:
        if self.service.is_running():
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("Desligue o servidor antes de restaurar.").build(), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        backups = await self.service.list_backups()
        if not backups:
            await interaction.followup.send(
                embed=EmbedBuilder.error_user("Nenhum backup encontrado.").build(), ephemeral=True
            )
            return
        view = discord.ui.View(timeout=60)
        view.add_item(BackupSelectMenu(self.service, backups))
        await interaction.followup.send(
            embed=EmbedBuilder.default(
                "Restaurar Backup",
                "Selecione o backup que deseja restaurar.\nO mundo atual será **substituído**.",
            )
            .color(Colors.ALERT)
            .build(),
            view=view,
            ephemeral=True,
        )

    async def _ram_callback(self, interaction: discord.Interaction) -> None:
        view = RamSelectView(self.service)
        await interaction.response.send_message(
            embed=EmbedBuilder.default(
                "Ajustar Memória RAM",
                "Selecione a quantidade de RAM que o servidor usará na próxima inicialização.",
            ).build(),
            view=view,
            ephemeral=True,
        )

    async def _wipe_callback(self, interaction: discord.Interaction) -> None:
        if self.service.is_running():
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("Desligue o servidor antes de fazer o wipe.").build(), ephemeral=True
            )
            return
        embed = EmbedBuilder.alert(
            "**⚠️ ZONA DE PERIGO ⚠️**\n\n"
            "Isso irá apagar a pasta do **MUNDO INTEIRO** — "
            "construções, progressos e inventários serão perdidos.\n"
            "Um backup emergencial será criado automaticamente."
        ).build()
        await interaction.response.send_message(embed=embed, view=WipeConfirmView(self.service), ephemeral=True)


# ═══════════════════════════════════════════════════════════════
# Cog Principal
# ═══════════════════════════════════════════════════════════════
