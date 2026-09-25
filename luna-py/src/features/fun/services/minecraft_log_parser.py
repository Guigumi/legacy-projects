"""
Parser de logs do servidor Minecraft.

Responsabilidade única: receber uma linha de texto do stdout do servidor
e retornar um evento estruturado (ParsedEvent) ou None se a linha não
for de interesse.

Completamente independente de asyncio, discord ou banco de dados —
pode ser testado com strings puras.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


# ── Regex compilados ───────────────────────────────────────────────────────────
# Suportam Paper, Vanilla e formatos com/sem ANSI, com/sem thread tag.

_RE_ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Mensagem de chat: <NomeJogador> mensagem
_RE_CHAT = re.compile(
    r"\[.*?INFO\]?:?(?:\s*\[Not Secure\])?\s*<([^>]+)>\s*(.+)$"
)

# Entrada no servidor
_RE_JOIN = re.compile(
    r"\[.*?INFO\]?:?(?:\s*\[Not Secure\])?\s*(\S+) joined the game$"
)

# Saída do servidor
_RE_LEAVE = re.compile(
    r"\[.*?INFO\]?:?(?:\s*\[Not Secure\])?\s*(\S+) left the game$"
)

# Login inicial (contém o IP)
# Ex: [15:24:00] [Server thread/INFO]: PlayerX[/127.0.0.1:54321] logged in with entity id
_RE_LOGIN = re.compile(
    r"\[.*?INFO\]?:?\s+(\S+)\[/([\d\.\:a-fA-F]+):\d+\] logged in with entity id"
)

# TPS da última 1m, 5m, 15m (Paper)
_RE_TPS = re.compile(
    r"\[.*?INFO\]?:? TPS from last 1m, 5m, 15m: ([\d.]+), ([\d.]+), ([\d.]+)"
)

# Servidor pronto para receber conexões
_RE_DONE = re.compile(
    r"\[.*?INFO\]?:? Done \("
)

# Conquistas / Advancements do jogador
_RE_ADVANCEMENT = re.compile(
    r"\[.*?INFO\]?:?\s+(\S+)\s+has\s+(made the advancement|completed the challenge|reached the goal)\s+\[(.+?)\]"
)

# Crash / exception grave
_RE_ERROR = re.compile(
    r"\[.*?(?:ERROR|FATAL)\]"
)

# Mortes — nick válido (3-16) + verbo de morte (evita nicks como "was", "hit", "killed")
_MC_NICK = r"[a-zA-Z0-9_]{3,16}"
_RE_DEATH = re.compile(
    rf"\[.*?INFO\]?:?\s+({_MC_NICK})\s+"
    r"(was\s+(?:slain|shot|buried|impaled|pricked|stung|frozen|burned|squashed|roasted|"
    r"doomed|killed|hit|pummeled|stabbed|fireballed|blown|struck)|"
    r"drowned|fell|burned|blew up|died|suffocated|withered away|starved|"
    r"hit the ground|went off|melted|froze|tried to swim|got|discovered|squished|"
    r"squashed|killed|withered|poisoned|crushed|experienced|went up|fell off|"
    r"walked into|was killed)"
    r".*$"
)

# Nicks que coincidem com palavras de morte — ignorados para evitar falsos positivos (#12)
_DEATH_FALSE_POSITIVE_NICKS = frozenset({
    "was", "killed", "hit", "died", "fell", "got", "tried", "went", "walked",
    "death", "burned", "drowned",
})

def format_death(msg: str, user: str) -> str:
    """Extrai os detalhes da morte em inglês direto do log, sem traduzir."""
    if msg.startswith(user + " "):
        details = msg[len(user) + 1:].strip()
    else:
        details = msg.strip()
    return f"morreu... ({details})" if details else "morreu..."


# ── Tipo de evento ─────────────────────────────────────────────────────────────

EventKind = Literal[
    "chat",
    "player_command",
    "join",
    "leave",
    "death",
    "tps",
    "server_ready",
    "error",
    "login",
]


@dataclass
class ParsedEvent:
    kind: EventKind
    data: dict[str, Any] = field(default_factory=dict)


# ── Parser ─────────────────────────────────────────────────────────────────────


class MinecraftLogParser:
    """
    Converte linhas de log do servidor Minecraft em ParsedEvent.

    Uso:
        parser = MinecraftLogParser()
        event = parser.parse(raw_line)
        if event and event.kind == "chat":
            print(event.data["user"], event.data["message"])
    """

    @staticmethod
    def clean(line: str) -> str:
        """Remove códigos ANSI e espaços extras de uma linha de log."""
        return _RE_ANSI.sub("", line).strip()

    def parse(self, raw_line: str) -> Optional[ParsedEvent]:
        """
        Analisa uma linha de log e retorna um ParsedEvent ou None.

        Ordem de prioridade (do mais específico ao mais genérico):
        1. TPS (só Paper)
        2. Chat / comando de jogador
        3. Join
        4. Leave
        5. Morte
        6. Servidor pronto
        7. Erro grave
        """
        line = self.clean(raw_line)
        if not line:
            return None

        # 1. TPS
        m = _RE_TPS.search(line)
        if m:
            return ParsedEvent(
                kind="tps",
                data={"tps_1m": m.group(1), "tps_5m": m.group(2), "tps_15m": m.group(3)},
            )

        # 2. Chat e comandos de jogador
        m = _RE_CHAT.search(line)
        if m:
            user, message = m.group(1), m.group(2).strip()
            if message.startswith("!"):
                parts = message[1:].strip().split()
                cmd = parts[0].lower() if parts else ""
                args = parts[1:] if len(parts) > 1 else []
                return ParsedEvent(
                    kind="player_command",
                    data={"user": user, "command": cmd, "args": args},
                )
            return ParsedEvent(kind="chat", data={"user": user, "message": message})

        # 3. Join
        m = _RE_JOIN.search(line)
        if m:
            return ParsedEvent(kind="join", data={"user": m.group(1)})

        # 4. Leave
        m = _RE_LEAVE.search(line)
        if m:
            return ParsedEvent(kind="leave", data={"user": m.group(1)})

        # 4.5 Login (IP check)
        m = _RE_LOGIN.search(line)
        if m:
            return ParsedEvent(kind="login", data={"user": m.group(1), "ip": m.group(2)})

        # 4.6 Conquistas / Advancements (repassados como chat estilizado)
        m = _RE_ADVANCEMENT.search(line)
        if m:
            user = m.group(1)
            action = m.group(2)
            adv = m.group(3)
            # Remove o namespace "minecraft:" e qualquer categoria anterior
            if adv.lower().startswith("minecraft:"):
                adv = adv[adv.find(":") + 1:].strip()
            if "/" in adv:
                adv = adv[adv.rfind("/") + 1:]
            
            # Substitui sublinhados por espaços apenas se houver sublinhados (ids técnicos)
            if "_" in adv:
                adv = adv.replace("_", " ").title()
            
            if action == "completed the challenge":
                msg = f"🏆 completou o desafio: **{adv}**"
            elif action == "reached the goal":
                msg = f"🎯 alcançou a meta: **{adv}**"
            else:
                msg = f"🏆 obteve uma conquista: **{adv}**"
                
            return ParsedEvent(
                kind="chat",
                data={
                    "user": user,
                    "message": msg,
                    "is_advancement": True,
                    "advancement_action": action,
                    "advancement_name": adv,
                }
            )

        # 5. Morte — nick válido + frase de morte reconhecida (#12)
        m = _RE_DEATH.search(line)
        if m:
            user = m.group(1)
            if user.lower() in _DEATH_FALSE_POSITIVE_NICKS:
                pass
            else:
                log_body = line.split(": ", 1)[-1] if ": " in line else line
                skip_phrases = (
                    "joined the game",
                    "left the game",
                    "logged in",
                    "has made the advancement",
                    "has completed the challenge",
                    "has reached the goal",
                )
                if not any(x in log_body for x in skip_phrases):
                    details = format_death(log_body, user)
                    msg = f"{user} {details}"
                    return ParsedEvent(kind="death", data={"user": user, "message": msg, "details": details})

        # 6. Servidor pronto
        if _RE_DONE.search(line):
            return ParsedEvent(kind="server_ready", data={})

        # 7. Erro grave
        if _RE_ERROR.search(line):
            return ParsedEvent(kind="error", data={"line": line})

        return None
