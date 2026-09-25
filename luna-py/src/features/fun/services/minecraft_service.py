"""
Serviço de gerenciamento do servidor Minecraft.

Responsabilidades:
    - Ciclo de vida do processo Java (start / stop)
    - Envio de comandos via RCON (com fallback para stdin)
    - Leitura de logs via stdout e emissão de eventos no EventBus
    - Backup, restauração e wipe de mundos
    - Consulta de status via mcstatus
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Optional, Tuple, List

import aiohttp
from mcstatus import JavaServer

from core.events import EventBus, BotEvent
from features.fun.rcon.minecraft_rcon import MinecraftRCON, RCONError, RCONAuthError
from features.fun.services.minecraft_log_parser import MinecraftLogParser
from features.fun.repositories.minecraft_repository import MinecraftRepository

logger = logging.getLogger(__name__)

# Limite de comandos RCON pendentes; tellraw do chat bridge é descartável (#5)
_RCON_MAX_PENDING = 50
_DISCORD_MC_MAX_CHARS = 256
_VPN_MAX_CONCURRENT = 10
_VPN_MAX_RETRIES = 3
_MAX_GUILDS_IN_MEMORY = 100
_LOGS_READLINE_TIMEOUT = 30.0

# ── Caminhos ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(os.getenv("LUNA_PROJECT_ROOT", str(Path.cwd())))
SERVER_DIR = Path(os.getenv("MINECRAFT_SERVER_DIR", str(PROJECT_ROOT / "data" / "minecraft_server")))
TEMPLATE_DIR = Path(os.getenv("MINECRAFT_TEMPLATE_DIR", str(PROJECT_ROOT / "minecraft-templete")))
BACKUP_DIR = Path(os.getenv("MINECRAFT_BACKUP_DIR", str(PROJECT_ROOT / "data" / "minecraft_backups")))


class MinecraftService:
    """
    Gerencia o servidor Minecraft local como subprocesso.

    Comunicação com o servidor:
        - Comandos  → RCON (protocolo TCP, padrão da indústria)
                     com fallback automático para stdin se RCON não estiver
                     disponível (ex: durante a inicialização)
        - Eventos   → Leitura contínua do stdout (join/leave/chat/mortes)
    """

    def __init__(self, event_bus: EventBus, repo: MinecraftRepository) -> None:
        self.event_bus = event_bus
        self.repo = repo
        self._parser = MinecraftLogParser()

        self.server_dir = str(SERVER_DIR)
        self.template_dir = str(TEMPLATE_DIR)

        self._jar_name: Optional[str] = None
        self.process: Optional[asyncio.subprocess.Process] = None
        self.current_version = "26.1.2"
        self.current_tps = "20.0"

        # Host / porta do servidor (Java Edition)
        self.mc_host = os.getenv("MINECRAFT_HOST", "127.0.0.1")
        self.mc_port = int(os.getenv("MINECRAFT_PORT", "25565"))
        self.mc_address = f"{self.mc_host}:{self.mc_port}"

        # RCON
        self._rcon_port = int(os.getenv("MINECRAFT_RCON_PORT", "25575"))
        _rcon_password = os.getenv("MINECRAFT_RCON_PASSWORD")
        if not _rcon_password or _rcon_password == "luna_rcon_secret":
            _rcon_password = secrets.token_urlsafe(16)
            logger.warning(
                "ATENÇÃO DE SEGURANÇA: MINECRAFT_RCON_PASSWORD não definida ou padrão detectada. "
                "Uma senha dinâmica forte e temporária foi gerada automaticamente para esta sessão."
            )
        self._rcon_password = _rcon_password
        self._rcon: Optional[MinecraftRCON] = None
        self._rcon_lock = asyncio.Lock()

        # Guilds que recebem eventos MC (env ou cache de canais configurados)
        self._allowed_guilds: list[int] = []
        self._guilds_with_mc_channel: set[int] = set()

        # Locks e flags de controle
        self._action_lock = asyncio.Lock()
        self._is_stopping = False
        self._log_task: Optional[asyncio.Task] = None
        self._auth_warning_logged = False

        # Backpressure RCON (#5)
        self._command_pending = 0
        self._command_pending_lock = asyncio.Lock()

        # HTTP compartilhado para verificação de VPN (#3)
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._vpn_sem = asyncio.Semaphore(_VPN_MAX_CONCURRENT)
        self._vpn_cache: dict[str, bool] = {}

        # Referências de tasks fire-and-forget
        self._background_tasks: set[asyncio.Task] = set()
        self._background_task_sem = asyncio.Semaphore(50)

        SERVER_DIR.mkdir(parents=True, exist_ok=True)

    # ── Verificações ───────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        """Retorna True se o processo Java está ativo."""
        return self.process is not None and self.process.returncode is None

    def _sync_is_installed(self) -> bool:
        if self._jar_name and os.path.exists(os.path.join(self.server_dir, self._jar_name)):
            return True
        if os.path.exists(self.server_dir):
            for f in os.listdir(self.server_dir):
                if f.endswith(".jar"):
                    self._jar_name = f
                    return True
        return False

    async def is_installed(self) -> bool:
        return await asyncio.to_thread(self._sync_is_installed)

    def has_auth_plugin(self) -> bool:
        """True se um plugin de autenticação (AuthMe) estiver instalado."""
        return any("authme" in name.lower() for name in self._sync_list_plugins())

    async def refresh_minecraft_guilds(self) -> None:
        """Recarrega guilds com canal MC configurado (cache em memória, máx 100)."""
        if self._allowed_guilds:
            return
        ids = await self.repo.get_guilds_with_minecraft_channel()
        self._guilds_with_mc_channel = set(ids[:_MAX_GUILDS_IN_MEMORY])

    def register_minecraft_guild(self, guild_id: int) -> None:
        """Registra guild após /mc-setup sem esperar restart."""
        if not self._allowed_guilds:
            self._guilds_with_mc_channel.add(guild_id)

    async def get_event_guild_ids(self) -> list[int]:
        """Guilds que devem receber eventos MC (join, chat, morte, etc.)."""
        if self._allowed_guilds:
            return list(self._allowed_guilds)
        if not self._guilds_with_mc_channel:
            await self.refresh_minecraft_guilds()
        return list(self._guilds_with_mc_channel)

    async def _ensure_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self) -> None:
        """Libera recursos HTTP do service (chamado no shutdown do bot)."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

    # ── IP Público ─────────────────────────────────────────────────────────────

    async def get_public_ip(self) -> str:
        hide_ip = os.getenv("MINECRAFT_HIDE_IP", "false").lower() in ("true", "1", "yes")
        domain = os.getenv("MINECRAFT_DOMAIN", "").strip()

        if hide_ip:
            return domain or "Ocultado por segurança"

        if domain:
            return domain

        import socket

        providers = [
            "https://ifconfig.me/ip",
            "https://api4.my-ip.io/ip",
            "https://ipv4.icanhazip.com",
        ]
        for url in providers:
            try:
                connector = aiohttp.TCPConnector(family=socket.AF_INET)
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            return (await resp.text()).strip()
            except Exception as exc:
                logger.debug("Falha ao obter IP de %s: %s", url, exc)
        return "Desconhecido"

    # ── Java ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_java_version(java_path: str) -> Optional[Tuple[int, ...]]:
        """Executa `java -version` e extrai a versão como tupla numérica."""
        import subprocess

        try:
            result = subprocess.run(
                [java_path, "-version"],
                capture_output=True, text=True, timeout=10,
            )
            # `java -version` imprime no stderr
            output = result.stderr or result.stdout or ""
            # Padrão: "21.0.3" ou "1.8.0_412" etc.
            match = re.search(r'"(\d+[\d._]*)"', output)
            if match:
                raw = match.group(1).replace("_", ".")
                return tuple(int(x) for x in raw.split(".") if x.isdigit())
        except Exception:
            pass
        return None

    def _get_java_path(self) -> Optional[str]:
        bin_name = "java.exe" if os.name == "nt" else "java"

        # 1. JRE local dentro do server_dir — retorno imediato (empacotado)
        local_java = os.path.join(self.server_dir, "jre", "bin", bin_name)
        if os.path.exists(local_java):
            return local_java

        # 2. Caminho explícito do operador — retorno imediato (override manual)
        custom_java = os.getenv("MINECRAFT_JAVA_PATH")
        if custom_java and os.path.exists(custom_java):
            return custom_java

        # 3. Coleta TODOS os candidatos (JAVA_HOME, PATH, instalações) e
        #    seleciona o de versão mais alta — evita que um JAVA_HOME antigo
        #    impeça a descoberta de versões mais recentes.
        candidates: list[str] = []

        java_home = os.getenv("JAVA_HOME")
        if java_home:
            home_java = os.path.join(java_home, "bin", bin_name)
            if os.path.exists(home_java):
                candidates.append(home_java)

        path_java = shutil.which(bin_name) or shutil.which("java")
        if path_java:
            candidates.append(path_java)

        # Busca robusta em diretórios padrões de instalação no Windows
        if os.name == "nt":
            common_roots = [
                r"C:\Program Files\Java",
                r"C:\Program Files\Eclipse Adoptium",
                r"C:\Program Files\Eclipse Foundation",
                r"C:\Program Files\Amazon Corretto",
                r"C:\Program Files\Microsoft",
                r"C:\Program Files\Zulu",
                r"C:\Program Files\BellSoft",
                r"C:\Program Files (x86)\Java",
                r"C:\Program Files\Common Files\Oracle\Java\javapath",
            ]
            for root in common_roots:
                if not os.path.exists(root):
                    continue
                direct_java = os.path.join(root, bin_name)
                if os.path.exists(direct_java):
                    candidates.append(direct_java)
                try:
                    for entry in os.scandir(root):
                        if entry.is_dir():
                            java_candidate = os.path.join(entry.path, "bin", bin_name)
                            if os.path.exists(java_candidate):
                                candidates.append(java_candidate)
                except Exception:
                    pass

        if not candidates:
            return None

        # Seleciona o Java com a versão mais alta
        best_path: Optional[str] = None
        best_version: Tuple[int, ...] = ()
        seen_paths: set[str] = set()

        for candidate in candidates:
            try:
                resolved = os.path.realpath(candidate)
            except Exception:
                resolved = candidate
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            version = self._parse_java_version(candidate)
            if version is not None and version > best_version:
                best_version = version
                best_path = candidate

        if best_path:
            logger.info(
                "Java selecionado: versão %s em %s (de %d candidatos)",
                ".".join(str(x) for x in best_version), best_path, len(seen_paths),
            )
            return best_path

        # Nenhum respondeu a -version — retorna o primeiro encontrado como fallback
        return candidates[0]

    # ── Instalação / Template ──────────────────────────────────────────────────

    def _sync_install(self) -> bool:
        template_jar = None
        for root, dirs, files in os.walk(self.template_dir):
            rel_path = os.path.relpath(root, self.template_dir)
            dest_dir = os.path.join(self.server_dir, rel_path)
            os.makedirs(dest_dir, exist_ok=True)
            for file in files:
                src = os.path.join(root, file)
                dst = os.path.join(dest_dir, file)
                try:
                    shutil.copy2(src, dst)
                except Exception as exc:
                    logger.warning("Não conseguiu copiar %s: %s", file, exc)
                if file.endswith(".jar") and rel_path == ".":
                    template_jar = file
        if template_jar:
            self._jar_name = template_jar
            return True
        logger.error("Nenhum .jar encontrado na raiz do template.")
        return False

    async def install_server(self) -> bool:
        async with self._action_lock:
            if not os.path.exists(self.template_dir):
                logger.error("Template não encontrado em %s", self.template_dir)
                return False
            success = await asyncio.to_thread(self._sync_install)
            if not success:
                return False
            await asyncio.to_thread(self._setup_properties)
            await asyncio.to_thread(self._patch_authme_config)
            return True

    def _setup_properties(self) -> None:
        # EULA
        with open(os.path.join(self.server_dir, "eula.txt"), "w") as f:
            f.write("eula=true\n")

        # Força online-mode=false e habilita RCON
        props_path = os.path.join(self.server_dir, "server.properties")
        
        # Preserva o estado da whitelist se já estiver configurado no arquivo
        whitelist_val = "true"
        if os.path.exists(props_path):
            try:
                with open(props_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if "=" in line:
                            parts = line.split("=", 1)
                            if parts[0].strip() == "white-list":
                                whitelist_val = parts[1].strip()
                                break
            except Exception as exc:
                logger.warning("Falha ao ler whitelist do server.properties: %s", exc)

        rcon_props = {
            "online-mode": "false",
            "white-list": whitelist_val,
            "enable-rcon": "true",
            "rcon.port": str(self._rcon_port),
            "rcon.password": self._rcon_password,
        }

        lines: list[str] = []
        if os.path.exists(props_path):
            with open(props_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

        # Substitui valores existentes
        props_found: set[str] = set()
        new_lines: list[str] = []
        for line in lines:
            key = line.split("=")[0].strip() if "=" in line else ""
            if key in rcon_props:
                new_lines.append(f"{key}={rcon_props[key]}\n")
                props_found.add(key)
            else:
                new_lines.append(line)

        # Adiciona propriedades que não existiam
        for key, value in rcon_props.items():
            if key not in props_found:
                new_lines.append(f"{key}={value}\n")

        with open(props_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def _patch_authme_config(self) -> None:
        """Garante preset Luna no AuthMe (dialog off, sem kick de nao-registrado)."""
        config_path = Path(self.server_dir) / "plugins" / "AuthMe" / "config.yml"
        if not config_path.exists():
            return
        try:
            text = config_path.read_text(encoding="utf-8")
            text = text.replace("kickNonRegistered: true", "kickNonRegistered: false")
            text = text.replace("teleportUnAuthedToSpawn: true", "teleportUnAuthedToSpawn: false")
            text = text.replace("enableAntiBot: true", "enableAntiBot: false")
            text = text.replace("loginCancelKicks: true", "loginCancelKicks: false")
            text = text.replace("allowCloseWithEscape: false", "allowCloseWithEscape: true")
            text = text.replace("showForgotPasswordButton: true", "showForgotPasswordButton: false")

            # Desativa preJoin.enable e postJoin.enable de forma segura
            # (parsing linha-a-linha evita catastrophic backtracking das regex anteriores)
            lines = text.splitlines(keepends=True)
            in_section: str | None = None  # "preJoin" ou "postJoin"
            patched_pre = False
            patched_post = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                # Detecta entrada em seção preJoin / postJoin (chave YAML)
                if stripped.startswith("preJoin:") and not patched_pre:
                    in_section = "preJoin"
                elif stripped.startswith("postJoin:") and not patched_post:
                    in_section = "postJoin"
                elif in_section and stripped.startswith("enable:"):
                    # Substitui "enable: true" → "enable: false" dentro da seção correta
                    lines[i] = line.replace("enable: true", "enable: false")
                    if in_section == "preJoin":
                        patched_pre = True
                    else:
                        patched_post = True
                    in_section = None
                elif in_section and stripped and not stripped.startswith("#") and ":" in stripped:
                    # Saiu do bloco de sub-chaves do preJoin/postJoin sem encontrar enable
                    key = stripped.split(":")[0].strip()
                    if key not in (
                        "enable", "showCancelButton", "allowCloseWithEscape",
                        "registerCancelKicks", "loginCancelKicks",
                    ):
                        in_section = None

            text = "".join(lines)
            config_path.write_text(text, encoding="utf-8")
            logger.info("AuthMe config.yml atualizado com preset Luna.")
        except Exception as exc:
            logger.warning("Falha ao aplicar preset AuthMe: %s", exc)

    # ── Iniciar / Parar ────────────────────────────────────────────────────────

    async def start_server(self, ram_mb: int = 2048) -> bool:
        async with self._action_lock:
            if self.process is not None and self.process.returncode is None:
                return True
            if not await self.is_installed():
                return False

            java_path = await asyncio.to_thread(self._get_java_path)
            if not java_path:
                logger.error("Java não encontrado.")
                return False

            # Diagnóstico simplificado de Java
            logger.info("Java detectado em: %s", java_path)

            try:
                await asyncio.to_thread(self._setup_properties)
            except Exception as exc:
                logger.error("Falha ao configurar server.properties: %s", exc, exc_info=True)
                return False

            try:
                await asyncio.to_thread(self._patch_authme_config)
            except Exception as exc:
                logger.error("Falha ao patchear AuthMe: %s", exc, exc_info=True)
                return False

            try:
                await self._sync_whitelist_file()
            except Exception as exc:
                logger.error("Falha ao sincronizar whitelist: %s", exc, exc_info=True)
                return False

            # Carrega guilds permitidos na memória
            env_guilds = os.getenv("MINECRAFT_ALLOWED_GUILDS", "")
            self._allowed_guilds = [
                int(x.strip()) for x in env_guilds.split(",") if x.strip().isdigit()
            ]
            await self.refresh_minecraft_guilds()

            if not self.has_auth_plugin():
                logger.warning("Aviso: Servidor offline (online-mode=false) sem o plugin AuthMe instalado.")
                self._auth_warning_logged = True
            else:
                self._auth_warning_logged = False


            jar_name = self._jar_name
            logger.info("Iniciando %s com %sMB RAM (Aikar's Flags)...", jar_name, ram_mb)

            aikar_flags = [
                "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled",
                "-XX:MaxGCPauseMillis=200", "-XX:+UnlockExperimentalVMOptions",
                "-XX:+DisableExplicitGC", "-XX:+AlwaysPreTouch",
                "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40",
                "-XX:G1HeapRegionSize=8M", "-XX:G1ReservePercent=20",
                "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
                "-XX:InitiatingHeapOccupancyPercent=15",
                "-XX:G1MixedGCLiveThresholdPercent=90",
                "-XX:G1RSetUpdatingPauseTimePercent=5",
                "-XX:SurvivorRatio=32", "-XX:+PerfDisableSharedMem",
                "-XX:MaxTenuringThreshold=1",
                "-Dusing.aikars.flags=https://mcflags.emc.gs",
                "-Daikars.new.flags=true",
            ]

            cmd_args = (
                [java_path, f"-Xms{ram_mb}M", f"-Xmx{ram_mb}M"]
                + aikar_flags
                + ["-jar", jar_name, "nogui"]
            )

            try:
                self.process = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    cwd=self.server_dir,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                self._log_task = asyncio.create_task(self._read_logs_loop())
                return True
            except Exception as exc:
                logger.error("Erro ao iniciar o servidor: %s", exc, exc_info=True)
                self.process = None
                return False

    async def stop_server(self) -> bool:
        async with self._action_lock:
            if self.process is None or self.process.returncode is not None:
                return False
            self._is_stopping = True
            try:
                # Tenta stop via RCON primeiro, fallback para stdin
                try:
                    await self.send_command("stop")
                except Exception:
                    pass

                try:
                    await asyncio.wait_for(self.process.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    self.process.terminate()

                if self._log_task:
                    self._log_task.cancel()
                    self._log_task = None

                await self._close_rcon()
                self.process = None
                return True
            except Exception as exc:
                logger.error("Erro ao parar o servidor: %s", exc)
                return False
            finally:
                self._is_stopping = False

    # ── RCON ───────────────────────────────────────────────────────────────────

    async def _get_rcon(self) -> Optional[MinecraftRCON]:
        """
        Retorna a conexão RCON ativa, criando/reconectando se necessário.

        Retorna None se não conseguir conectar (ex: servidor ainda subindo).
        """
        async with self._rcon_lock:
            if self._rcon and self._rcon.is_connected():
                return self._rcon

            rcon = MinecraftRCON(
                host=self.mc_host,
                port=self._rcon_port,
                password=self._rcon_password,
            )
            try:
                await rcon.connect()
                self._rcon = rcon
                logger.info("RCON conectado ao servidor Minecraft.")
                return self._rcon
            except RCONAuthError:
                logger.error(
                    "RCON: senha incorreta — verifique MINECRAFT_RCON_PASSWORD e rcon.password no server.properties."
                )
                await rcon.close()
                return None
            except RCONError as exc:
                logger.debug("RCON indisponível (servidor ainda pode estar subindo): %s", exc)
                await rcon.close()
                return None

    async def _close_rcon(self) -> None:
        async with self._rcon_lock:
            if self._rcon:
                await self._rcon.close()
                self._rcon = None

    @staticmethod
    def _is_low_priority_command(command: str) -> bool:
        """Tellraw do bridge Discord→MC pode ser descartado sob pressão."""
        return command.strip().startswith('tellraw @a {"text":"[Discord]')

    async def send_command(self, command: str, *, low_priority: bool = False) -> bool:
        """
        Envia um comando ao servidor.

        Estratégia:
            1. Tenta via RCON (resposta confirmada).
            2. Se RCON não disponível, usa stdin como fallback.

        low_priority: se True e a fila estiver cheia, descarta (chat bridge).

        Retorna True se o comando foi enviado com sucesso.
        """
        if not self.is_running():
            return False

        if "\n" in command or "\r" in command:
            raise ValueError("O comando não pode conter quebras de linha (evitando injeção de múltiplos comandos).")

        is_low = low_priority or self._is_low_priority_command(command)
        async with self._command_pending_lock:
            if is_low and self._command_pending >= _RCON_MAX_PENDING:
                logger.debug(
                    "RCON: descartando comando de baixa prioridade (fila: %d).",
                    self._command_pending,
                )
                return False
            self._command_pending += 1

        try:
            # Tentativa via RCON
            rcon = await self._get_rcon()
            if rcon:
                try:
                    await rcon.send_command(command)
                    return True
                except RCONError as exc:
                    logger.warning("RCON falhou (%s), usando fallback stdin.", exc)
                    await self._close_rcon()

            # Fallback: stdin
            if not self.process or not self.process.stdin:
                return False
            try:
                self.process.stdin.write(f"{command}\n".encode())
                await self.process.stdin.drain()
                return True
            except Exception as exc:
                logger.error("Erro ao enviar comando via stdin: %s", exc)
                return False
        finally:
            async with self._command_pending_lock:
                self._command_pending -= 1

    async def send_discord_chat_to_mc(self, display_name: str, content: str) -> bool:
        """Envia mensagem do Discord ao chat in-game (truncada + baixa prioridade)."""
        if len(content) > _DISCORD_MC_MAX_CHARS:
            content = content[: _DISCORD_MC_MAX_CHARS - 3] + "..."
        text_obj = f"[Discord] {display_name}: {content}"
        json_text = json.dumps(text_obj)
        command = f'tellraw @a {{"text":{json_text},"color":"aqua"}}'
        return await self.send_command(command, low_priority=True)

    async def send_command_with_response(self, command: str) -> tuple[bool, str]:
        """
        Envia um comando ao servidor e retorna (sucesso, resposta).

        Estratégia:
            1. Tenta via RCON (resposta confirmada do console).
            2. Se RCON não disponível, usa stdin como fallback.
        """
        if not self.is_running():
            return False, "Servidor offline."

        if "\n" in command or "\r" in command:
            raise ValueError("O comando não pode conter quebras de linha.")

        # Tentativa via RCON
        rcon = await self._get_rcon()
        if rcon:
            try:
                response = await rcon.send_command(command)
                return True, response
            except RCONError as exc:
                logger.warning("RCON falhou (%s), usando fallback stdin.", exc)
                # Invalida a conexão para reconectar na próxima
                await self._close_rcon()

        # Fallback: stdin
        if not self.process or not self.process.stdin:
            return False, "Processo ou stdin indisponível."
        try:
            self.process.stdin.write(f"{command}\n".encode())
            await self.process.stdin.drain()
            return True, "Enviado via stdin (sem resposta do console)."
        except Exception as exc:
            logger.error("Erro ao enviar comando via stdin: %s", exc)
            return False, f"Erro ao enviar: {exc}"

    async def _sync_whitelist_file(self) -> None:
        """
        Sincroniza fisicamente a whitelist offline no arquivo whitelist.json
        com os nicks vinculados no banco de dados enquanto o servidor está offline.
        """
        import hashlib
        import json
        import uuid

        def get_offline_uuid(name: str) -> str:
            # Algoritmo padrão para offline player uuid do Minecraft:
            hash_bytes = hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest()
            hash_list = list(hash_bytes)
            hash_list[6] = (hash_list[6] & 0x0f) | 0x30
            hash_list[8] = (hash_list[8] & 0x3f) | 0x80
            adjusted_bytes = bytes(hash_list)
            return str(uuid.UUID(bytes=adjusted_bytes))

        whitelist_path = Path(self.server_dir) / "whitelist.json"
        try:
            nicks = await self.repo.get_all_linked_nicknames()
            whitelist_data = [
                {"uuid": get_offline_uuid(nick), "name": nick}
                for nick in nicks
            ]
            
            def _write():
                whitelist_path.write_text(json.dumps(whitelist_data, indent=2), encoding="utf-8")
                
            await asyncio.to_thread(_write)
            logger.info("Whitelist persistente sincronizada fisicamente no whitelist.json (%d nicks).", len(nicks))
        except Exception as exc:
            logger.error("Erro ao sincronizar whitelist offline fisicamente: %s", exc)

    async def ensure_whitelist(self, nickname: str, add: bool = True) -> bool:
        """
        Adiciona ou remove um jogador da whitelist do servidor.
        Garante que o comando de reload da whitelist seja enviado.
        """
        action = "add" if add else "remove"
        success = await self.send_command(f"whitelist {action} {nickname}")
        if success:
            await self.send_command("whitelist reload")
        return success

    async def sync_all_whitelists(self) -> None:
        """
        Sincroniza a whitelist do servidor com todos os nicks vinculados no banco.
        Útil para quando o servidor acaba de ligar.

        #6 — Usa _sync_whitelist_file() para escrever o whitelist.json diretamente
        e envia apenas 1 comando RCON (whitelist reload), ao invés de N comandos
        individuais que travavam o RCON lock por ~10-25s em servidores grandes.
        """
        if not self.is_running():
            return

        logger.info("Iniciando sincronização de whitelist (via arquivo)...")
        await self._sync_whitelist_file()
        await self.send_command("whitelist reload")
        nicks = await self.repo.get_all_linked_nicknames()
        logger.info("Sincronização de whitelist concluída (%d nicks).", len(nicks))

    # ── Leitura de logs ────────────────────────────────────────────────────────

    async def _read_logs_loop(self) -> None:
        """
        Lê o stdout do servidor e emite eventos via EventBus.

        Delega o parsing de cada linha ao MinecraftLogParser.
        """
        if not self.process or not self.process.stdout:
            return

        try:
            while True:
                try:
                    line_bytes = await asyncio.wait_for(
                        self.process.stdout.readline(),
                        timeout=_LOGS_READLINE_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.warning("Timeout ao ler logs do servidor (sem output há 30s)")
                    continue

                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace")

                # Cede controle para não travar o event loop
                await asyncio.sleep(0)

                event = self._parser.parse(line)
                if event is None:
                    continue

                kind = event.kind
                data = event.data

                if kind == "tps":
                    self.current_tps = data["tps_1m"]

                elif kind == "chat":
                    await self._emit(BotEvent.MINECRAFT_CHAT, data)

                elif kind == "player_command":
                    await self._emit(BotEvent.MINECRAFT_PLAYER_COMMAND, data)

                elif kind == "login":
                    # Verifica VPN/Proxy (#5 — task com referência para evitar GC prematuro)
                    ip = data.get("ip")
                    user = data.get("user")
                    if ip and user:
                        async def _check_vpn_with_sem():
                            async with self._background_task_sem:
                                await self._check_vpn(user, ip)
                        task = asyncio.create_task(_check_vpn_with_sem())
                        self._background_tasks.add(task)
                        task.add_done_callback(self._background_tasks.discard)

                elif kind == "join":
                    await self._emit(BotEvent.MINECRAFT_JOIN, data)

                elif kind == "leave":
                    await self._emit(BotEvent.MINECRAFT_LEAVE, data)

                elif kind == "death":
                    await self._emit(BotEvent.MINECRAFT_DEATH, data)

                elif kind == "server_ready":
                    logger.info("Servidor Minecraft pronto para conexões.")
                    # Sincroniza a whitelist com os vínculos do banco (#5 — task com referência)
                    task = asyncio.create_task(self.sync_all_whitelists())
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

                elif kind == "error":
                    logger.warning("Log de erro do servidor MC: %s", data.get("line", ""))

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Erro no leitor de logs: %s", exc)
        finally:
            # Detecta crash
            if not self._is_stopping and self.process:
                ret = self.process.returncode
                if ret is not None and ret != 0:
                    logger.error("Servidor Minecraft encerrou com código %d (crash?).", ret)
                    await self._emit(
                        BotEvent.MINECRAFT_DEATH,
                        {"message": "O SERVIDOR SOFREU UM CRASH INESPERADO!"},
                    )
            self.process = None

    async def _emit(self, event: BotEvent, data: dict) -> None:
        """Emite evento apenas para guilds com canal MC ou MINECRAFT_ALLOWED_GUILDS."""
        target_guilds = await self.get_event_guild_ids()
        if not target_guilds:
            return
        for guild_id in target_guilds:
            await self.event_bus.emit(guild_id, event, data)

    # ── Status ─────────────────────────────────────────────────────────────────

    async def _get_mc_server(self) -> JavaServer:
        """Retorna uma instância de JavaServer otimizada para evitar lentidão de DNS SRV em IPs locais."""
        host = self.mc_host
        clean_host = host.strip()
        # Se for localhost, IP numérico simples ou faixa privada, usa o construtor direto
        is_simple = (
            clean_host == "localhost"
            or clean_host.replace(".", "").isdigit()
            or clean_host.startswith("127.")
            or clean_host.startswith("192.168.")
            or clean_host.startswith("10.")
        )
        if is_simple:
            return JavaServer(clean_host, self.mc_port, timeout=1.0)
        try:
            return await JavaServer.async_lookup(self.mc_address, timeout=1.0)
        except Exception:
            return JavaServer(clean_host, self.mc_port, timeout=1.0)

    async def get_status(self) -> Tuple[bool, int, int, str]:
        """Retorna (online, players, ping_ms, tps).

        #7 — O TPS já é capturado automaticamente pelo log parser via stdout do Paper
        (evento 'tps' em _read_logs_loop). Enviar o comando 'tps' via RCON a cada
        chamada era redundante e consumia o lock desnecessariamente.
        """
        if not self.is_running():
            return False, 0, 0, "0.0"

        try:
            server = await self._get_mc_server()
            status = await server.async_status()
            return True, status.players.online, int(status.latency), self.current_tps
        except Exception:
            return False, 0, 0, self.current_tps

    async def get_players(self) -> List[str]:
        """Retorna a lista de nomes de jogadores online."""
        if not self.is_running():
            return []
        try:
            server = await self._get_mc_server()
            status = await server.async_status()
            if status.players.sample:
                return [p.name for p in status.players.sample]
        except Exception:
            pass
        return []

    async def _check_vpn(self, username: str, ip: str) -> None:
        """Verifica VPN/Proxy com semáforo e retry em 429 (chamar via create_task)."""
        if ip in ("127.0.0.1", "0:0:0:0:0:0:0:1", "localhost"):
            return

        # Verifica cache em memória para evitar requisições de rede repetidas
        if ip in self._vpn_cache:
            is_vpn = self._vpn_cache[ip]
            if is_vpn:
                logger.warning(
                    "Bloqueando %s (IP: %s) - VPN/Proxy detectado (Cache).",
                    username,
                    ip,
                )
                await self.send_command(
                    f"kick {username} VPN/Proxy detectado. Por favor, use sua conexão real."
                )
            return

        async with self._vpn_sem:
            await self._check_vpn_with_retry(username, ip)

    async def _check_vpn_with_retry(self, username: str, ip: str) -> None:
        api_key = os.getenv("MINECRAFT_IP_API_KEY")
        if api_key:
            url = f"https://pro.ip-api.com/json/{ip}?key={api_key}&fields=proxy,hosting,status,message"
        else:
            url = f"http://ip-api.com/json/{ip}?fields=proxy,hosting,status,message"

        session = await self._ensure_http_session()
        for attempt in range(_VPN_MAX_RETRIES):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        if res.get("status") == "success":
                            is_vpn = bool(res.get("proxy") or res.get("hosting"))
                            self._vpn_cache[ip] = is_vpn
                            if is_vpn:
                                logger.warning(
                                    "Bloqueando %s (IP: %s) - VPN/Proxy/Hosting detectado.",
                                    username,
                                    ip,
                                )
                                await self.send_command(
                                    f"kick {username} VPN/Proxy detectado. Por favor, use sua conexão real."
                                )
                        return
                    if resp.status == 429:
                        delay = min(2.0 ** attempt, 30.0)
                        logger.warning(
                            "VPN check 429 para %s — retry %d/%d em %.1fs.",
                            ip,
                            attempt + 1,
                            _VPN_MAX_RETRIES,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.warning(
                        "Verificação de VPN para %s: HTTP %d.", ip, resp.status
                    )
                    return
            except Exception as exc:
                logger.error("Erro ao verificar VPN para %s: %s", ip, exc)
                return

    # ── Plugins ────────────────────────────────────────────────────────────────

    def _sync_list_plugins(self) -> List[str]:
        plugins_dir = os.path.join(self.server_dir, "plugins")
        if not os.path.exists(plugins_dir):
            return []
        return [f.replace(".jar", "") for f in os.listdir(plugins_dir) if f.endswith(".jar")]

    async def list_plugins(self) -> List[str]:
        return await asyncio.to_thread(self._sync_list_plugins)

    # ── Backup & Restore ───────────────────────────────────────────────────────

    _WORLD_FOLDERS = ("world", "world_nether", "world_the_end")

    @staticmethod
    def _zip_worlds(server_dir: str, zip_path: str) -> None:
        import zipfile
        with zipfile.ZipFile(zip_path, "w") as zf:
            for folder in MinecraftService._WORLD_FOLDERS:
                folder_path = os.path.join(server_dir, folder)
                if os.path.isdir(folder_path):
                    for root, _, files in os.walk(folder_path):
                        for file in files:
                            fp = os.path.join(root, file)
                            arcname = os.path.relpath(fp, server_dir)
                            # Evita recompactar arquivos de região (.mca, .mcr) que já são comprimidos internamente
                            if file.endswith((".mca", ".mcr")):
                                zf.write(fp, arcname, compress_type=zipfile.ZIP_STORED)
                            else:
                                zf.write(fp, arcname, compress_type=zipfile.ZIP_DEFLATED)

    async def create_backup(self) -> Optional[str]:
        """Cria um backup das três dimensões. Retorna o nome do arquivo ou None."""
        world_dir = os.path.join(self.server_dir, "world")
        if not os.path.exists(world_dir):
            return None

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_name = f"world_backup_{ts}"
        backup_path = os.path.join(str(BACKUP_DIR), backup_name)

        try:
            if self.is_running():
                await self.send_command("save-all")
                await asyncio.sleep(2)

            await asyncio.to_thread(self._zip_worlds, self.server_dir, f"{backup_path}.zip")

            # Retenção: mantém no máximo 5 backups
            backups = await self.list_backups()
            if len(backups) > 5:
                async def _do_retention() -> None:
                    for old in backups[5:]:
                        old_path = os.path.join(str(BACKUP_DIR), old)
                        if os.path.exists(old_path):
                            try:
                                os.remove(old_path)
                            except Exception:
                                pass
                await asyncio.to_thread(_do_retention)

            return f"{backup_name}.zip"
        except Exception as exc:
            logger.error("Falha ao criar backup: %s", exc)
            return None

    def _sync_list_backups(self) -> List[str]:
        if not BACKUP_DIR.exists():
            return []
        return sorted(
            [f for f in os.listdir(str(BACKUP_DIR)) if f.endswith(".zip")],
            reverse=True,
        )

    async def list_backups(self) -> List[str]:
        return await asyncio.to_thread(self._sync_list_backups)

    async def restore_backup(self, backup_name: str) -> bool:
        """Restaura um backup. O servidor DEVE estar desligado."""
        async with self._action_lock:
            if self.is_running():
                return False
            backup_path = os.path.join(str(BACKUP_DIR), backup_name)
            if not await asyncio.to_thread(os.path.exists, backup_path):
                return False
            try:
                for folder in self._WORLD_FOLDERS:
                    path = os.path.join(self.server_dir, folder)
                    if await asyncio.to_thread(os.path.exists, path):
                        await asyncio.to_thread(shutil.rmtree, path, True)
                await asyncio.to_thread(shutil.unpack_archive, backup_path, self.server_dir)
                return True
            except Exception as exc:
                logger.error("Falha ao restaurar backup: %s", exc)
                return False

    async def wipe_world(self) -> bool:
        """Faz backup emergencial e apaga as três dimensões."""
        async with self._action_lock:
            if self.is_running():
                return False
            if not await asyncio.to_thread(
                os.path.exists, os.path.join(self.server_dir, "world")
            ):
                return True  # já está limpo

            try:
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                backup_name = f"pre_wipe_{ts}"
                backup_path = os.path.join(str(BACKUP_DIR), backup_name)
                await asyncio.to_thread(self._zip_worlds, self.server_dir, f"{backup_path}.zip")
                logger.info("Backup pre-wipe concluído: %s", backup_name)

                for folder in self._WORLD_FOLDERS:
                    path = os.path.join(self.server_dir, folder)
                    await asyncio.to_thread(shutil.rmtree, path, ignore_errors=True)
                return True
            except Exception as exc:
                logger.error("Falha ao limpar o mundo: %s", exc)
                return False

    # ── Vínculo de Jogadores (API para o Cog) ──────────────────────────────────
    # #8 — O Cog não deve acessar o Repository diretamente.
    # Estes métodos expõem a lógica de vínculo pela camada de Service.

    async def link_player(self, guild_id: int, discord_id: int, nickname: str) -> None:
        """Vincula um Discord ID a um nickname do Minecraft."""
        await self.repo.link_player(guild_id, discord_id, nickname)

    async def unlink_player(self, guild_id: int, discord_id: int) -> Optional[str]:
        """Remove o vínculo e retorna o nickname anterior (ou None)."""
        return await self.repo.unlink_player(guild_id, discord_id)

    async def get_player_by_nickname(self, guild_id: int, nickname: str) -> Optional[int]:
        """Retorna o discord_id vinculado ao nickname (case-insensitive), ou None."""
        return await self.repo.get_player_by_nickname(guild_id, nickname)

    async def get_player_by_discord(self, guild_id: int, discord_id: int) -> Optional[str]:
        """Retorna o mc_nickname vinculado ao discord_id, ou None."""
        return await self.repo.get_player_by_discord(guild_id, discord_id)

    async def get_webhook_config(self, guild_id: int) -> tuple[Optional[str], Optional[int]]:
        """Retorna (webhook_url, webhook_channel_id) persistidos para o guild."""
        return await self.repo.get_webhook_config(guild_id)

    async def set_webhook_url(
        self,
        guild_id: int,
        url: Optional[str],
        channel_id: Optional[int] = None,
    ) -> None:
        """Persiste (ou limpa) o URL do webhook e o canal associado."""
        await self.repo.set_webhook_url(guild_id, url, channel_id)

    async def get_ram(self) -> int:
        """RAM configurada em MB para o servidor Java."""
        return await self.repo.get_ram()

    async def set_ram(self, ram_mb: int) -> None:
        """Persiste RAM em MB."""
        await self.repo.set_ram(ram_mb)
