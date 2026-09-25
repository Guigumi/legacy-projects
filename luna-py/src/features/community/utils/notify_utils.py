from __future__ import annotations

import re
from datetime import datetime, timedelta
import discord
from config.settings import BRT, BotEmojis, Separators, now_brt
from core.utils.embed_builder import EmbedBuilder

# Regex para durações rápidas: 30m, 1h, 2h30m, 1h30, 90m etc.
_DURATION_RE = re.compile(
    r"^(?:(\d+)\s*h(?:oras?)?)?[\s,]*(?:(\d+)\s*m(?:in(?:uto)?s?)?)?$",
    re.IGNORECASE,
)

def _parse_duration(text: str) -> timedelta | None:
    """Tenta interpretar texto como duração relativa (ex: '1h30m', '45m', '2h')."""
    text = text.strip()
    m = _DURATION_RE.match(text)
    if not m:
        return None
    hours = int(m.group(1)) if m.group(1) else 0
    minutes = int(m.group(2)) if m.group(2) else 0
    if hours == 0 and minutes == 0:
        return None
    return timedelta(hours=hours, minutes=minutes)

def _resolve_notify_datetime(
    date_input: str, time_input: str
) -> tuple[datetime | None, str | None]:
    """Resolve a data/hora informada no modal/command de notificação."""
    delta = _parse_duration(date_input)
    if delta is not None:
        return now_brt() + delta, None

    if not time_input:
        return None, (
            "Quando usar uma **data**, informe também a **hora** (HH:MM).\n"
            "Para notificação rápida, use duração: `1h`, `30m`, `2h30m`."
        )

    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", date_input.strip())
    if not m:
        return None, (
            "Formato inválido.\n"
            "• Data: **DD/MM** + Hora: **HH:MM** (Brasília)\n"
            "• Ou duração rápida: `30m`, `1h`, `2h30m`"
        )

    day = int(m.group(1))
    month = int(m.group(2))
    year = None
    if m.group(3):
        raw_year = m.group(3)
        year = int(raw_year) if len(raw_year) == 4 else 2000 + int(raw_year)

    try:
        hour, minute = map(int, time_input.split(":"))
    except Exception:
        return None, ("Hora inválida. Use **HH:MM** (Brasília).")

    now = now_brt()
    if year is None:
        year = now.year

    try:
        dt_local = datetime(year, month, day, hour, minute, tzinfo=BRT)
    except ValueError:
        return None, (
            "Data/hora inválida. Verifique se a data existe e está no formato **DD/MM** + **HH:MM**."
        )

    if dt_local <= now and (m.group(3) is None):
        try:
            dt_local = datetime(year + 1, month, day, hour, minute, tzinfo=BRT)
        except ValueError:
            return None, (
                "Data/hora inválida. Verifique se a data existe e está no formato **DD/MM** + **HH:MM**."
            )

    return dt_local, None

def _parse_scheduled_iso(iso: str) -> datetime:
    """Parse ISO do banco, retorna datetime aware no fuso de Brasília."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BRT)
    return dt

def _unix(dt: datetime) -> int:
    return int(dt.timestamp())

def _parse_optional_remind_minutes(text: str | None) -> int:
    raw = (text or "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0

async def _resolve_future_notify_datetime(
    interaction: discord.Interaction, date_input: str, time_input: str
) -> datetime | None:
    dt_brt, err = _resolve_notify_datetime(date_input, time_input)
    if err:
        await interaction.response.send_message(
            embed=EmbedBuilder.error_user(err).build(),
            ephemeral=True
        )
        return None

    if dt_brt <= now_brt():
        await interaction.response.send_message(
            embed=EmbedBuilder.error_user(
                "A data/hora deve ser no **futuro**."
            ).build(),
            ephemeral=True
        )
        return None

    return dt_brt

def _format_notification_time(dt: datetime) -> str:
    ts = _unix(dt)
    return f"<t:{ts}:F> (<t:{ts}:R>)"

def _format_remind_label(remind_before: int) -> str:
    return f"{remind_before} min antes" if remind_before > 0 else "Desligado"

def _build_notification_manage_embed(
    *,
    title: str,
    description: str | None,
    scheduled_at: datetime,
    remind_before: int,
    notif_id: int,
    user: discord.Member | discord.User,
) -> discord.Embed:
    return (
        EmbedBuilder.success(description or "Sem descrição.")
        .title(title)
        .author(user.display_name, user.display_avatar.url)
        .field(
            f"{BotEmojis.COMMON_WATCH} Lembrete",
            _format_remind_label(remind_before),
            inline=True,
        )
        .field("Data/Hora", _format_notification_time(scheduled_at), inline=True)
        .field(
            f"{BotEmojis.COMMON_NOTIFICATIONS} Notificação",
            f"`ID: #{notif_id}`",
            inline=False,
        )
        .footer("Você pode adicionar membros ou editar a notificação.")
        .build()
    )


def _build_notification_list_embed(notifs: list[dict]) -> discord.Embed:
    """Constrói embed com a lista de notificações do usuário."""
    lines: list[str] = []
    for n in notifs[:25]:
        try:
            dt = _parse_scheduled_iso(n["scheduled_at"])
            ts = _unix(dt)
            time_str = f"<t:{ts}:R>"
        except Exception:
            time_str = "?"
        lines.append(f"**#{n['id']}** — {n['title']} — {time_str}")

    return (
        EmbedBuilder.default()
        .author(name=f"{BotEmojis.COMMON_NOTIFICATIONS} Suas Notificações")
        .description("\n".join(lines))
        .footer("Selecione uma notificação abaixo para gerenciá-la.")
        .build()
    )


def _build_empty_notification_list_embed() -> discord.Embed:
    """Constrói embed para quando o usuário não tem notificações."""
    return (
        EmbedBuilder.default()
        .author(name=f"{BotEmojis.COMMON_NOTIFICATIONS} Nenhuma Notificação")
        .description(
            "Você não tem notificações agendadas.\n\n"
            "Use `/notify criar` para criar uma nova."
        )
        .build()
    )
