"""Tests de tutor.report.collect_week."""

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tutor.report import collect_week
from tutor.tests.fixtures import make_webui_db

MADRID = ZoneInfo("Europe/Madrid")
START = datetime(2026, 11, 16, tzinfo=MADRID)
END = START + timedelta(days=7)


def ts(*args):
    """Timestamp Unix de un datetime en hora de Madrid."""
    return datetime(*args, tzinfo=MADRID).timestamp()


def user(uid, name, email, role="user"):
    return {"id": uid, "name": name, "email": email, "role": role}


def chat(cid, uid, title, models, messages, **extra):
    return {"id": cid, "user_id": uid, "title": title, "models": models,
            "messages": messages, **extra}


ALUMNO = user("u1", "Ana", "ana@edu.es")
ADMIN = user("a1", "Root", "root@edu.es", role="admin")
TUTOR = ("tutor-ari",)


def test_cuenta_sesiones_dias_y_mensajes(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO], [
        chat("c1", "u1", "Chat 1", TUTOR, [
            ("user", ts(2026, 11, 16, 10, 0)),
            ("assistant", ts(2026, 11, 16, 10, 1)),
            ("user", ts(2026, 11, 16, 11, 0)),
            ("user", ts(2026, 11, 16, 12, 0)),
        ]),
        chat("c2", "u1", "Chat 2", TUTOR, [
            ("user", ts(2026, 11, 18, 9, 0)),
            ("assistant", ts(2026, 11, 18, 9, 1)),
        ]),
    ])
    result = collect_week(db, START, END)
    assert len(result) == 1
    s = result[0]
    assert s.email == "ana@edu.es"
    assert s.sessions == 2
    assert s.days_active == 2
    assert s.user_messages == 4


def test_mensajes_fuera_de_la_semana_no_cuentan(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO], [
        chat("c1", "u1", "Chat 1", TUTOR, [
            ("user", START.timestamp() - 1),
            ("user", END.timestamp()),
        ]),
    ])
    result = collect_week(db, START, END)
    assert result[0].sessions == 0
    assert result[0].days_active == 0
    assert result[0].user_messages == 0


def test_dias_en_hora_local(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO], [
        chat("c1", "u1", "Chat 1", TUTOR, [
            ("user", ts(2026, 11, 16, 23, 30)),
            ("user", ts(2026, 11, 17, 0, 30)),
        ]),
    ])
    result = collect_week(db, START, END)
    assert result[0].days_active == 2


def test_filtra_por_modelo(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO], [
        chat("c1", "u1", "Otro modelo", ("programacion",), [
            ("user", ts(2026, 11, 16, 10, 0)),
        ]),
    ])
    default = collect_week(db, START, END)
    assert default[0].sessions == 0
    assert default[0].user_messages == 0
    all_models = collect_week(db, START, END, model_ids=None)
    assert all_models[0].sessions == 1
    assert all_models[0].user_messages == 1


def test_lista_alumnos_sin_actividad_y_excluye_admin(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO, ADMIN], [
        chat("c1", "a1", "Chat del admin", TUTOR, [
            ("user", ts(2026, 11, 16, 10, 0)),
        ]),
    ])
    result = collect_week(db, START, END)
    emails = [s.email for s in result]
    assert "root@edu.es" not in emails
    assert emails == ["ana@edu.es"]
    assert result[0].sessions == 0
    assert result[0].user_messages == 0
    assert result[0].longest == ()


def test_tres_chats_mas_largos_con_enlace(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO], [
        chat("c5", "u1", "Cinco", TUTOR,
             [("user", ts(2026, 11, 16, 10, 0) + i) for i in range(5)]),
        chat("c2", "u1", "Dos", TUTOR,
             [("user", ts(2026, 11, 16, 11, 0) + i) for i in range(2)]),
        chat("c7", "u1", "Siete", TUTOR,
             [("user", ts(2026, 11, 16, 12, 0) + i) for i in range(7)]),
        chat("c9", "u1", "Dos bis", TUTOR,
             [("user", ts(2026, 11, 16, 13, 0) + i) for i in range(2)]),
    ])
    result = collect_week(db, START, END)
    longest = result[0].longest
    assert len(longest) == 3
    assert [c.user_messages for c in longest] == [7, 5, 2]
    assert [c.chat_id for c in longest] == ["c7", "c5", "c2"]
    assert longest[0].url == "https://ia.santiagoapostol.net/c/c7"
    custom = collect_week(db, START, END, base_url="https://otro.example")
    assert custom[0].longest[0].url == "https://otro.example/c/c7"


def test_json_roto_se_ignora(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO], [
        {"id": "c1", "user_id": "u1", "title": "Roto", "raw_json": "{no es json"},
    ])
    result = collect_week(db, START, END)
    assert result[0].sessions == 0
    assert result[0].user_messages == 0


def test_usa_lista_messages_si_no_hay_history(tmp_path):
    raw = json.dumps(
        {
            "models": ["tutor-ari"],
            "messages": [
                {"id": "m1", "role": "user", "content": "x",
                 "timestamp": ts(2026, 11, 16, 10, 0)},
                {"id": "m2", "role": "assistant", "content": "x",
                 "timestamp": ts(2026, 11, 16, 10, 1)},
                {"id": "m3", "role": "user", "content": "x",
                 "timestamp": ts(2026, 11, 16, 11, 0)},
            ],
        }
    )
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO], [
        {"id": "c1", "user_id": "u1", "title": "Plano", "raw_json": raw},
    ])
    result = collect_week(db, START, END)
    assert result[0].sessions == 1
    assert result[0].user_messages == 2


def test_errores_de_entrada(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO], [])
    with pytest.raises(ValueError):
        collect_week(db, datetime(2026, 11, 16), END)
    with pytest.raises(ValueError):
        collect_week(db, START, datetime(2026, 11, 23))
    with pytest.raises(FileNotFoundError):
        collect_week(tmp_path / "noexiste.db", START, END)


def test_no_modifica_la_bd(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ALUMNO], [
        chat("c1", "u1", "Chat 1", TUTOR, [("user", ts(2026, 11, 16, 10, 0))]),
    ])
    before_mtime = os.stat(db).st_mtime_ns
    before_bytes = db.read_bytes()
    collect_week(db, START, END)
    assert os.stat(db).st_mtime_ns == before_mtime
    assert db.read_bytes() == before_bytes


def test_orden_por_email(tmp_path):
    zoe = user("u2", "Zoe", "zoe@edu.es")
    bob = user("u3", "Bob", "bob@edu.es")
    db = make_webui_db(tmp_path / "webui.db", [zoe, ALUMNO, bob], [])
    result = collect_week(db, START, END)
    assert [s.email for s in result] == ["ana@edu.es", "bob@edu.es", "zoe@edu.es"]
