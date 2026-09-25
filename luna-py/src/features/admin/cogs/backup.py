from __future__ import annotations

import os
import logging
from datetime import datetime
from pathlib import Path

import discord
from discord.ext import commands, tasks

from core.bot import LunaBot
from core.utils.embed_builder import EmbedBuilder
from config.settings import BotEmojis

logger = logging.getLogger(__name__)


class BackupCog(commands.Cog):
    """Cog para gerenciar backups automáticos e manuais do banco de dados SQLite."""

    def __init__(self, bot: LunaBot) -> None:
        self.bot = bot
        # parents[3] = src/  |  parents[4] = Luna-Bot/
        self._src_dir = Path(__file__).resolve().parents[3]
        self._project_dir = Path(__file__).resolve().parents[4]
        self.backup_dir = self._project_dir / "data" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.auto_backup.start()

    def cog_unload(self) -> None:
        self.auto_backup.cancel()

    @tasks.loop(hours=24)
    async def auto_backup(self) -> None:
        """Task periódica que cria backup a cada 24 horas."""
        try:
            filename = await self._run_backup()
            logger.info("Backup automático concluído com sucesso: %s", filename)
        except Exception:
            logger.exception("Falha no backup automático")

    async def _run_backup(self) -> str:
        """Cria um backup consistente do banco de dados SQLite usando VACUUM INTO."""
        db_path = self._src_dir / "data" / "luna.db"
        if not db_path.exists():
            raise FileNotFoundError(f"Banco de dados não encontrado em {db_path}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"luna_backup_{timestamp}.db"
        dest_path = self.backup_dir / backup_filename

        # Usar VACUUM INTO para copiar de forma segura o SQLite mesmo sob modo WAL ativo
        dest_abs_path = str(dest_path.resolve())
        # Escapa aspas simples no path se houver (improvável em ambientes normais, mas boa prática)
        safe_path = dest_abs_path.replace("'", "''")
        
        await self.bot.db.execute(f"VACUUM INTO '{safe_path}'")

        # Limpar backups antigos, mantendo apenas os 7 mais recentes
        backups = sorted(
            [f for f in os.listdir(self.backup_dir) if f.startswith("luna_backup_") and f.endswith(".db")],
            key=lambda x: (self.backup_dir / x).stat().st_mtime
        )

        while len(backups) > 7:
            oldest = backups.pop(0)
            try:
                os.remove(self.backup_dir / oldest)
                logger.info("Backup antigo removido: %s", oldest)
            except Exception:
                logger.exception("Erro ao remover backup antigo %s", oldest)

        return backup_filename

    @commands.hybrid_command(
        name="backup",
        description="[Owner] Cria um backup manual do banco de dados do bot"
    )
    @commands.is_owner()
    async def backup_cmd(self, ctx: commands.Context) -> None:
        await ctx.defer(ephemeral=True)
        try:
            filename = await self._run_backup()
            embed = (
                EmbedBuilder.success("Backup do banco de dados concluído!")
                .description(
                    f"{BotEmojis.BOX_CHECK} O backup foi gerado com sucesso.\n"
                    f"**Arquivo:** `{filename}`"
                )
                .build()
            )
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception("Comando backup falhou")
            embed = EmbedBuilder.error_user(f"Falha ao criar o backup: {str(e)}").build()
            await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackupCog(bot))
