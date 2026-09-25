"""
Cog de Auto-Update — comandos owner-only (com dev mode ativo) via Git.

Comandos:
  !update          → Verifica e mostra status do repositório
  !update check    → Verifica se há commits novos no remote
  !update now      → Descarta locais + git pull + instala deps + restart
  !update log      → Mostra os últimos commits locais
  !update auto on  → Ativa verificação automática periódica
  !update auto off → Desativa verificação automática
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from config.settings import OWNER_ID, BotEmojis, VERSION
from core.utils.embed_builder import EmbedBuilder

if TYPE_CHECKING:
    from core.bot import LunaBot

logger = logging.getLogger(__name__)

# Intervalo padrão de verificação automática (minutos)
_DEFAULT_CHECK_INTERVAL_MINUTES = 30


def _is_owner():
    """Check decorator — aceita apenas o owner com modo dev ativo."""

    async def predicate(ctx: commands.Context) -> bool:
        bot = getattr(ctx, 'bot', None)
        dev_mode = getattr(bot, '_dev_mode', False) if bot else False
        if ctx.author.id != OWNER_ID or not dev_mode:
            raise commands.NotOwner()
        return True

    return commands.check(predicate)


class UpdateCog(commands.Cog, name="Update"):
    """Gerenciamento de atualizações do bot via Git."""

    bot: LunaBot

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        self._auto_update_enabled: bool = False
        self._notify_channel_id: int | None = None

    async def cog_load(self) -> None:
        """Chamado quando o cog é carregado — restaura config persistida."""
        await self._load_settings()
        if self._auto_update_enabled:
            logger.info(
                " Auto-update restaurado do banco — ativando loop (%dmin).",
                _DEFAULT_CHECK_INTERVAL_MINUTES,
            )
            if not self._auto_check_loop.is_running():
                self._auto_check_loop.start()

    async def cog_unload(self) -> None:
        """Chamado quando o cog é descarregado."""
        if self._auto_check_loop.is_running():
            self._auto_check_loop.cancel()

    # ── Persistência de configuração ──────────────────────────

    async def _load_settings(self) -> None:
        """Carrega configurações de auto-update do banco (bot_settings)."""
        try:
            db = self.bot.db
            row = await db.fetchone(
                "SELECT value FROM bot_settings WHERE key = ?",
                ("auto_update_enabled",),
            )
            if row:
                self._auto_update_enabled = row[0] == "1"

            row = await db.fetchone(
                "SELECT value FROM bot_settings WHERE key = ?",
                ("auto_update_channel",),
            )
            if row and row[0]:
                self._notify_channel_id = int(row[0])
        except Exception:
            logger.debug("Falha ao carregar settings de auto-update — usando defaults.")

    async def _save_setting(self, key: str, value: str) -> None:
        """Salva uma configuração no banco (bot_settings) — upsert."""
        try:
            await self.bot.db.execute(
                "INSERT INTO bot_settings (key, value, updated_at) "
                "VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = datetime('now')",
                (key, value),
            )
            await self.bot.db.commit()
        except Exception:
            logger.debug("Falha ao salvar setting '%s' no banco.", key)

    # ── Task periódica ────────────────────────────────────────

    @tasks.loop(minutes=_DEFAULT_CHECK_INTERVAL_MINUTES)
    async def _auto_check_loop(self) -> None:
        """Verifica periodicamente se há updates e aplica automaticamente."""
        try:
            # Verificar carga do sistema antes de executar update
            if await self._system_overloaded():
                logger.debug(
                    "Sistema sobrecarregado — pulando verificação de update automática."
                )
                return

            updater = self.bot.updater_service
            if updater is None:
                return

            pending_deps = updater.has_pending_dependency_sync()
            check = await updater.check_for_updates()
            if check.error and not pending_deps:
                logger.error(
                    f"{BotEmojis.STATUS_DISABLED} Auto-update não conseguiu verificar updates: %s",
                    check.error,
                )
                await self._notify_owner(
                    f"{BotEmojis.STATUS_DISABLED} **Auto-update não conseguiu verificar updates.**\n"
                    f"Erro: `{check.error}`"
                )
                return

            if not check.has_update and not pending_deps:
                return

            if check.has_update:
                logger.info(
                    " Auto-update: %d commit(s) novo(s) detectado(s). Atualizando...",
                    check.commits_behind,
                )
            else:
                logger.info(
                    " Auto-update: sincronizando dependências pendentes antes do restart."
                )

            # Notificar o owner se tiver canal configurado
            if check.has_update:
                await self._notify_owner(
                    f" **Auto-update detectou {check.commits_behind} commit(s) novo(s).**\n"
                    f"Atualizando de `{check.short_local}` → `{check.short_remote}`...\n"
                    f"O bot irá reiniciar em instantes."
                )
            elif pending_deps:
                await self._notify_owner(
                    " **Auto-update encontrou dependências pendentes de sincronização.**\n"
                    "Tentando concluir a instalação antes do próximo restart."
                )

            # Aplicar update
            result = await updater.pull_and_update()

            if result.success and result.needs_restart:
                success_title = (
                    f"{BotEmojis.STATUS_ENABLED} **Dependências sincronizadas com sucesso!**"
                    if result.pending_deps_only
                    else f"{BotEmojis.STATUS_ENABLED} **Update aplicado com sucesso!**"
                )
                await self._notify_owner(
                    f"{success_title}\n"
                    f"{' Dependências atualizadas.' if result.deps_updated else ''}\n"
                    f" Iniciando processo de reiniciação (pode aguardar o desligamento do servidor do mine)..."
                )
                logger.info(" Auto-update concluído. Agendando restart...")
                await self._schedule_restart_with_minecraft_check(result)
            elif result.error:
                logger.error(
                    f"{BotEmojis.STATUS_DISABLED} Auto-update falhou: %s", result.error
                )
                await self._notify_owner(
                    f"{BotEmojis.STATUS_DISABLED} **Auto-update falhou:** {result.error}"
                )

        except Exception:
            logger.exception("Erro no loop de auto-update.")

    @_auto_check_loop.before_loop
    async def _before_auto_check(self) -> None:
        """Espera o bot estar pronto antes de iniciar o loop."""
        await self.bot.wait_until_ready()

    # ── Comandos ──────────────────────────────────────────────

    @commands.group(name="update", invoke_without_command=True)
    @_is_owner()
    async def update_group(self, ctx: commands.Context) -> None:
        """Mostra o status geral do repositório."""
        updater = self.bot.updater_service
        if updater is None:
            await ctx.send(
                embed=EmbedBuilder.error_internal(
                    "UpdaterService não disponível."
                ).build()
            )
            return

        async with ctx.typing():
            is_repo = await updater.is_git_repo()
            if not is_repo:
                await ctx.send(
                    embed=EmbedBuilder.error_internal(
                        "O diretório do bot não é um repositório Git."
                    ).build()
                )
                return

            current = await updater.get_current_version()
            branch = await updater.get_branch()
            remote_url = await updater.get_remote_url()
            has_changes = await updater.has_local_changes()

            embed = (
                EmbedBuilder.default()
                .title(" Status do Repositório")
                .field("Versão", f"`{VERSION}`", inline=True)
                .field("Commit", f"`{current}`", inline=True)
                .field("Branch", f"`{branch}`", inline=True)
                .field("Remote", f"`{remote_url}`", inline=False)
                .field(
                    "Mudanças locais",
                    (
                        f"{BotEmojis.STATUS_WARNING} Sim (pode causar conflitos)"
                        if has_changes
                        else f"{BotEmojis.STATUS_ENABLED} Nenhuma"
                    ),
                    inline=True,
                )
                .field(
                    "Auto-update",
                    f"{' Ativo' if self._auto_update_enabled else ' Inativo'}"
                    f" ({_DEFAULT_CHECK_INTERVAL_MINUTES}min)",
                    inline=True,
                )
                .footer(
                    "!update check • !update now • !update auto on/off • !update log"
                )
                .build()
            )

        await ctx.send(embed=embed)

    @update_group.command(name="check")
    @_is_owner()
    async def update_check(self, ctx: commands.Context) -> None:
        """Verifica se há commits novos no remote (não modifica nada)."""
        updater = self.bot.updater_service
        if updater is None:
            await ctx.send(
                embed=EmbedBuilder.error_internal(
                    "UpdaterService não disponível."
                ).build()
            )
            return

        msg = await ctx.send(
            embed=EmbedBuilder.default(" Verificando updates...").build()
        )

        check = await updater.check_for_updates()

        if check.error:
            embed = EmbedBuilder.error_internal(
                f"Falha ao verificar updates:\n```{check.error}```"
            ).build()
            await msg.edit(embed=embed)
            return

        if not check.has_update:
            embed = (
                EmbedBuilder.success("Bot está atualizado!")
                .field("Commit", f"`{check.short_local}`", inline=True)
                .field("Branch", f"`{check.branch}`", inline=True)
                .footer("Nenhum commit novo no remote.")
                .build()
            )
            await msg.edit(embed=embed)
            return

        # Há updates disponíveis
        changelog_text = ""
        if check.changelog:
            lines = [f"`{line}`" for line in check.changelog[:10]]
            changelog_text = "\n".join(lines)
            if len(check.changelog) > 10:
                changelog_text += f"\n*... e mais {len(check.changelog) - 10}*"

        embed = (
            EmbedBuilder.alert(
                f"**{check.commits_behind} commit(s) novo(s) disponível(is)!**"
            )
            .field("Local", f"`{check.short_local}`", inline=True)
            .field("Remote", f"`{check.short_remote}`", inline=True)
            .field("Branch", f"`{check.branch}`", inline=True)
        )

        if changelog_text:
            embed = embed.field("Changelog", changelog_text, inline=False)

        embed = embed.footer("Use !update now para aplicar a atualização.")
        await msg.edit(embed=embed.build())

    @update_group.command(name="now")
    @_is_owner()
    async def update_now(self, ctx: commands.Context) -> None:
        """Faz git pull, atualiza dependências se necessário, e reinicia o bot."""
        updater = self.bot.updater_service
        if updater is None:
            await ctx.send(
                embed=EmbedBuilder.error_internal(
                    "UpdaterService não disponível."
                ).build()
            )
            return

        # Executar update
        msg = await ctx.send(
            embed=EmbedBuilder.default(
                " Atualizando...",
                "Descartando mudanças locais e executando `git pull`...",
            ).build()
        )

        result = await updater.pull_and_update()

        if result.error:
            embed = (
                EmbedBuilder.error_internal(f"Falha no update:\n```{result.error}```")
                .footer("Verifique os logs para mais detalhes.")
                .build()
            )
            await msg.edit(embed=embed)
            return

        if result.success and result.needs_restart:
            changelog_text = ""
            if result.changelog:
                lines = [f"`{line}`" for line in result.changelog[:10]]
                changelog_text = "\n".join(lines)

            title = (
                "Dependências sincronizadas com sucesso!"
                if result.pending_deps_only
                else "Update aplicado com sucesso!"
            )
            embed = EmbedBuilder.success(title)
            if changelog_text:
                embed = embed.field("Commits aplicados", changelog_text, inline=False)
            if result.deps_updated:
                embed = embed.field(
                    "Dependências",
                    f"{BotEmojis.STATUS_ENABLED} Atualizadas",
                    inline=True,
                )

            embed = embed.field("Restart", " Preparando para reiniciar...", inline=False)
            await msg.edit(embed=embed.build())

            # Restart protegido (avalia shutdown do mine antes)
            await self._schedule_restart_with_minecraft_check(result, notify_msg=msg)
            return

        if not result.pulled:
            embed = EmbedBuilder.success(
                "Nenhum update disponível — já está atualizado."
            ).build()
            await msg.edit(embed=embed)
            return

    @update_group.command(name="log")
    @_is_owner()
    async def update_log(self, ctx: commands.Context) -> None:
        """Mostra os últimos 15 commits do repositório local."""
        updater = self.bot.updater_service
        if updater is None:
            await ctx.send(
                embed=EmbedBuilder.error_internal(
                    "UpdaterService não disponível."
                ).build()
            )
            return

        ok, stdout, stderr = await updater._git(
            "log", "--oneline", "--no-decorate", "--max-count=15"
        )

        if not ok:
            await ctx.send(
                embed=EmbedBuilder.error_internal(
                    f"Falha ao obter log:\n```{stderr.strip()}```"
                ).build()
            )
            return

        if not stdout.strip():
            await ctx.send(
                embed=EmbedBuilder.default(
                    " Histórico", "Nenhum commit encontrado."
                ).build()
            )
            return

        lines = [
            f"`{line.strip()}`" for line in stdout.strip().splitlines() if line.strip()
        ]
        log_text = "\n".join(lines)

        branch = await updater.get_branch()
        embed = (
            EmbedBuilder.default()
            .title(" Últimos Commits")
            .description(log_text)
            .footer(f"Branch: {branch} • Mostrando últimos {len(lines)} commits")
            .build()
        )

        await ctx.send(embed=embed)

    @update_group.group(name="auto", invoke_without_command=True)
    @_is_owner()
    async def update_auto(self, ctx: commands.Context) -> None:
        """Mostra o status do auto-update."""
        status = " **Ativo**" if self._auto_update_enabled else " **Inativo**"
        channel = (
            f"<#{self._notify_channel_id}>" if self._notify_channel_id else "Nenhum"
        )

        embed = (
            EmbedBuilder.default()
            .title(" Auto-Update")
            .field("Status", status, inline=True)
            .field(
                "Intervalo", f"{_DEFAULT_CHECK_INTERVAL_MINUTES} minutos", inline=True
            )
            .field("Canal de notificação", channel, inline=True)
            .footer("!update auto on • !update auto off • !update auto channel #canal")
            .build()
        )

        await ctx.send(embed=embed)

    @update_auto.command(name="on")
    @_is_owner()
    async def update_auto_on(self, ctx: commands.Context) -> None:
        """Ativa a verificação automática de updates."""
        if self._auto_update_enabled and self._auto_check_loop.is_running():
            await ctx.send(
                embed=EmbedBuilder.alert("Auto-update já está ativo.").build()
            )
            return

        self._auto_update_enabled = True
        # Salvar o canal atual como canal de notificação se não tiver um
        if self._notify_channel_id is None:
            self._notify_channel_id = ctx.channel.id

        # Persistir no banco para sobreviver a restarts
        await self._save_setting("auto_update_enabled", "1")
        await self._save_setting("auto_update_channel", str(self._notify_channel_id))

        if not self._auto_check_loop.is_running():
            self._auto_check_loop.start()

        embed = (
            EmbedBuilder.success(
                f"Auto-update **ativado**!\n"
                f"Verificação a cada **{_DEFAULT_CHECK_INTERVAL_MINUTES} minutos**.\n"
                f"Notificações em <#{self._notify_channel_id}>.\n"
                f" Configuração salva — sobrevive a restarts."
            )
            .footer("Use !update auto off para desativar.")
            .build()
        )

        await ctx.send(embed=embed)
        logger.info(" Auto-update ativado por %s.", ctx.author)

    @update_auto.command(name="off")
    @_is_owner()
    async def update_auto_off(self, ctx: commands.Context) -> None:
        """Desativa a verificação automática de updates."""
        if not self._auto_update_enabled:
            await ctx.send(
                embed=EmbedBuilder.alert("Auto-update já está inativo.").build()
            )
            return

        self._auto_update_enabled = False
        if self._auto_check_loop.is_running():
            self._auto_check_loop.cancel()

        # Persistir no banco
        await self._save_setting("auto_update_enabled", "0")

        embed = (
            EmbedBuilder.success(
                "Auto-update **desativado**.\n"
                " Configuração salva — não reativa sozinho após restart."
            )
            .footer("Use !update auto on para reativar.")
            .build()
        )

        await ctx.send(embed=embed)
        logger.info(" Auto-update desativado por %s.", ctx.author)

    @update_auto.command(name="channel")
    @_is_owner()
    async def update_auto_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        """Define o canal para notificações de auto-update."""
        self._notify_channel_id = channel.id

        # Persistir no banco
        await self._save_setting("auto_update_channel", str(channel.id))

        embed = EmbedBuilder.success(
            f"Canal de notificação definido para {channel.mention}.\n"
            f" Configuração salva."
        ).build()

        await ctx.send(embed=embed)

    # ── Helpers ───────────────────────────────────────────────

    async def _system_overloaded(self) -> bool:
        """Verifica se o sistema está sobrecarregado (alta carga de CPU/memória)."""
        try:
            import psutil

            # Verificar carga de CPU (>80%) ou memória (>90%)
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()

            if cpu_percent > 80 or memory.percent > 90:
                logger.debug(
                    "Sistema sobrecarregado: CPU %.1f%%, Memória %.1f%%",
                    cpu_percent,
                    memory.percent,
                )
                return True
        except ImportError:
            # psutil não disponível, assumir não sobrecarregado
            pass
        except Exception:
            logger.debug("Erro ao verificar carga do sistema.")

        return False

    async def _notify_owner(self, message: str) -> None:
        """Envia uma mensagem no canal de notificação configurado."""
        if self._notify_channel_id is None:
            return

        try:
            channel = self.bot.get_channel(self._notify_channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(self._notify_channel_id)

            if channel is not None and isinstance(channel, discord.abc.Messageable):
                embed = EmbedBuilder.default(" Auto-Update", message).build()
                await channel.send(embed=embed)
        except Exception:
            logger.debug(
                "Falha ao notificar canal %s sobre auto-update.",
                self._notify_channel_id,
            )

    async def _schedule_restart_with_minecraft_check(self, result, notify_msg=None) -> None:
        """Antes de reiniciar o bot, verifica se há necessidade de desligamento suave do Minecraft Server em até 5min."""
        import asyncio
        minecraft_service = self.bot.container.minecraft_service
        
        if minecraft_service and minecraft_service.is_running():
            logger.info("Minecraft rodando. Agendando desligamento para daqui a 5 minutos...")
            
            notice_msg = "O servidor de Minecraft será desligado em 5 minutos para manutenção e atualização do Bot!"
            await minecraft_service.send_command(f'tellraw @a {{"text":"{notice_msg}","color":"yellow"}}')
            await minecraft_service.send_command(f"say [LUNA] {notice_msg}")
            
            if notify_msg:
                try:
                    embed = notify_msg.embeds[0]
                    embed.description = embed.description or ""
                    embed.description += f"\n\n⏰ **Aguardando 5 minutos** para o fechamento pacífico do servidor do Minecraft..."
                    await notify_msg.edit(embed=embed)
                except Exception:
                    pass
            
            # Avisos a cada minuto
            for i in range(4, 0, -1):
                await asyncio.sleep(60)
                await minecraft_service.send_command(f'tellraw @a {{"text":"O servidor será desligado em {i} minuto(s)...","color":"yellow"}}')
                
            await asyncio.sleep(50)
            await minecraft_service.send_command(f'tellraw @a {{"text":"Salvando e desligando em 10 segundos...","color":"red"}}')
            await asyncio.sleep(10)
            
            # Fecha com segurança
            logger.info("Parando o Minecraft Server antes do restart do bot...")
            await minecraft_service.stop_server()
            
        else:
            logger.info("Minecraft Server está offline. Procedendo com o restart imediato.")
            
        await self._graceful_restart()

    async def _graceful_restart(self) -> None:
        """
        Encerra o **processo** de forma limpa para aplicar um update.

        IMPORTANTE: Python cacheia módulos em sys.modules. Fazer bot.close()
        e recriar LunaBot() no loop resiliente NÃO recarrega o código novo
        do git pull — os imports continuam com o código antigo em memória.

        A solução correta é **matar o processo** para que o systemd (ou o
        script start.sh) inicie um processo novo, que importa o código
        atualizado do disco.

        Fluxo:
          1. bot.close() — cleanup de DB, sessions, websocket (com timeout de segurança)
          2. os._exit(0) — encerra o processo imediatamente
          3. systemd detecta que o processo morreu (Restart=always)
          4. systemd inicia um novo processo com o código atualizado

        Sem systemd, o método tenta fazer restart via exec() no próprio
        processo; se isso falhar, cai para exit e depende de supervisor.
        """
        import asyncio
        import os
        import sys

        logger.info(" Iniciando restart para update — encerrando processo...")

        # Criar task para close para não bloquear se o loop estiver sendo cancelado
        close_task = asyncio.create_task(self.bot.close())
        try:
            # O auto-update roda num loop próprio; durante bot.close() esse loop
            # pode ser cancelado e interromper o restart antes do os._exit().
            # shield() evita que o close_task seja cancelado em cascata.
            await asyncio.wait_for(asyncio.shield(close_task), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("%s Timeout ao fechar bot (10s) — forçando exit.", BotEmojis.COMMON_WATCH)
        except asyncio.CancelledError:
            logger.warning(
                f"{BotEmojis.STATUS_WARNING} Restart cancelado durante bot.close() — forçando exit."
            )
        except Exception:
            logger.debug("Erro durante close() no restart — ignorando.")
        finally:
            # Dar tempo mínimo para o cleanup finalizar sem deixar que
            # cancelamentos impeçam o encerramento final do processo.
            try:
                await asyncio.sleep(1)
            except BaseException:
                pass

            # Primeiro tentamos reiniciar o próprio processo (exec),
            # o que funciona tanto com quanto sem systemd.
            # Se falhar, caímos para os._exit() e deixamos um supervisor
            # (systemd/start.sh/operator) subir novamente.
            # src/features/admin/cogs/update.py -> cogs(0), admin(1), features(2), src(3), raiz(4)
            project_root = Path(__file__).resolve().parents[4]
            bot_entrypoint = project_root / "src" / "main.py"
            restart_cmd = [sys.executable, str(bot_entrypoint)]

            logger.info(" Reiniciando processo via exec: %s", " ".join(restart_cmd))
            try:
                os.execv(sys.executable, restart_cmd)
            except Exception:
                logger.exception("Falha no exec de restart — forçando exit.")

            logger.info(
                " Processo encerrando — supervisor irá reiniciar com código novo."
            )
            os._exit(0)


async def setup(bot: LunaBot) -> None:
    await bot.add_cog(UpdateCog(bot))
