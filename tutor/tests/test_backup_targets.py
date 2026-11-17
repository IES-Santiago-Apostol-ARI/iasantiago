"""Tests de los targets de backup del Makefile (T04).

Usan `make -n` (dry-run): no ejecutan nada, solo muestran lo que ejecutarían.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def make_n(*args):
    return subprocess.run(
        ["make", "-n", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
    )


def test_backup_incluye_chats():
    r = make_n("backup", "DATE=D")
    assert r.returncode == 0
    out = r.stdout
    for s in (
        "openwebui/data",
        "tutor/data",
        "openwebui-D.tgz",
        "tutor-D.tgz",
        "topics-D.tgz",
        "qdrant-D.tgz",
        "state-D.tgz",
    ):
        assert s in out, f"falta {s!r} en la salida de `make -n backup`"


def test_backup_openwebui_para_y_rearranca():
    r = make_n("backup-openwebui", "DATE=D", "BACKUP_DIR=/mnt/nas/x")
    assert r.returncode == 0
    out = r.stdout
    assert "docker stop openwebui" in out
    assert "docker start openwebui" in out
    assert "/mnt/nas/x/openwebui-D.tgz" in out
    assert out.index("docker stop") < out.index("tar") < out.index("docker start")


def test_backup_tutor_usa_su_contenedor():
    r = make_n("backup-tutor", "DATE=D")
    assert r.returncode == 0
    assert "docker stop tutor-webui" in r.stdout
    assert "tutor-D.tgz" in r.stdout


def test_backup_dir_desde_el_entorno():
    env = {**os.environ, "BACKUP_DIR": "/desde/env"}
    r = subprocess.run(
        ["make", "-n", "-C", str(ROOT), "backup-topics", "DATE=D"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0
    assert "/desde/env/topics-D.tgz" in r.stdout


def test_backup_dir_por_defecto():
    env = {k: v for k, v in os.environ.items() if k != "BACKUP_DIR"}
    r = subprocess.run(
        ["make", "-n", "-C", str(ROOT), "backup-topics", "DATE=D"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0
    assert "/opt/iasantiago-rag/backups/topics-D.tgz" in r.stdout


def test_restore_no_restaura_chats_automaticamente():
    r = make_n("restore", "BACKUP=X")
    assert r.returncode == 0
    for line in r.stdout.splitlines():
        assert not (line.startswith("sudo tar") and "openwebui-X.tgz" in line)
    # ...pero sí debe explicar cómo restaurarlos a mano
    for s in ("openwebui-X.tgz", "tutor-X.tgz", "make tutor"):
        assert s in r.stdout, f"falta la ayuda {s!r} en `make -n restore`"


def test_macro_aborta_si_stop_falla():
    r = make_n("backup-openwebui", "DATE=D")
    assert r.returncode == 0
    assert "no se pudo parar openwebui" in r.stdout
    assert "no ha vuelto a arrancar" in r.stdout


def test_macro_es_shell_valido():
    r = make_n("backup-openwebui", "DATE=D")
    assert r.returncode == 0
    check = subprocess.run(
        ["bash", "-n"], input=r.stdout, text=True, capture_output=True
    )
    assert check.returncode == 0, check.stderr
