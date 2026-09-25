from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
import time
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config.settings import BotEmojis, Colors, BRT
from core.bot import LunaBot
from core.enums import Feature
from core.events import BotEvent
from core.utils.embed_builder import EmbedBuilder
from features.fun.services.minecraft_service import MinecraftService

logger = logging.getLogger(__name__)

# Discord webhook: 30 msgs / 60s por canal — envia 1 msg a cada 2s da fila (#1)
_WEBHOOK_SEND_INTERVAL = 2.0
# Discord → MC: máx 5 mensagens por usuário a cada 10s (#2)
_DISCORD_MC_MAX_MSGS = 5
_DISCORD_MC_WINDOW_SEC = 10.0
# Limpeza de timestamps: a cada 10 minutos
_DISCORD_MC_CLEANUP_INTERVAL = 600


class _SimpleLRUWebhookCache:
    """LRU cache simples para webhooks com máximo de 50 entradas."""
    def __init__(self, maxsize: int = 50):
        self.maxsize = maxsize
        self.cache: dict[int, discord.Webhook] = {}
        self.access_times: dict[int, float] = {}

    def get(self, key: int) -> Optional[discord.Webhook]:
        if key in self.cache:
            self.access_times[key] = time.monotonic()
            return self.cache[key]
        return None

    def set(self, key: int, value: discord.Webhook) -> None:
        self.access_times[key] = time.monotonic()
        if key in self.cache:
            self.cache[key] = value
        elif len(self.cache) < self.maxsize:
            self.cache[key] = value
        else:
            oldest_key = min(self.access_times, key=self.access_times.get)
            del self.cache[oldest_key]
            del self.access_times[oldest_key]
            self.cache[key] = value

    def pop(self, key: int, default=None):
        self.access_times.pop(key, None)
        return self.cache.pop(key, default)

    def clear(self):
        self.cache.clear()
        self.access_times.clear()

    def __contains__(self, key: int) -> bool:
        return key in self.cache

    def __getitem__(self, key: int) -> discord.Webhook:
        self.access_times[key] = time.monotonic()
        return self.cache[key]

    def __setitem__(self, key: int, value: discord.Webhook) -> None:
        self.set(key, value)
from features.fun.ui.minecraft_ui import (
    AVATAR_URL,
    SERVER_ICON,
    ConsoleCommandModal,
    WhitelistMemberModal,
    WhitelistActionView,
    BackupSelectMenu,
    RestoreConfirmView,
    WipeConfirmView,
    MinecraftPublicView,
    MineConfigView,
    VincularNickModal,
    SetupChannelView,
    DesvincularModal,
)


@dataclass(frozen=True, slots=True)
class _QueuedWebhookMsg:
    username: str
    content: str
    avatar_url: Optional[str]


class MinecraftCog(commands.Cog):
    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self.service: MinecraftService = bot.container.minecraft_service
        self.guild_service = bot.container.guild_service

        # Cache em memória de webhooks (LRU com máx 50)
        self._webhook_cache = _SimpleLRUWebhookCache(maxsize=50)
        self._webhook_queues: dict[int, deque[_QueuedWebhookMsg]] = {}
        self._webhook_workers: dict[int, asyncio.Task] = {}

        # Rate limit Discord → MC por (guild_id, user_id) (#2)
        self._discord_mc_timestamps: dict[tuple[int, int], list[float]] = {}

        self._empty_since: datetime.datetime | None = None
        self._shutdown_task: asyncio.Task | None = None

        self.bot.event_bus.subscribe(BotEvent.MINECRAFT_CHAT, self.on_minecraft_chat)
        self.bot.event_bus.subscribe(BotEvent.MINECRAFT_DEATH, self.on_minecraft_death)
        self.bot.event_bus.subscribe(BotEvent.MINECRAFT_JOIN, self.on_minecraft_join)
        self.bot.event_bus.subscribe(BotEvent.MINECRAFT_LEAVE, self.on_minecraft_leave)
        self.bot.event_bus.subscribe(BotEvent.MINECRAFT_PLAYER_COMMAND, self.on_minecraft_player_command)

        self._daily_backup_loop.start()
        self._idle_check_loop.start()
        self._cleanup_timestamps_loop.start()

    async def cog_unload(self) -> None:
        if self._daily_backup_loop.is_running():
            self._daily_backup_loop.cancel()
        if self._idle_check_loop.is_running():
            self._idle_check_loop.cancel()
        if self._cleanup_timestamps_loop.is_running():
            self._cleanup_timestamps_loop.cancel()
        # Cancelar shutdown por inatividade em andamento
        if self._shutdown_task and not self._shutdown_task.done():
            self._shutdown_task.cancel()
        for task in self._webhook_workers.values():
            if not task.done():
                task.cancel()
        self._webhook_workers.clear()

    # ── Tasks ──────────────────────────────────────────────────

    @tasks.loop(seconds=_DISCORD_MC_CLEANUP_INTERVAL)
    async def _cleanup_timestamps_loop(self) -> None:
        """Limpa entradas vazias de rate limit a cada 10 min."""
        now = time.monotonic()
        to_remove = [
            key for key, timestamps in list(self._discord_mc_timestamps.items())
            if not any(now - t < _DISCORD_MC_WINDOW_SEC for t in timestamps)
        ]
        for key in to_remove:
            del self._discord_mc_timestamps[key]
        if to_remove:
            logger.debug("Limpeza de rate limit: removidas %d entradas", len(to_remove))

    @tasks.loop(time=datetime.time(hour=4, minute=0, tzinfo=BRT))
    async def _daily_backup_loop(self) -> None:
        """Auto-backup diário às 04:00 BRT."""
        try:
            name = await self.service.create_backup()
            if name:
                logger.info("Backup diário de Minecraft: %s", name)
        except Exception as exc:
            logger.error("Falha no auto-backup de Minecraft: %s", exc)

    @tasks.loop(minutes=5)
    async def _idle_check_loop(self) -> None:
        """Desliga o servidor após 1h sem jogadores."""
        if not self.service.is_running():
            self._empty_since = None
            return

        status = await self.service.get_status()
        if not status or not status[0]:
            return

        players = status[1]
        if players > 0:
            self._empty_since = None
        else:
            now = datetime.datetime.now(datetime.timezone.utc)
            if self._empty_since is None:
                self._empty_since = now
            elif datetime.datetime.now(datetime.timezone.utc) - self._empty_since >= datetime.timedelta(minutes=60):
                self._empty_since = None
                # Evita dois countdowns paralelos após hot-reload (#11)
                if self._shutdown_task is None or self._shutdown_task.done():
                    self._shutdown_task = asyncio.create_task(self._idle_shutdown())

    async def _idle_shutdown(self) -> None:
        logger.info("Desligamento por inatividade (1h vazio).")


        async def _notify(guild_id: int) -> None:
            channel = await self._get_mine_channel(guild_id)
            if channel:
                webhook = await self._get_webhook(channel)
                if webhook:
                    embed = EmbedBuilder.alert(
                        "O servidor ficou vazio por 1 hora e foi desligado para economizar recursos.\n"
                        "Use `/minecraft` para religá-lo quando quiser jogar!"
                    ).build()
                    await webhook.send(
                        embed=embed, username="Luna", avatar_url=self.bot.user.display_avatar.url
                    )

        await self._handle_minecraft_event(0, _notify)

        for i in range(4, 0, -1):
            if not self.service.is_running():
                return
            await self.service.send_command(
                f'tellraw @a {{"text":"O servidor dormirá em {i} minuto(s) por inatividade...","color":"yellow"}}'
            )
            await asyncio.sleep(60)

        if not self.service.is_running():
            return

        st = await self.service.get_status()
        if st and st[0] and st[1] > 0:
            await self.service.send_command(
                'tellraw @a {"text":"Alguém logou! Desligamento por inatividade ABORTADO.","color":"green"}'
            )
            logger.info("Shutdown de inatividade abortado — player conectou.")
            return

        await self.service.send_command('tellraw @a {"text":"Servidor encerrando...","color":"gray"}')
        await asyncio.sleep(2)
        await self.service.stop_server()

    # ── Embeds ─────────────────────────────────────────────────

    async def _build_public_embed(self) -> discord.Embed:
        is_online, players, ping, tps = await self.service.get_status()
        status = f"{BotEmojis.STATUS_LIVE} **Online**" if is_online else f"{BotEmojis.STATUS_STOPPED} **Offline**"
        desc = (
            f"**Status:** {status}\n"
            f"**Versão:** `{self.service.current_version} (Paper)`\n"
            f"**Jogadores:** {players}\n"
        )
        if is_online:
            desc += f"**Ping:** {ping}ms  |  **TPS:** {tps}\n"
        return (
            EmbedBuilder.default(f"{BotEmojis.MINECRAFT} Minecraft Server", desc)
            .color(Colors.GAMES if is_online else Colors.DEFAULT)
            .build()
        )

    async def _build_config_embed(self) -> discord.Embed:
        is_online, players, ping, tps = await self.service.get_status()
        status = f"{BotEmojis.STATUS_LIVE} Online" if is_online else f"{BotEmojis.STATUS_STOPPED} Offline"
        backups = await self.service.list_backups()
        desc = (
            f"**Status:** {status}\n"
            f"**Versão:** `{self.service.current_version} (Paper)`\n"
            f"**Jogadores:** {players}\n"
            f"**TPS:** {tps if is_online else 'N/A'}\n"
            f"**Backups disponíveis:** {len(backups)}\n"
        )
        if not self.service.has_auth_plugin():
            desc += (
                "\n**Segurança:** Servidor em modo offline sem AuthMe. "
                "Instale o plugin AuthMe (incluído no template Luna) antes de abrir ao público.\n"
            )
        return (
            EmbedBuilder.default(f"{BotEmojis.MINECRAFT} Minecraft — Administração", desc)
            .color(Colors.ALERT if is_online or not self.service.has_auth_plugin() else Colors.DEFAULT)
            .build()
        )

    # ── Webhooks ───────────────────────────────────────────────

    async def _get_webhook(self, channel: discord.TextChannel) -> Optional[discord.Webhook]:
        """
        Resolve o webhook para o canal com duas camadas de cache:

        1. Memória (dict em runtime) — mais rápido, perdido no restart.
        2. Banco de dados (URL salvo) — persiste entre restarts, sem chamar a API.

        Se nenhum dos dois tiver o webhook, cria um novo e persiste o URL.
        Invalida as duas camadas automaticamente em caso de 404 (webhook deletado).
        """
        guild_id = channel.guild.id

        # Camada 1: cache em memória
        if channel.id in self._webhook_cache:
            return self._webhook_cache[channel.id]

        # Camada 2: URL persistido no banco (valida canal #9)
        try:
            saved_url, saved_channel_id = await self.service.get_webhook_config(guild_id)
            if saved_url and saved_channel_id == channel.id:
                wh = discord.Webhook.from_url(saved_url, client=self.bot)
                self._webhook_cache[channel.id] = wh
                logger.debug("Webhook reconstruído do banco para guild %s.", guild_id)
                return wh
            if saved_url and saved_channel_id != channel.id:
                logger.info(
                    "Webhook em cache aponta para canal %s, mas o atual é %s — recriando.",
                    saved_channel_id,
                    channel.id,
                )
                self._webhook_cache.pop(channel.id, None)
                await self.service.set_webhook_url(guild_id, None, None)
        except Exception as exc:
            logger.warning("Erro ao ler webhook do banco para guild %s: %s", guild_id, exc)

        # Camada 3: buscar/criar via API
        try:
            webhooks = await channel.webhooks()
            wh = next((w for w in webhooks if w.name == "Luna Minecraft"), None)
            if wh is None:
                wh = await channel.create_webhook(name="Luna Minecraft")
                logger.info("Webhook 'Luna Minecraft' criado em #%s.", channel.name)

            # Persiste URL e canal no banco para próximos restarts (#9)
            await self.service.set_webhook_url(guild_id, wh.url, channel.id)
            self._webhook_cache[channel.id] = wh
            return wh

        except discord.Forbidden:
            logger.warning("Sem permissão para webhook em #%s.", channel.name)
            return None
        except Exception as exc:
            logger.error("Erro ao resolver webhook: %s", exc)
            return None

    async def _get_mine_channel(self, guild_id: int) -> Optional[discord.TextChannel]:
        config = await self.guild_service.get_config(guild_id)
        if not config:
            return None
        channel_id = config.get("minecraft_channel") or config.get("log_channel")
        if not channel_id:
            return None
        channel = self.bot.get_channel(int(channel_id))
        if channel and isinstance(channel, discord.TextChannel):
            return channel
        return None

    async def _send_webhook(
        self,
        guild_id: int,
        username: str,
        content: str,
        avatar_url: Optional[str] = None,
    ) -> None:
        """Enfileira mensagem MC→Discord respeitando rate limit do webhook (#1)."""
        if guild_id not in self._webhook_queues:
            self._webhook_queues[guild_id] = deque()
        self._webhook_queues[guild_id].append(
            _QueuedWebhookMsg(username=username, content=content, avatar_url=avatar_url)
        )
        worker = self._webhook_workers.get(guild_id)
        if worker is None or worker.done():
            self._webhook_workers[guild_id] = asyncio.create_task(self._webhook_worker(guild_id))

    async def _webhook_worker(self, guild_id: int) -> None:
        """Processa a fila de webhooks com intervalo fixo e backoff em 429."""
        backoff = _WEBHOOK_SEND_INTERVAL
        try:
            while True:
                queue = self._webhook_queues.get(guild_id)
                if not queue:
                    self._webhook_queues.pop(guild_id, None)
                    break
                await asyncio.sleep(backoff)
                queue = self._webhook_queues.get(guild_id)
                if not queue:
                    self._webhook_queues.pop(guild_id, None)
                    break
                msg = queue.popleft()
                if not queue:
                    self._webhook_queues.pop(guild_id, None)

                retry_after = await self._deliver_webhook(guild_id, msg)
                if retry_after is not None:
                    if guild_id not in self._webhook_queues:
                        self._webhook_queues[guild_id] = deque()
                    self._webhook_queues[guild_id].appendleft(msg)
                    backoff = min(max(retry_after, _WEBHOOK_SEND_INTERVAL), 60.0)
                else:
                    backoff = _WEBHOOK_SEND_INTERVAL
        except asyncio.CancelledError:
            pass
        finally:
            self._webhook_queues.pop(guild_id, None)
            if guild_id in self._webhook_workers and self._webhook_workers[guild_id].done():
                self._webhook_workers.pop(guild_id, None)

    async def _deliver_webhook(
        self, guild_id: int, msg: _QueuedWebhookMsg
    ) -> Optional[float]:
        """Envia uma mensagem via webhook. Retorna retry_after em caso de 429."""
        channel = await self._get_mine_channel(guild_id)
        if not channel:
            return None
        webhook = await self._get_webhook(channel)
        if not webhook:
            return None
        try:
            await webhook.send(
                content=msg.content,
                username=msg.username,
                avatar_url=msg.avatar_url or SERVER_ICON,
                wait=False,
            )
            return None
        except discord.NotFound:
            logger.warning(
                "Webhook 'Luna Minecraft' não encontrado em #%s — recriando na próxima mensagem.",
                channel.name,
            )
            self._webhook_cache.pop(channel.id, None)
            await self.service.set_webhook_url(guild_id, None, None)
            return None
        except discord.Forbidden:
            logger.error("Sem permissão para webhook em #%s.", channel.name)
            return None
        except discord.HTTPException as exc:
            if exc.status == 429:
                retry = float(getattr(exc, "retry_after", 5.0) or 5.0)
                logger.warning("Rate limit webhook guild %s — retry em %.1fs", guild_id, retry)
                return retry
            logger.error("Erro HTTP ao enviar webhook: %s", exc)
            return None

    def _allow_discord_to_mc(self, guild_id: int, user_id: int) -> bool:
        """Cooldown por usuário: máx 5 mensagens / 10s (#2)."""
        key = (guild_id, user_id)
        now = time.monotonic()
        timestamps = [t for t in self._discord_mc_timestamps.get(key, []) if now - t < _DISCORD_MC_WINDOW_SEC]
        if len(timestamps) >= _DISCORD_MC_MAX_MSGS:
            self._discord_mc_timestamps[key] = timestamps
            return False
        timestamps.append(now)
        if timestamps:
            self._discord_mc_timestamps[key] = timestamps
        else:
            self._discord_mc_timestamps.pop(key, None)
        return True

    async def _handle_minecraft_event(self, guild_id: int, func) -> None:
        if guild_id == 0:
            target_guilds = await self.service.get_event_guild_ids()
            if not target_guilds:
                return
            await asyncio.gather(*(func(g_id) for g_id in target_guilds), return_exceptions=True)
        else:
            await func(guild_id)

    async def _log_audit(self, guild_id: int, user: discord.User | discord.Member, action: str) -> None:
        """Envia um log de auditoria de segurança para o canal de Minecraft/logs do Discord."""
        channel = await self._get_mine_channel(guild_id)
        if not channel:
            return
        embed = (
            EmbedBuilder.alert(
                f"👤 **Usuário:** {user.mention} ({user.id})\n"
                f"💻 **Comando/Ação:** `{action}`"
            )
            .title("Segurança — Log de Auditoria Minecraft")
            .timestamp()
            .build()
        )
        try:
            await channel.send(embed=embed)
        except Exception as exc:
            logger.error("Falha ao enviar log de auditoria para guild %s: %s", guild_id, exc)

    # ── Permission helpers ─────────────────────────────────────

    async def _is_allowed(self, interaction: discord.Interaction) -> bool:
        is_owner = await self.bot.is_owner(interaction.user)
        is_enabled = await self.bot.guild_service.is_feature_enabled(
            interaction.guild_id, Feature.MINECRAFT
        )
        if not is_enabled and not is_owner:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user(
                    "O Minecraft não está ativado neste servidor.\n"
                    "Peça ao administrador para usar `!config` e ativar."
                ).build(),
                ephemeral=True,
            )
            return False
        return True

    async def _is_allowed_ctx(self, ctx: commands.Context) -> bool:
        is_owner = await self.bot.is_owner(ctx.author)
        is_enabled = await self.bot.guild_service.is_feature_enabled(
            ctx.guild.id, Feature.MINECRAFT
        )
        if not is_enabled and not is_owner:
            await ctx.send(
                embed=EmbedBuilder.error_user(
                    "O Minecraft não está ativado neste servidor.\n"
                    "Peça ao administrador para usar `!config` e ativar."
                ).build()
            )
            return False
        return True

    # ── Slash Commands ─────────────────────────────────────────

    @app_commands.command(name="minecraft", description="Painel do servidor de Minecraft")
    async def minecraft_slash(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Comando apenas para servidores.", ephemeral=True)
            return
        if not await self._is_allowed(interaction):
            return
        embed = await self._build_public_embed()
        view = MinecraftPublicView(self)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="mineconfig", description="Painel de administração do servidor Minecraft")
    async def mineconfig_slash(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Comando apenas para servidores.", ephemeral=True)
            return
        is_admin = interaction.permissions.administrator or await self.bot.is_owner(interaction.user)
        if not is_admin:
            await interaction.response.send_message(
                embed=EmbedBuilder.error_user("Você não tem permissão para isso.").build(), ephemeral=True
            )
            return
        is_owner = await self.bot.is_owner(interaction.user)
        embed = await self._build_config_embed()
        view = MineConfigView(self, is_owner=is_owner)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── Prefix Commands ────────────────────────────────────────

    @commands.command(name="minecraft")
    async def minecraft_prefix(self, ctx: commands.Context) -> None:
        """Painel público do Minecraft."""
        if not ctx.guild:
            return
        if not await self._is_allowed_ctx(ctx):
            return
        embed = await self._build_public_embed()
        view = MinecraftPublicView(self)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="mineconfig")
    async def mineconfig_prefix(self, ctx: commands.Context) -> None:
        """Painel de administração do Minecraft."""
        if not ctx.guild:
            return
        is_admin = ctx.author.guild_permissions.administrator or await self.bot.is_owner(ctx.author)
        if not is_admin:
            await ctx.send(embed=EmbedBuilder.error_user("Você não tem permissão para isso.").build())
            return
        is_owner = await self.bot.is_owner(ctx.author)
        embed = await self._build_config_embed()
        view = MineConfigView(self, is_owner=is_owner)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="mine")
    async def mine_prefix(self, ctx: commands.Context, *, comando: str) -> None:
        """Atalho de prefixo para comandos do console (Owner Only)."""
        if not await self.bot.is_owner(ctx.author):
            return
        if not self.service.is_running():
            await ctx.send(embed=EmbedBuilder.error_user("Servidor offline.").build())
            return
        logger.info("[MINE] %s executou: %s", ctx.author, comando)
        success, response = await self.service.send_command_with_response(comando)
        if success:
            await self._log_audit(ctx.guild.id, ctx.author, comando)
            clean_resp = response.strip() if response else "Comando executado com sucesso (sem retorno)."
            if len(clean_resp) > 1900:
                clean_resp = clean_resp[:1900] + "\n[...]"
            await ctx.send(
                embed=EmbedBuilder.success(f"Console: `{comando}`")
                .field("Saída", f"```txt\n{clean_resp}\n```")
                .build()
            )
        else:
            await ctx.send(embed=EmbedBuilder.error_internal(f"Falha ao executar:\n`{response}`").build())

    # ── Listeners ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Discord → Minecraft: repassa mensagens do canal vinculado."""
        if message.author.bot or not message.guild:
            return

        try:
            bot_prefixes = await self.bot.get_prefix(message)
            bot_prefixes = (bot_prefixes,) if isinstance(bot_prefixes, str) else tuple(bot_prefixes)
        except Exception:
            bot_prefixes = ("!",)

        # Ignorar comandos de outros bots comuns
        ignore_prefixes = bot_prefixes + ("/", ".", "?", "-", "~", "$", ">", "+")

        if message.content.startswith(ignore_prefixes):
            return

        channel = await self._get_mine_channel(message.guild.id)
        if not channel or message.channel.id != channel.id:
            return

        if not self.service.is_running():
            return

        if not self._allow_discord_to_mc(message.guild.id, message.author.id):
            return

        attachments_text = ""
        if message.attachments:
            suffix = (
                f" [+ {len(message.attachments)} anexo(s)]"
                if message.clean_content
                else f"[{len(message.attachments)} anexo(s)]"
            )
            attachments_text = suffix
            
        if message.stickers:
            attachments_text += f" [Sticker: {message.stickers[0].name}]"

        clean_content = message.clean_content.replace("\n", " | ") + attachments_text

        # Evitar envio de mensagens totalmente vazias (ex: mensagem de sistema)
        if not clean_content.strip():
            return

        await self.service.send_discord_chat_to_mc(message.author.display_name, clean_content)

    async def on_minecraft_chat(self, guild_id: int, event: BotEvent, data: dict[str, Any]) -> None:
        user = data.get("user", "???")
        msg = data.get("message", "")

        if data.get("is_advancement"):
            action = data.get("advancement_action")
            adv = data.get("advancement_name", "")
            
            if action == "completed the challenge":
                desc = f"🏆 completou o desafio: **{adv}**"
                color = Colors.ALERT
            elif action == "reached the goal":
                desc = f"🎯 alcançou a meta: **{adv}**"
                color = Colors.DEFAULT
            else:
                desc = f"🏆 obteve a conquista: **{adv}**"
                color = Colors.SUCCESS

            async def _send_adv(gid: int) -> None:
                channel = await self._get_mine_channel(gid)
                if not channel:
                    return
                embed = (
                    EmbedBuilder()
                    .author(name=user, icon_url=AVATAR_URL.format(username=user))
                    .description(desc)
                    .color(color)
                    .build()
                )
                await channel.send(embed=embed)
                
            await self._handle_minecraft_event(guild_id, _send_adv)
            return

        async def _send(gid: int) -> None:
            await self._send_webhook(gid, username=user, content=msg, avatar_url=AVATAR_URL.format(username=user))

        await self._handle_minecraft_event(guild_id, _send)

    async def on_minecraft_death(self, guild_id: int, event: BotEvent, data: dict[str, Any]) -> None:
        msg = data.get("message", "")
        user = data.get("user")
        details = data.get("details", msg)

        async def _send(gid: int) -> None:
            channel = await self._get_mine_channel(gid)
            if not channel:
                return
            embed_builder = EmbedBuilder()
            if user:
                embed_builder.author(name=user, icon_url=AVATAR_URL.format(username=user))
                embed_builder.description(f"💀 {details}")
            else:
                embed_builder.description(f"💀 **{msg}**")
            embed_builder.color(Colors.ERROR_INTERNAL)
            await channel.send(embed=embed_builder.build())

        await self._handle_minecraft_event(guild_id, _send)

    async def on_minecraft_join(self, guild_id: int, event: BotEvent, data: dict[str, Any]) -> None:
        user = data.get("user", "???")

        async def _send(gid: int) -> None:
            channel = await self._get_mine_channel(gid)
            if not channel:
                return
            embed = (
                EmbedBuilder()
                .author(name=user, icon_url=AVATAR_URL.format(username=user))
                .description("👋 entrou no servidor")
                .color(Colors.SUCCESS)
                .build()
            )
            await channel.send(embed=embed)

        await self._handle_minecraft_event(guild_id, _send)

    async def on_minecraft_leave(self, guild_id: int, event: BotEvent, data: dict[str, Any]) -> None:
        user = data.get("user", "???")

        async def _send(gid: int) -> None:
            channel = await self._get_mine_channel(gid)
            if not channel:
                return
            embed = (
                EmbedBuilder()
                .author(name=user, icon_url=AVATAR_URL.format(username=user))
                .description("🚪 saiu do servidor")
                .color(Colors.DEFAULT)
                .build()
            )
            await channel.send(embed=embed)

        await self._handle_minecraft_event(guild_id, _send)

    async def on_minecraft_player_command(
        self, guild_id: int, event: BotEvent, data: dict[str, Any]
    ) -> None:
        user = data.get("user", "???")
        cmd = data.get("command", "")

        if cmd == "status":
            is_online, players, ping, tps = await self.service.get_status()
            await self.service.send_command(
                f"say [Luna] Servidor Online | Jogadores: {players} | TPS: {tps}"
            )
        elif cmd == "ping":
            await self.service.send_command(f"say [Luna] Pong! O bot está te ouvindo, {user}!")
        elif cmd == "info":
            await self.service.send_command(
                f"say [Luna] Versão: {self.service.current_version} Paper"
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Remove o vínculo e a whitelist quando um membro sai do servidor."""
        # Nota: guild_id 0 no EventBus representa broadcast, mas aqui tratamos por guild
        old_nick = await self.service.unlink_player(member.guild.id, member.id)
        if old_nick:
            logger.info("Removendo %s da whitelist (saiu do Discord).", old_nick)
            if self.service.is_running():
                await self.service.ensure_whitelist(old_nick, add=False)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        """Garante a remoção se o membro for banido."""
        old_nick = await self.service.unlink_player(guild.id, user.id)
        if old_nick:
            logger.info("Removendo %s da whitelist (banido do Discord).", old_nick)
            if self.service.is_running():
                await self.service.ensure_whitelist(old_nick, add=False)


async def setup(bot: LunaBot) -> None:
    cog = MinecraftCog(bot)
    await bot.add_cog(cog)
    await cog.service.refresh_minecraft_guilds()
