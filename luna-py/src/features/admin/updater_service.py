"""
Luna Bot — Serviço de Auto-Update via Git.

Responsabilidades:
  • Verificar se há commits novos no remote (git fetch + rev-parse)
  • Executar git pull para atualizar o código
  • Detectar mudanças em requirements.txt e instalar dependências
  • Sinalizar ao bot que um restart é necessário
  • Gerar changelog resumido (commits entre versões)

Fluxo:
  1. fetch origin
  2. comparar HEAD local vs origin/branch
  3. se diferente → git pull
  4. se requirements.txt mudou → pip install -r requirements.txt
  5. sinalizar restart (o bot.py cuida de encerrar e o systemd reinicia)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import BotEmojis

logger = logging.getLogger(__name__)

# Diretório raiz do projeto (onde está o .git)
# src/features/admin/updater_service.py -> admin (0), features (1), src (2), raiz (3)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class UpdateCheckResult:
    """Resultado de uma verificação de update."""

    has_update: bool = False
    local_commit: str = ""
    remote_commit: str = ""
    branch: str = ""
    commits_behind: int = 0
    changelog: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def short_local(self) -> str:
        return self.local_commit[:7] if self.local_commit else "?"

    @property
    def short_remote(self) -> str:
        return self.remote_commit[:7] if self.remote_commit else "?"

    @property
    def summary(self) -> str:
        if self.error:
            return f"{BotEmojis.STATUS_DISABLED} Erro: {self.error}"
        if not self.has_update:
            return f"{BotEmojis.STATUS_ENABLED} Atualizado ({self.short_local} @ {self.branch})"
        return (
            f" {self.commits_behind} commit(s) novo(s) "
            f"({self.short_local} → {self.short_remote})"
        )


@dataclass
class UpdateResult:
    """Resultado de um git pull."""

    success: bool = False
    pulled: bool = False
    deps_updated: bool = False
    needs_restart: bool = False
    pending_deps_only: bool = False
    changelog: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def summary(self) -> str:
        if self.error:
            return f"{BotEmojis.STATUS_DISABLED} Erro no update: {self.error}"
        if self.pending_deps_only:
            parts = [f"{BotEmojis.STATUS_ENABLED} Dependências sincronizadas"]
            if self.needs_restart:
                parts.append("(restart pendente)")
            return " ".join(parts)
        if not self.pulled:
            return f"{BotEmojis.STATUS_ENABLED} Nenhum update disponível."
        parts = [f"{BotEmojis.STATUS_ENABLED} Código atualizado"]
        if self.deps_updated:
            parts.append("+ dependências instaladas")
        if self.needs_restart:
            parts.append("(restart pendente)")
        return " ".join(parts)


class UpdaterService:
    """
    Serviço de auto-update via Git.

    Uso:
        updater = UpdaterService()

        # Verificar se há updates
        check = await updater.check_for_updates()
        if check.has_update:
            result = await updater.pull_and_update()
            if result.needs_restart:
                # Sinalizar restart ao bot
                ...
    """

    async def shutdown_bot(self, bot_instance=None):
        """Método para shutdown explícito antes de restart."""
        logger.info("Encerrando bot para aplicar update...")
        if bot_instance:
            try:
                await bot_instance.close()
                logger.info("Bot encerrado com sucesso.")
            except Exception as exc:
                logger.error(f"Erro ao encerrar bot: {exc}")
        else:
            logger.warning("Bot instance não fornecida para shutdown explícito.")
        logger.info("Processo será finalizado para restart.")

    def __init__(
        self,
        repo_path: Path | None = None,
        remote: str = "origin",
        branch: str | None = None,
        auto_install_deps: bool = True,
    ) -> None:
        self.repo_path = repo_path or _PROJECT_ROOT
        self.remote = remote
        self._branch = branch  # None = detectar automaticamente
        self._auto_install_deps = auto_install_deps
        self._requirements_hash: str | None = None
        self._deps_sync_pending: bool = False

        # Capturar hash do requirements.txt atual para comparar depois
        self._requirements_hash = self._hash_requirements()

    # ── Propriedades ──────────────────────────────────────────

    @property
    def requirements_path(self) -> Path:
        return self.repo_path / "requirements.txt"

    @property
    def constraints_path(self) -> Path:
        return self.repo_path / "constraints.txt"

    @property
    def venv_python(self) -> str:
        """Caminho do Python da venv (o mesmo que está rodando)."""
        return sys.executable

    # ── API Pública ───────────────────────────────────────────

    async def get_branch(self) -> str:
        """Retorna o branch atual."""
        if self._branch:
            return self._branch
        ok, stdout, _ = await self._git("rev-parse", "--abbrev-ref", "HEAD")
        branch = stdout.strip() if ok else "main"
        self._branch = branch
        return branch

    async def check_for_updates(self) -> UpdateCheckResult:
        """
        Faz fetch e verifica se há commits novos no remote.
        Não modifica nenhum arquivo local.
        """
        result = UpdateCheckResult()

        try:
            # 1. Verificar se é um repo git
            if not (self.repo_path / ".git").exists():
                result.error = "Diretório não é um repositório git."
                return result

            # 2. Obter branch
            branch = await self.get_branch()
            result.branch = branch

            # 3. Fetch do remote
            ok, _, stderr = await self._git("fetch", self.remote, "--quiet")
            if not ok:
                result.error = f"Falha no git fetch: {stderr.strip()}"
                return result

            # 4. Obter commit local e remote
            ok, local_hash, _ = await self._git("rev-parse", "HEAD")
            if not ok:
                result.error = "Falha ao obter commit local."
                return result
            result.local_commit = local_hash.strip()

            ok, remote_hash, _ = await self._git("rev-parse", f"{self.remote}/{branch}")
            if not ok:
                result.error = f"Falha ao obter commit de {self.remote}/{branch}."
                return result
            result.remote_commit = remote_hash.strip()

            # 5. Comparar
            if result.local_commit == result.remote_commit:
                result.has_update = False
                return result

            # 6. Contar commits atrás
            ok, count_str, _ = await self._git(
                "rev-list",
                "--count",
                f"HEAD..{self.remote}/{branch}",
            )
            result.commits_behind = int(count_str.strip()) if ok else 0
            result.has_update = result.commits_behind > 0

            # 7. Gerar changelog (últimos commits do remote que não temos)
            if result.has_update:
                ok, log_output, _ = await self._git(
                    "log",
                    "--oneline",
                    "--no-decorate",
                    f"HEAD..{self.remote}/{branch}",
                    "--max-count=15",
                )
                if ok and log_output.strip():
                    result.changelog = [
                        line.strip()
                        for line in log_output.strip().splitlines()
                        if line.strip()
                    ]

        except Exception as exc:
            result.error = f"Exceção: {exc}"
            logger.exception("Erro ao verificar updates.")

        return result

    async def pull_and_update(self) -> UpdateResult:
        """
        Executa git pull e, se necessário, atualiza dependências.
        Retorna informações sobre o que foi feito.
        """
        result = UpdateResult()

        try:
            current_req_hash = self._hash_requirements()

            # Se um pull anterior atualizou o requirements.txt mas o pip falhou,
            # tentamos recuperar antes de buscar novos commits.
            if self.has_pending_dependency_sync():
                if not self._auto_install_deps:
                    result.error = (
                        "requirements.txt mudou, mas a instalação automática de "
                        "dependências está desativada."
                    )
                    return result

                logger.warning(
                    "requirements.txt divergiu do ambiente atual — tentando "
                    "sincronizar dependências pendentes."
                )
                deps_ok = await self._install_dependencies()
                if not deps_ok:
                    result.error = (
                        "Falha ao instalar dependências pendentes. "
                        "O restart foi cancelado."
                    )
                    return result

                self._requirements_hash = current_req_hash
                self._deps_sync_pending = False
                result.success = True
                result.deps_updated = True
                result.needs_restart = True
                result.pending_deps_only = True
                return result

            # 1. Verificar se há updates primeiro
            check = await self.check_for_updates()
            if check.error:
                result.error = check.error
                return result

            if not check.has_update:
                result.pulled = False
                return result

            result.changelog = check.changelog

            # 2. Descartar mudanças locais para evitar conflito no pull.
            # (ex.: alterações temporárias geradas por scripts de teste)
            discard_ok, discarded_count, discard_error = (
                await self.discard_local_changes()
            )
            if not discard_ok:
                result.error = discard_error or "Falha ao descartar mudanças locais."
                return result
            if discarded_count > 0:
                logger.warning(
                    f"{BotEmojis.STATUS_WARNING} %d mudança(s) local(is) descartada(s) antes do update.",
                    discarded_count,
                )

            # 3. Salvar hash do requirements antes do pull
            old_req_hash = self._hash_requirements()

            # 4. Git pull
            branch = await self.get_branch()
            ok, stdout, stderr = await self._git(
                "pull", self.remote, branch, "--ff-only"
            )

            if not ok:
                # Tentar merge normal se fast-forward falhar
                ok, stdout, stderr = await self._git("pull", self.remote, branch)
                if not ok:
                    result.error = (
                        f"Falha no git pull: {stderr.strip()}\n"
                        "Pode haver conflitos locais. Resolva manualmente."
                    )
                    return result

            # 5. Verificar se requirements.txt mudou
            new_req_hash = self._hash_requirements()
            requirements_changed = (
                old_req_hash != new_req_hash and new_req_hash is not None
            )

            # 6. Instalar dependências se mudaram
            if requirements_changed and not self._auto_install_deps:
                result.pulled = True
                self._deps_sync_pending = True
                result.error = (
                    "Código atualizado, mas requirements.txt mudou e a instalação "
                    "automática de dependências está desativada. "
                    "O restart foi cancelado."
                )
                return result

            if requirements_changed and self._auto_install_deps:
                logger.info(" requirements.txt mudou — instalando dependências...")
                deps_ok = await self._install_dependencies()
                if not deps_ok:
                    result.pulled = True
                    self._deps_sync_pending = True
                    result.error = (
                        "Código atualizado, mas a instalação de dependências falhou. "
                        "O restart foi cancelado para evitar subir o bot quebrado. "
                        "Tente novamente após corrigir o ambiente."
                    )
                    logger.warning(
                        f"{BotEmojis.STATUS_WARNING} Restart cancelado após falha na instalação de dependências."
                    )
                    return result
                result.deps_updated = True
                self._deps_sync_pending = False

            result.pulled = True
            result.success = True
            logger.info(
                " Git pull concluído: %s → %s (%d commits)",
                check.short_local,
                check.short_remote,
                check.commits_behind,
            )

            # 7. O código foi atualizado, precisa de restart
            self._requirements_hash = new_req_hash
            self._deps_sync_pending = False
            result.needs_restart = True

        except Exception as exc:
            result.error = f"Exceção: {exc}"
            logger.exception("Erro durante o update.")

        return result

    async def get_current_version(self) -> str:
        """Retorna o hash curto do commit atual."""
        ok, stdout, _ = await self._git("rev-parse", "--short", "HEAD")
        return stdout.strip() if ok else "?"

    async def get_remote_url(self) -> str:
        """Retorna a URL do remote."""
        ok, stdout, _ = await self._git("remote", "get-url", self.remote)
        return stdout.strip() if ok else "?"

    async def is_git_repo(self) -> bool:
        """Verifica se o diretório é um repositório git."""
        return (self.repo_path / ".git").exists()

    async def has_local_changes(self) -> bool:
        """Verifica se há mudanças locais não commitadas."""
        ok, stdout, _ = await self._git("status", "--porcelain")
        if not ok:
            return False
        relevant = self._relevant_status_lines(stdout)
        return len(relevant) > 0

    async def discard_local_changes(self) -> tuple[bool, int, str | None]:
        """
        Descarta mudanças locais relevantes (tracked) antes de um update.
        Retorna (sucesso, qtd_descartada, erro).
        """
        ok, stdout, stderr = await self._git("status", "--porcelain")
        if not ok:
            return False, 0, f"Falha ao verificar mudanças locais: {stderr.strip()}"

        relevant = self._relevant_status_lines(stdout)
        if not relevant:
            return True, 0, None

        ok, _, stderr = await self._git("reset", "--hard", "HEAD")
        if not ok:
            return False, 0, f"Falha ao descartar mudanças locais: {stderr.strip()}"

        return True, len(relevant), None

    def has_pending_dependency_sync(self) -> bool:
        """Retorna True quando há um update já baixado aguardando sync de deps."""
        return self._deps_sync_pending

    # ── Métodos Internos ──────────────────────────────────────

    @staticmethod
    def _relevant_status_lines(status_output: str) -> list[str]:
        """Filtra mudanças locais ignorando arquivos de runtime/local."""
        lines = status_output.strip().splitlines()
        return [
            line
            for line in lines
            if not any(
                ignore in line
                for ignore in ("data/", ".env", "__pycache__", ".pyc", "cookies.txt")
            )
        ]

    def _hash_requirements(self) -> str | None:
        """Calcula o hash SHA256 do requirements.txt."""
        req = self.requirements_path
        if not req.exists():
            return None
        try:
            content = req.read_bytes()
            return hashlib.sha256(content).hexdigest()
        except OSError:
            return None

    async def _install_dependencies(self) -> bool:
        """Executa pip install -r requirements.txt na venv atual."""
        try:
            import platform

            arch = platform.machine().lower()

            # Ajustar timeout baseado na arquitetura (ARM pode ser mais lento)
            timeout = (
                300 if "arm" in arch or "aarch64" in arch else 180
            )  # 5min ARM, 3min x64

            logger.info(
                "Instalando dependências para arquitetura: %s (timeout: %ds)",
                arch,
                timeout,
            )

            install_cmd = [
                self.venv_python,
                "-m",
                "pip",
                "install",
                "-r",
                str(self.requirements_path),
                "--quiet",
                "--disable-pip-version-check",
                "--timeout=60",  # Timeout por pacote
            ]
            if self.constraints_path.exists():
                install_cmd.extend(["-c", str(self.constraints_path)])
                logger.info("Aplicando constraints.txt durante sync de dependências.")

            proc = await asyncio.create_subprocess_exec(
                *install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.repo_path),
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            if proc.returncode == 0:
                logger.info(
                    f"{BotEmojis.STATUS_ENABLED} Dependências atualizadas com sucesso."
                )
                return True

            logger.error(
                "Falha ao instalar dependências (exit %d): %s",
                proc.returncode,
                stderr.decode(errors="replace").strip(),
            )
            return False

        except asyncio.TimeoutError:
            logger.error("Timeout ao instalar dependências (%ds).", timeout)
            return False
        except Exception as exc:
            logger.exception("Erro ao instalar dependências: %s", exc)
            return False

    async def _git(self, *args: str) -> tuple[bool, str, str]:
        """
        Executa um comando git e retorna (sucesso, stdout, stderr).
        """
        env = os.environ.copy()

        # Nunca pedir senha/input interativamente
        env["GIT_TERMINAL_PROMPT"] = "0"

        # Resolver "Host key verification failed" para SSH remotes.
        # - StrictHostKeyChecking=accept-new: aceita a host key na primeira
        #   conexão automaticamente (sem prompt), mas rejeita se mudar depois.
        # - Mantém o UserKnownHostsFile padrão (~/.ssh/known_hosts) para que
        #   a chave aceita persista entre execuções.
        # - Se já existir um GIT_SSH_COMMAND customizado, não sobrescrever.
        if "GIT_SSH_COMMAND" not in env:
            env["GIT_SSH_COMMAND"] = (
                "ssh -o StrictHostKeyChecking=accept-new"
                " -o BatchMode=yes"
                " -o ConnectTimeout=10"
            )

        try:
            # Aumentar timeout para operações git maiores (pull, fetch)
            timeout = 120  # 2 minutos
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.repo_path),
                env=env,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            success = proc.returncode == 0

            if not success:
                logger.debug(
                    "git %s → exit %d | stderr: %s",
                    " ".join(args),
                    proc.returncode,
                    stderr.strip(),
                )

            return success, stdout, stderr

        except asyncio.TimeoutError:
            logger.error("Timeout executando: git %s (%ds)", " ".join(args), timeout)
            return False, "", f"Timeout ({timeout}s)"
        except FileNotFoundError:
            logger.error("git não encontrado no PATH.")
            return False, "", "git não instalado"
        except Exception as exc:
            logger.exception("Erro ao executar git: %s", exc)
            return False, "", str(exc)
