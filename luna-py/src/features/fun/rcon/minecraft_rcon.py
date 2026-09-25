"""
Implementação do protocolo RCON do Minecraft via asyncio puro.

O protocolo RCON usa TCP com pacotes de estrutura fixa:
    [4 bytes LE: length][4 bytes LE: request_id][4 bytes LE: type][payload\x00\x00]

Tipos de pacote:
    3 = Login (autenticação com senha)
    2 = Command (envio de comandos)
    0 = Response (resposta do servidor)

Respostas com request_id == -1 indicam falha de autenticação.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constantes do protocolo ────────────────────────────────────────────────────
_PACKET_TYPE_LOGIN = 3
_PACKET_TYPE_COMMAND = 2
_PACKET_TYPE_RESPONSE = 0

_MAX_PAYLOAD_SIZE = 1446  # limite seguro do protocolo RCON
_RECONNECT_DELAY = 5.0     # segundos entre tentativas de reconexão
_AUTH_TIMEOUT = 10.0       # timeout para autenticação inicial
_CMD_TIMEOUT = 10.0        # timeout por comando


def _pack_packet(request_id: int, packet_type: int, payload: str) -> bytes:
    """Serializa um pacote RCON para bytes."""
    body = payload.encode("utf-8") + b"\x00\x00"
    length = 4 + 4 + len(body)  # request_id + type + body
    return struct.pack("<iii", length, request_id, packet_type) + body


def _unpack_header(raw: bytes) -> tuple[int, int, int]:
    """Desserializa os 12 bytes do cabeçalho: (length, request_id, type)."""
    return struct.unpack("<iii", raw)


class RCONError(Exception):
    """Erro base do RCON."""


class RCONAuthError(RCONError):
    """Senha incorreta ou autenticação negada."""


class RCONNotConnectedError(RCONError):
    """Tentativa de uso com conexão fechada."""


class MinecraftRCON:
    """
    Cliente asyncio para o protocolo RCON do Minecraft.

    Uso:
        rcon = MinecraftRCON("127.0.0.1", 25575, "senha")
        await rcon.connect()
        response = await rcon.send_command("list")
        await rcon.close()

    Ou via context manager:
        async with MinecraftRCON("127.0.0.1", 25575, "senha") as rcon:
            response = await rcon.send_command("list")
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        cmd_timeout: float = _CMD_TIMEOUT,
        auth_timeout: float = _AUTH_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.cmd_timeout = cmd_timeout
        self.auth_timeout = auth_timeout

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()
        self._request_id = 1

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Abre a conexão TCP e autentica via RCON."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.auth_timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise RCONError(f"Falha ao conectar em {self.host}:{self.port}: {exc}") from exc

        await self._authenticate()
        logger.info("RCON conectado em %s:%s", self.host, self.port)

    async def close(self) -> None:
        """Fecha a conexão TCP de forma limpa."""
        if self._writer and not self._writer.is_closing():
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
        logger.debug("RCON desconectado.")

    async def __aenter__(self) -> "MinecraftRCON":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    # ── Interface pública ────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        """Verifica se a conexão está estabelecida e o writer não foi fechado."""
        return self._reader is not None and self._writer is not None and not self._writer.is_closing()

    async def send_command(self, command: str) -> str:
        """
        Envia um comando ao servidor e retorna a resposta em texto.

        Levanta RCONNotConnectedError se não estiver conectado.
        Retorna string vazia se o servidor não enviou output.
        """
        if not self.is_connected():
            raise RCONNotConnectedError("RCON não está conectado.")

        # Trunca payload enorme para não violar o protocolo
        if len(command.encode("utf-8")) > _MAX_PAYLOAD_SIZE:
            command = command.encode("utf-8")[:_MAX_PAYLOAD_SIZE].decode("utf-8", errors="ignore")
            logger.warning("Comando RCON truncado para %d bytes.", _MAX_PAYLOAD_SIZE)

        async with self._lock:
            req_id = self._next_id()
            packet = _pack_packet(req_id, _PACKET_TYPE_COMMAND, command)
            try:
                await asyncio.wait_for(
                    self._write_and_read(packet, req_id), timeout=self.cmd_timeout
                )
                return await asyncio.wait_for(
                    self._read_response(req_id), timeout=self.cmd_timeout
                )
            except asyncio.TimeoutError:
                logger.warning("RCON: timeout ao executar comando '%s'", command[:64])
                return ""
            except (OSError, EOFError) as exc:
                logger.error("RCON: erro de rede durante comando: %s", exc)
                await self.close()
                raise RCONError(f"Erro de rede durante comando: {exc}") from exc

    # ── Internos ─────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        """Incrementa e retorna o próximo request ID (1–2^31-1)."""
        self._request_id = (self._request_id % 2_147_483_647) + 1
        return self._request_id

    async def _authenticate(self) -> None:
        """Envia o pacote de login e verifica a resposta."""
        req_id = self._next_id()
        packet = _pack_packet(req_id, _PACKET_TYPE_LOGIN, self.password)
        assert self._writer is not None
        self._writer.write(packet)
        await self._writer.drain()

        try:
            resp_id, resp_type, _ = await asyncio.wait_for(
                self._recv_packet(), timeout=self.auth_timeout
            )
        except asyncio.TimeoutError as exc:
            raise RCONError("Timeout durante autenticação RCON.") from exc

        if resp_id == -1:
            raise RCONAuthError("Autenticação RCON falhou: senha incorreta.")
        logger.debug("RCON autenticado (request_id=%d, type=%d)", resp_id, resp_type)

    async def _write_and_read(self, packet: bytes, _req_id: int) -> None:
        """Escreve um pacote no socket."""
        assert self._writer is not None
        self._writer.write(packet)
        await self._writer.drain()

    async def _read_response(self, req_id: int) -> str:
        """
        Lê pacotes de resposta até encontrar o que corresponde ao req_id.

        O Minecraft pode fragmentar respostas longas em múltiplos pacotes;
        aqui acumulamos até receber o pacote com o ID correto.
        """
        parts: list[str] = []
        # Limite de iterações para não entrar em loop infinito se o servidor
        # enviar spam, mas suficientemente alto para comandos verbosos.
        for _ in range(128):
            resp_id, resp_type, payload = await self._recv_packet()
            if resp_type == _PACKET_TYPE_RESPONSE and resp_id == req_id:
                parts.append(payload)
                # Respostas RCON simples têm um único pacote.
                # Para simplificar, retornamos imediatamente após o primeiro match.
                return "".join(parts)
            # Pacote de outro contexto (pode ocorrer em ambientes concorrentes)
            logger.debug("RCON: ignorando pacote extra (id=%d, type=%d)", resp_id, resp_type)
        return "".join(parts)

    async def _recv_packet(self) -> tuple[int, int, str]:
        """
        Lê um único pacote RCON e retorna (request_id, type, payload).

        Formato do pacote:
            4 bytes LE: length (conta a partir do próximo campo)
            4 bytes LE: request_id
            4 bytes LE: type
            N bytes:    payload (UTF-8, terminado por \x00\x00)
        """
        assert self._reader is not None

        # Lê o campo 'length'
        raw_len = await self._reader.readexactly(4)
        (length,) = struct.unpack("<i", raw_len)

        if length < 10 or length > 4106:
            raise RCONError(f"Comprimento de pacote RCON inválido: {length}")

        # Lê o resto do pacote (request_id + type + payload)
        body = await self._reader.readexactly(length)
        req_id, pkt_type = struct.unpack("<ii", body[:8])

        # Payload: tudo depois dos 8 bytes de cabeçalho, menos os 2 bytes \x00\x00 finais
        payload_bytes = body[8:-2]
        payload = payload_bytes.decode("utf-8", errors="replace")
        return req_id, pkt_type, payload
