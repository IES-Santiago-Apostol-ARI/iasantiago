"""Tests de los targets de backup del Makefile (T04).

Usan `make -n` (dry-run): no ejecutan nada, solo muestran lo que ejecutarían.
"""

import os
import subprocess
import time
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


# ------- T12: copias sin cache/ y con caducidad -------

def test_backup_excluye_cache():
    r = make_n("backup-openwebui", "DATE=D")
    assert r.returncode == 0
    assert "--exclude=openwebui/data/cache" in r.stdout
    r = make_n("backup-tutor", "DATE=D")
    assert r.returncode == 0
    assert "--exclude=tutor/data/cache" in r.stdout


def test_prune_solo_copias_de_chats():
    r = make_n("backup-prune", "BACKUP_DIR=/x", "BACKUP_KEEP_DAYS=7")
    assert r.returncode == 0
    for s in (
        "find /x",
        "-mtime +7",
        "openwebui-*.tgz",
        "tutor-*.tgz",
        "-delete",
    ):
        assert s in r.stdout, f"falta {s!r} en la salida de `make -n backup-prune`"
    for s in ("topics-", "qdrant-", "state-"):
        assert s not in r.stdout, f"no debe tocar {s!r}"


def test_prune_14_dias_por_defecto():
    env = {k: v for k, v in os.environ.items() if k != "BACKUP_KEEP_DAYS"}
    r = subprocess.run(
        ["make", "-n", "-C", str(ROOT), "backup-prune"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0
    assert "-mtime +14" in r.stdout


def test_backup_ejecuta_prune_al_final():
    r = make_n("backup", "DATE=D")
    assert r.returncode == 0
    out = r.stdout
    assert "-mtime +14" in out
    assert out.index("-mtime +14") > out.rindex("tutor-D.tgz")


def _run_prune_recipe(tmp_path, keep_days):
    """Ejecuta de verdad la receta de backup-prune (sin sudo) en tmp_path."""
    r = make_n(
        "backup-prune",
        f"BACKUP_DIR={tmp_path}",
        f"BACKUP_KEEP_DAYS={keep_days}",
    )
    assert r.returncode == 0
    lines = [l for l in r.stdout.splitlines() if not l.startswith("make:")]
    cmd = "\n".join(lines).replace("sudo ", "")
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)


def _make_backup_files(tmp_path, old=True):
    """Crea 5 copias de prueba; si old=True les pone fecha de hace 30 días."""
    names = (
        "openwebui-a.tgz",
        "tutor-a.tgz",
        "topics-a.tgz",
        "qdrant-a.tgz",
        "openwebui-b.tgz",
    )
    for name in names:
        p = tmp_path / name
        p.write_text("x")
        if old:
            old_time = time.time() - 30 * 86400
            os.utime(p, (old_time, old_time))
    return names


def test_prune_borra_solo_lo_viejo(tmp_path):
    names = _make_backup_files(tmp_path, old=True)
    # openwebui-b.tgz es reciente: no debe borrarse
    (tmp_path / "openwebui-b.tgz").write_text("x")
    r = _run_prune_recipe(tmp_path, "14")
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "openwebui-a.tgz").exists()
    assert not (tmp_path / "tutor-a.tgz").exists()
    for name in ("topics-a.tgz", "qdrant-a.tgz", "openwebui-b.tgz"):
        assert (tmp_path / name).exists(), f"{name} no debía borrarse"


def test_prune_rechaza_dias_invalidos(tmp_path):
    names = _make_backup_files(tmp_path, old=True)
    r = _run_prune_recipe(tmp_path, "abc")
    assert r.returncode != 0
    for name in names:
        assert (tmp_path / name).exists(), f"{name} no debía tocarse"


def test_prune_sin_carpeta(tmp_path):
    r = make_n(
        "backup-prune",
        f"BACKUP_DIR={tmp_path / 'no-existe'}",
        "BACKUP_KEEP_DAYS=14",
    )
    assert r.returncode == 0
    lines = [l for l in r.stdout.splitlines() if not l.startswith("make:")]
    cmd = "\n".join(lines).replace("sudo ", "")
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
