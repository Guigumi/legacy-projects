from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from features.admin.repositories.automod_repository import AutoModRepository

# ── Regex ─────────────────────────────────────────────────────────────────────

INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/\S+",
    re.IGNORECASE,
)

URL_REGEX = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE,
)

# ── Constantes ────────────────────────────────────────────────────────────────

CAPS_MIN_LEN = 8          # tamanho mínimo para ativar o filtro de CAPS
CAPS_THRESHOLD = 0.70     # fração de letras maiúsculas para disparar
REPEAT_THRESHOLD = 0.60   # fração de caracteres iguais ao mais frequente
SPAM_WINDOW_SECS = 6      # janela de tempo para rate-limit de spam
SPAM_MAX_MSGS = 5         # máximo de mensagens na janela antes de agir


# ── Estrutura de resultado ────────────────────────────────────────────────────

@dataclass
class ViolationResult:
    violated: bool = False
    vtype: str | None = None      # invite_link | blocked_word | caps | repeat | link | mentions | spam
    detail: str | None = None     # palavra bloqueada ou detalhe extra


# ── Histórico de mensagens em memória (rate-limit) ────────────────────────────

# guild_id → user_id → deque de timestamps
_spam_history: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))


class AutoModService:
    """Lógica de negócio do AutoMod — análise de violações com múltiplos filtros."""

    def __init__(self, repo: AutoModRepository) -> None:
        self.repo = repo

    # ── Config ────────────────────────────────────────────────────────────────

    async def get_config(self, guild_id: int) -> dict | None:
        return await self.repo.get_config(guild_id)

    async def save_config(self, guild_id: int, data: dict) -> None:
        await self.repo.save_config(guild_id, data)

    def build_default_config(self, existing: dict | None) -> dict:
        """Retorna um config com todos os campos, usando os valores existentes como base."""
        base = existing or {}
        return {
            "invites_blocked": base.get("invites_blocked", 0),
            "blocked_words":   base.get("blocked_words", ""),
            "block_links":     base.get("block_links", 0),
            "max_mentions":    base.get("max_mentions", 5),
            "log_channel_id":  base.get("log_channel_id"),
            "ignored_channels": base.get("ignored_channels", ""),
            "ignored_roles":   base.get("ignored_roles", ""),
            "punishment":      base.get("punishment", "warn_delete"),
            "target_group":    base.get("target_group", "all"),
            "preset":          base.get("preset", "alto"),
            "max_warnings":    base.get("max_warnings", 3),
        }

    # ── Helpers de lista ──────────────────────────────────────────────────────

    @staticmethod
    def _ids_from_str(raw: str) -> list[int]:
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]

    @staticmethod
    def _ids_to_str(ids: list[int]) -> str:
        return ",".join(str(i) for i in ids)

    def toggle_id(self, raw: str, target_id: int) -> str:
        """Adiciona ou remove um ID de uma lista armazenada como string CSV."""
        ids = self._ids_from_str(raw)
        if target_id in ids:
            ids.remove(target_id)
        else:
            ids.append(target_id)
        return self._ids_to_str(ids)

    def is_ignored_channel(self, config: dict, channel_id: int) -> bool:
        return channel_id in self._ids_from_str(config.get("ignored_channels", ""))

    def is_ignored_role(self, config: dict, member_roles: list[int]) -> bool:
        ignored = set(self._ids_from_str(config.get("ignored_roles", "")))
        return bool(ignored & set(member_roles))

    # ── Análise de mensagem ────────────────────────────────────────────────────

    async def analyze_message(
        self,
        guild_id: int,
        user_id: int,
        content: str,
        mention_count: int,
        is_recent_member: bool = False,
    ) -> ViolationResult:
        """Analisa a mensagem e retorna a primeira violação encontrada (ou nenhuma)."""
        config = await self.repo.get_config(guild_id)
        if not config:
            return ViolationResult()

        preset = config.get("preset", "alto")

        def filter_enabled(filter_name: str) -> bool:
            if filter_name == "invite_link":
                return config.get("invites_blocked") == 1
            if filter_name == "blocked_word":
                return bool(config.get("blocked_words"))

            if preset == "alto":
                if filter_name == "link":
                    return config.get("block_links") == 1
                return True

            if preset == "medio":
                # Apenas os que menos atrapalham membros comuns
                return filter_name in ("invite_link", "mentions", "blocked_word", "spam")

            if preset == "baixo":
                if is_recent_member:
                    # Ativa tudo para membros novos
                    if filter_name == "link":
                        return config.get("block_links") == 1
                    return True
                else:
                    # Deixa os mais tranquilos para membros antigos
                    return filter_name in ("invite_link", "mentions", "blocked_word", "spam")

            # custom
            if filter_name == "link":
                return config.get("block_links") == 1
            return True

        # 1. Convites do Discord
        if filter_enabled("invite_link") and INVITE_REGEX.search(content):
            return ViolationResult(True, "invite_link")

        # 2. Links externos (exceto convites já capturados acima)
        if filter_enabled("link"):
            # remove trechos de convite já checados e verifica se ainda há URLs
            sanitized = INVITE_REGEX.sub("", content)
            if URL_REGEX.search(sanitized):
                return ViolationResult(True, "link")

        # 3. Palavras bloqueadas
        if filter_enabled("blocked_word"):
            blocked_words_str = config.get("blocked_words", "")
            if blocked_words_str:
                content_lower = content.lower()
                for word in (w.strip().lower() for w in blocked_words_str.split(",") if w.strip()):
                    if word in content_lower:
                        return ViolationResult(True, "blocked_word", word)

        # 4. Flood de menções
        if filter_enabled("mentions"):
            max_mentions = int(config.get("max_mentions") or 5)
            if mention_count > max_mentions:
                return ViolationResult(True, "mentions", str(mention_count))

        # 5. CAPS excessivo
        if filter_enabled("caps"):
            letters = [c for c in content if c.isalpha()]
            if len(letters) >= CAPS_MIN_LEN:
                caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
                if caps_ratio >= CAPS_THRESHOLD:
                    return ViolationResult(True, "caps")

        # 6. Flood de caracteres repetidos
        if filter_enabled("repeat"):
            if len(content) >= CAPS_MIN_LEN:
                most_common_count = max(content.count(c) for c in set(content))
                if most_common_count / len(content) >= REPEAT_THRESHOLD:
                    return ViolationResult(True, "repeat")

        # 7. Spam de mensagens (rate-limit em memória)
        if filter_enabled("spam"):
            now = time.monotonic()
            history = _spam_history[guild_id][user_id]
            # remove timestamps fora da janela
            while history and now - history[0] > SPAM_WINDOW_SECS:
                history.popleft()
            history.append(now)
            if len(history) > SPAM_MAX_MSGS:
                return ViolationResult(True, "spam")

        return ViolationResult()
