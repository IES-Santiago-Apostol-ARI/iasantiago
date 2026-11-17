"""Fixture para crear una BD SQLite con el esquema de Open WebUI (solo lectura en tests)."""

import json
import sqlite3
from pathlib import Path


def make_webui_db(path, users: list[dict], chats: list[dict]) -> Path:
    """Crea las tablas ``user`` y ``chat`` e inserta las filas dadas.

    Cada ``user`` es un dict con claves ``id, name, email, role``.
    Cada ``chat`` es un dict con ``id, user_id, title, models, messages`` donde
    ``messages`` es una lista de tuplas ``(role, timestamp)``. La fixture construye
    el JSON de la columna ``chat`` con ``history.messages`` (ids ``m0``, ``m1``, …,
    ``content`` = ``"x"``) y también la lista plana ``messages``.

    Si el dict del chat incluye la clave opcional ``raw_json``, su valor se inserta
    tal cual en la columna ``chat`` (útil para probar JSON roto o variantes).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE user (id TEXT PRIMARY KEY, name TEXT, email TEXT, role TEXT)"
        )
        cur.execute(
            "CREATE TABLE chat (id TEXT PRIMARY KEY, user_id TEXT, title TEXT, "
            "chat TEXT, created_at INTEGER, updated_at INTEGER, "
            "archived INTEGER DEFAULT 0)"
        )
        for u in users:
            cur.execute(
                "INSERT INTO user VALUES (?, ?, ?, ?)",
                (u["id"], u["name"], u["email"], u["role"]),
            )
        for c in chats:
            if "raw_json" in c:
                chat_json = c["raw_json"]
            else:
                history_messages = {}
                flat = []
                for i, (role, ts) in enumerate(c.get("messages", [])):
                    mid = f"m{i}"
                    msg = {"id": mid, "role": role, "content": "x", "timestamp": ts}
                    history_messages[mid] = msg
                    flat.append(msg)
                chat_json = json.dumps(
                    {
                        "models": c.get("models", []),
                        "history": {"messages": history_messages},
                        "messages": flat,
                    }
                )
            cur.execute(
                "INSERT INTO chat VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    c["id"],
                    c["user_id"],
                    c["title"],
                    chat_json,
                    c.get("created_at", 0),
                    c.get("updated_at", 0),
                    c.get("archived", 0),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return path
