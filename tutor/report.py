"""Núcleo del informe semanal por alumno sobre la BD de Open WebUI (solo lectura)."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

DEFAULT_MODEL = "tutor-ari"
DEFAULT_BASE_URL = "https://ia.santiagoapostol.net"
DEFAULT_TZ = "Europe/Madrid"


@dataclass(frozen=True)
class ChatSummary:
    chat_id: str
    title: str
    user_messages: int   # mensajes role=="user" del chat DENTRO del intervalo
    url: str             # f"{base_url}/c/{chat_id}"


@dataclass(frozen=True)
class StudentWeek:
    email: str
    name: str
    sessions: int        # nº de chats con >=1 mensaje de usuario en el intervalo
    days_active: int     # nº de fechas locales (tz) distintas con mensajes de usuario
    user_messages: int   # total de mensajes de usuario en el intervalo
    longest: tuple[ChatSummary, ...]  # máx. 3, orden: user_messages desc, luego chat_id asc


def _parse_chat(chat_json: str) -> tuple[list, object | None]:
    """Devuelve (mensajes, models) de la columna ``chat``; ([], None) si es inválida."""
    try:
        data = json.loads(chat_json)
    except (TypeError, ValueError):
        return [], None
    if not isinstance(data, dict):
        return [], None
    messages: list = []
    history = data.get("history")
    if isinstance(history, dict):
        history_messages = history.get("messages")
        if isinstance(history_messages, dict):
            messages = list(history_messages.values())
        elif isinstance(history_messages, list):
            messages = list(history_messages)
    if not messages:
        flat = data.get("messages")
        if isinstance(flat, list):
            messages = list(flat)
    return messages, data.get("models")


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def collect_week(
    db_path: str | Path,
    start: datetime,
    end: datetime,
    model_ids: Iterable[str] | None = (DEFAULT_MODEL,),
    base_url: str = DEFAULT_BASE_URL,
    tz: str = DEFAULT_TZ,
) -> list[StudentWeek]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start y end deben ser datetimes con zona horaria")

    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el fichero de la BD: {path}")

    if model_ids is None:
        allowed_models: set | None = None
    else:
        allowed_models = set(model_ids)
        if not allowed_models:
            allowed_models = None

    tzinfo = ZoneInfo(tz)
    start_ts = start.timestamp()
    end_ts = end.timestamp()

    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        students = cur.execute(
            "SELECT id, email, name FROM user WHERE role = 'user'"
        ).fetchall()
        chats = cur.execute(
            "SELECT id, user_id, title, chat FROM chat"
        ).fetchall()
    finally:
        conn.close()

    # user_id -> info de acumulación del alumno
    by_user_id: dict[str, dict] = {}
    for user_id, email, name in students:
        by_user_id[user_id] = {
            "email": email,
            "name": name,
            "sessions": 0,
            "days": set(),
            "messages": 0,
            "chats": [],  # (user_messages, chat_id, title)
        }

    for chat_id, user_id, title, chat_json in chats:
        messages, models = _parse_chat(chat_json)
        if allowed_models is not None:
            if not isinstance(models, list) or not any(
                m in allowed_models for m in models
            ):
                continue

        info = by_user_id.get(user_id)
        if info is None:
            continue  # chat de admin/pending o usuario ausente

        user_msgs_in_range = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "user":
                continue
            timestamp = msg.get("timestamp")
            if not _is_numeric(timestamp):
                continue
            if start_ts <= timestamp < end_ts:
                user_msgs_in_range.append(timestamp)

        if not user_msgs_in_range:
            continue

        info["sessions"] += 1
        info["messages"] += len(user_msgs_in_range)
        info["days"].update(
            datetime.fromtimestamp(ts, tz=tzinfo).date() for ts in user_msgs_in_range
        )
        info["chats"].append((len(user_msgs_in_range), chat_id, title))

    result: list[StudentWeek] = []
    # Una fila por user_id (dos alumnos con el mismo email -> dos filas);
    # orden por (email o '', user_id) para que email NULL no rompa el orden.
    for user_id, info in sorted(
        by_user_id.items(), key=lambda kv: ((kv[1]["email"] or ""), kv[0])
    ):
        email = info["email"] or ""
        # orden: user_messages desc, luego chat_id asc; máximo 3
        longest = sorted(info["chats"], key=lambda c: (-c[0], c[1]))[:3]
        result.append(
            StudentWeek(
                email=email,
                name=info["name"],
                sessions=info["sessions"],
                days_active=len(info["days"]),
                user_messages=info["messages"],
                longest=tuple(
                    ChatSummary(
                        chat_id=chat_id,
                        title=title,
                        user_messages=count,
                        url=f"{base_url}/c/{chat_id}",
                    )
                    for count, chat_id, title in longest
                ),
            )
        )
    return result


_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def iso_week_bounds(week: str, tz: str = DEFAULT_TZ) -> tuple[datetime, datetime]:
    """'2026-W47' -> (lunes 00:00, lunes siguiente 00:00) en tz. Formato inválido -> ValueError."""
    m = _WEEK_RE.match(week)
    if not m:
        raise ValueError(f"Semana ISO inválida: {week!r} (esperaba AAAA-Wnn)")
    year, week_num = int(m.group(1)), int(m.group(2))
    tzinfo = ZoneInfo(tz)
    try:
        start = datetime.fromisocalendar(year, week_num, 1).replace(tzinfo=tzinfo)
    except ValueError as exc:
        raise ValueError(f"Semana ISO inválida: {week!r}") from exc
    return start, start + timedelta(days=7)


def _link(summary: ChatSummary) -> str:
    title = summary.title or "(sin título)"
    return f"[{title.replace('|', chr(92) + '|')}]({summary.url})"


def render_markdown(weeks: list[StudentWeek], start: datetime, end: datetime) -> str:
    lines = [
        f"# Uso del tutor — semana del {start:%d/%m/%Y} al {end - timedelta(days=1):%d/%m/%Y}",
        "",
        "| Alumno | Sesiones | Días activos | Mensajes | Conversaciones más largas |",
        "|---|---|---|---|---|",
    ]
    for w in weeks:
        longest = "<br>".join(_link(s) for s in w.longest) or "—"
        lines.append(
            f"| {w.name} ({w.email}) | {w.sessions} | {w.days_active} "
            f"| {w.user_messages} | {longest} |"
        )
    sin_actividad = sum(1 for w in weeks if w.sessions == 0)
    lines += ["", f"Sin actividad: {sin_actividad} de {len(weeks)} alumnos."]
    return "\n".join(lines) + "\n"


def render_csv(weeks: list[StudentWeek]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["email", "nombre", "sesiones", "dias_activos", "mensajes",
         "chat1", "chat2", "chat3"]
    )
    for w in weeks:
        urls = [s.url for s in w.longest] + [""] * 3
        writer.writerow(
            [w.email, w.name, w.sessions, w.days_active, w.user_messages,
             *urls[:3]]
        )
    return buf.getvalue()


def _previous_iso_week(tz: str) -> str:
    now = datetime.now(ZoneInfo(tz))
    iso_now = now.isocalendar()
    monday = datetime.fromisocalendar(iso_now.year, iso_now.week, 1).replace(
        tzinfo=ZoneInfo(tz)
    )
    prev = monday - timedelta(days=7)
    iso = prev.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tutor.report",
        description="Informe semanal de uso del tutor (solo lectura).",
    )
    parser.add_argument("--db", required=True, help="ruta a webui.db")
    parser.add_argument(
        "--week", default=None,
        help="semana ISO (p. ej. 2026-W47); por defecto la anterior a la actual",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"modelo a contar (por defecto {DEFAULT_MODEL})")
    parser.add_argument("--all-models", action="store_true",
                        help="no filtrar por modelo")
    parser.add_argument("--format", choices=("md", "csv"), default="md")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--out", default=None, help="fichero de salida (UTF-8)")
    args = parser.parse_args(argv)

    try:
        week = args.week or _previous_iso_week(DEFAULT_TZ)
        start, end = iso_week_bounds(week)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    model_ids = None if args.all_models else (args.model,)
    try:
        weeks = collect_week(
            args.db, start, end,
            model_ids=model_ids, base_url=args.base_url,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    text = render_markdown(weeks, start, end) if args.format == "md" else render_csv(weeks)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
