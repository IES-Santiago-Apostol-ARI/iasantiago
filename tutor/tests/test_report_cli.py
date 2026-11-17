"""Tests de la CLI del informe semanal (tutor.report: iso_week_bounds, render, main, make)."""

from __future__ import annotations

import csv
import io
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tutor.report import (
    collect_week,
    iso_week_bounds,
    main,
    render_csv,
    render_markdown,
)
from tutor.tests.fixtures import make_webui_db

ROOT = Path(__file__).resolve().parents[2]
MADRID = ZoneInfo("Europe/Madrid")
START = datetime(2026, 11, 16, tzinfo=MADRID)
END = datetime(2026, 11, 23, tzinfo=MADRID)
TUTOR = ("tutor-ari",)


def ts(*args):
    """Timestamp Unix de un datetime en hora de Madrid."""
    return datetime(*args, tzinfo=MADRID).timestamp()


def user(uid, name, email, role="user"):
    return {"id": uid, "name": name, "email": email, "role": role}


def chat(cid, uid, title, models, messages, **extra):
    return {"id": cid, "user_id": uid, "title": title, "models": models,
            "messages": messages, **extra}


ANA = user("u1", "Ana", "ana@edu.es")
LUCIA = user("u2", "Lucía", "lucia@edu.es")


def _db(tmp_path):
    """BD con Ana (2 chats tutor) y Lucía (sin actividad)."""
    return make_webui_db(tmp_path / "webui.db", [ANA, LUCIA], [
        chat("c1", "u1", "Título 1", TUTOR, [
            ("user", ts(2026, 11, 16, 10, 0)),
            ("user", ts(2026, 11, 16, 11, 0)),
        ]),
        chat("c2", "u1", "Título 2", TUTOR, [
            ("user", ts(2026, 11, 18, 9, 0)),
        ]),
    ])


def test_iso_week_bounds():
    assert iso_week_bounds("2026-W47") == (START, END)
    with pytest.raises(ValueError):
        iso_week_bounds("2026-47")
    with pytest.raises(ValueError):
        iso_week_bounds("2026-W99")


def test_markdown_cabecera_tabla_y_resumen(tmp_path):
    db = _db(tmp_path)
    weeks = collect_week(db, START, END)
    md = render_markdown(weeks, START, END)
    assert "# Uso del tutor — semana del 16/11/2026 al 22/11/2026" in md
    assert "| Alumno | Sesiones | Días activos | Mensajes | Conversaciones más largas |" in md
    assert "[Título 1](https://ia.santiagoapostol.net/c/c1)" in md
    assert "[Título 2](https://ia.santiagoapostol.net/c/c2)" in md
    assert "—" in md
    assert "Sin actividad: 1 de 2 alumnos." in md


def test_markdown_escapa_barras_y_titulo_vacio(tmp_path):
    db = make_webui_db(tmp_path / "webui.db", [ANA], [
        chat("c1", "u1", "a|b", TUTOR, [("user", ts(2026, 11, 16, 10, 0))]),
        chat("c2", "u1", "", TUTOR, [("user", ts(2026, 11, 17, 10, 0))]),
    ])
    weeks = collect_week(db, START, END)
    md = render_markdown(weeks, START, END)
    assert "a\\|b" in md
    assert "(sin título)" in md


def test_csv(tmp_path):
    db = _db(tmp_path)
    weeks = collect_week(db, START, END)
    out = render_csv(weeks)
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0] == ["email", "nombre", "sesiones", "dias_activos",
                       "mensajes", "chat1", "chat2", "chat3"]
    lucia = [r for r in rows if r[0] == "lucia@edu.es"][0]
    assert lucia[5:8] == ["", "", ""]


def test_main_md_a_fichero(tmp_path):
    db = _db(tmp_path)
    out = tmp_path / "informe.md"
    assert main(["--db", str(db), "--week", "2026-W47", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Uso del tutor")


def test_main_all_models(tmp_path, capsys):
    db = make_webui_db(tmp_path / "webui.db", [ANA], [
        chat("c1", "u1", "Otro", ("programacin",),
             [("user", ts(2026, 11, 16, 10, 0))]),
    ])
    assert main(["--db", str(db), "--week", "2026-W47", "--format", "csv"]) == 0
    rows = list(csv.reader(io.StringIO(capsys.readouterr().out)))
    assert rows[1][2] == "0"
    assert main(["--db", str(db), "--week", "2026-W47", "--format", "csv",
                 "--all-models"]) == 0
    rows = list(csv.reader(io.StringIO(capsys.readouterr().out)))
    assert rows[1][2] == "1"


def test_main_errores(tmp_path):
    assert main(["--db", str(tmp_path / "noexiste.db"), "--week", "2026-W47"]) == 2
    assert main(["--db", str(tmp_path / "noexiste.db"), "--week", "2026-W99"]) == 2


def test_make_tutor_report():
    proc = subprocess.run(
        ["make", "-n", "-C", str(ROOT), "tutor-report", "WEEK=2026-W47"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert "python3 -m tutor.report --db tutor/data/webui.db --week 2026-W47" in proc.stdout
