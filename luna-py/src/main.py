"""
Luna Bot — ponto de entrada atualizado.
Carrega variáveis de ambiente e inicia o bot com auto-reconnect resiliente.
"""

import asyncio
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path

# Adicionar src ao path
ROOT = Path(__file__).parent.parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from core.bot import LunaBot  # noqa: E402
from core.di import DependencyContainer  # noqa: E402

RECONNECT_BASE_DELAY = 5
RECONNECT_MAX_DELAY = 300
RECONNECT_BACKOFF_FACTOR = 2

import json

class StructuredJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        standard_attrs = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
            'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
            'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
            'processName', 'process', 'message', 'asctime'
        }
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}
        if extra:
            log_data["extra"] = extra
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)

class ContextualConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        standard_attrs = {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
            'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
            'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
            'processName', 'process', 'message', 'asctime'
        }
        message = super().format(record)
        extra = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}
        if extra:
            extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
            message = f"{message} │ {extra_str}"
        return message

def setup_logging() -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ContextualConsoleFormatter(
        fmt="%(asctime)s │ %(levelname)-4s │ %(message)s",
        datefmt="%m-%d %H:%M"
    ))
    
    file_handler = logging.FileHandler(ROOT / "data" / "luna.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StructuredJSONFormatter(
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    logger = logging.getLogger("luna.launcher")
    logger.info("Logs configurados: arquivo (JSON/DEBUG) e console (legível/INFO).")
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

logger = logging.getLogger("luna.launcher")

def _check_connectivity() -> bool:
    targets = [
        ("discord.com", 443),
        ("gateway.discord.gg", 443),
        ("1.1.1.1", 53),
    ]
    for host, port in targets:
        try:
            conn = socket.create_connection((host, port), timeout=5)
            conn.close()
            return True
        except OSError:
            continue
    return False

async def _wait_for_internet() -> None:
    delay = 5
    loop = asyncio.get_running_loop()
    while True:
        connected = await loop.run_in_executor(None, _check_connectivity)
        if connected:
            logger.info(" Conexão com a internet detectada.")
            return
        logger.warning("Sem internet — tentando novamente em %ds...", delay)
        await asyncio.sleep(delay)
        delay = min(delay + 5, 60)

async def run_bot_forever(token: str) -> None:
    delay = RECONNECT_BASE_DELAY
    consecutive_failures = 0

    while True:
        # Injeção de Dependências global
        di_container = DependencyContainer()
        bot = LunaBot(container=di_container)
        started_at = time.monotonic()

        try:
            logger.info(" Iniciando Luna Bot...")
            await _wait_for_internet()

            async with bot:
                await bot.start(token)

        except SystemExit:
            logger.info(" SystemExit recebido — encerrando.")
            break
        except Exception as exc:
            uptime = time.monotonic() - started_at
            consecutive_failures += 1

            if uptime > 60:
                delay = RECONNECT_BASE_DELAY
                consecutive_failures = 1

            logger.error(
                " Bot desconectou após %.0fs (tentativa #%d): %s: %s",
                uptime,
                consecutive_failures,
                type(exc).__name__,
                exc,
            )
            logger.exception("Detalhes do erro:")

        finally:
            try:
                if not bot.is_closed():
                    await bot.close()
            except Exception:
                pass
            await di_container.close()

        logger.warning(
            " Reconectando em %ds (backoff #%d)...",
            delay,
            consecutive_failures,
        )
        await asyncio.sleep(delay)
        delay = min(
            int(delay * RECONNECT_BACKOFF_FACTOR),
            RECONNECT_MAX_DELAY,
        )

    logger.info(" Luna Bot encerrado.")

def _handle_signal(signum: int, _frame: object) -> None:
    sig_name = signal.Signals(signum).name
    logger.info(" Sinal recebido: %s — encerrando...", sig_name)
    raise SystemExit(0)

def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN não encontrado. Configure o arquivo .env")
        sys.exit(1)

    (ROOT / "data").mkdir(exist_ok=True)
    setup_logging()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_signal)

    try:
        asyncio.run(run_bot_forever(token))
    except (KeyboardInterrupt, SystemExit):
        logger.info(" Bye!")

if __name__ == "__main__":
    main()
