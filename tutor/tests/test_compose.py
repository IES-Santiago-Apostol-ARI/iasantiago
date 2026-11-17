"""Tests de T03: add-on de compose del modo tutor y targets del Makefile."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

ENV_VARS = [
    "DOCLING_GPU_MEMORY_FRACTION",
    "INGESTOR_STATE_HOST_DIR",
    "OAUTH2_CLIENT_ID",
    "OAUTH2_CLIENT_SECRET",
    "OAUTH2_COOKIE_SECRET",
    "OAUTH2_EMAIL_DOMAINS",
    "OAUTH2_REDIRECT_URL",
    "OPENAI_API_KEY",
    "PYTORCH_CUDA_ALLOC_CONF",
    "QDRANT_STORAGE",
    "TOPICS_HOST_DIR",
    "TZ",
    "VLLM_DTYPE",
    "VLLM_GPU_MEMORY_UTILIZATION",
    "VLLM_KV_CACHE_DTYPE",
    "VLLM_LOGGING_LEVEL",
    "VLLM_MAX_MODEL_LEN",
    "VLLM_MAX_NUM_BATCHED_TOKENS",
    "VLLM_MAX_NUM_SEQS",
    "VLLM_MODEL",
    "VLLM_MODEL_REVISION",
    "VLLM_TENSOR_PARALLEL_SIZE",
    "VLLM_WORKER_MULTIPROC_METHOD",
]

MAIN = "docker-compose.yml"
TUTOR = "docker-compose.tutor.yml"


@pytest.fixture
def compose_dir(tmp_path):
    """Copia ambos ficheros de compose a tmp_path con .env y test.env."""
    shutil.copy(ROOT / MAIN, tmp_path / MAIN)
    shutil.copy(ROOT / TUTOR, tmp_path / TUTOR)
    (tmp_path / ".env").write_text("")  # lo exige env_file: .env de rag-api
    (tmp_path / "test.env").write_text(
        "\n".join(f"{name}=x" for name in ENV_VARS) + "\n"
    )
    return tmp_path


def compose(compose_dir, files, *args):
    """Ejecuta docker compose con los ficheros indicados y devuelve stdout."""
    cmd = ["docker", "compose", "-p", "t", "--env-file", "test.env"]
    for f in files:
        cmd += ["-f", f]
    cmd += list(args)
    result = subprocess.run(cmd, cwd=compose_dir, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(
            f"docker compose falló (rc={result.returncode}):\n{result.stderr}"
        )
    return result.stdout


def test_addon_no_cambia_servicios_compartidos(compose_dir):
    if shutil.which("docker") is None:
        pytest.skip("docker no disponible")
    solo = compose(compose_dir, [MAIN], "config", "--hash", "vllm,qdrant,rag-api")
    con_tutor = compose(
        compose_dir, [MAIN, TUTOR], "config", "--hash", "vllm,qdrant,rag-api"
    )
    assert solo == con_tutor


def test_servicios_del_tutor_restart_no_y_solo_localhost(compose_dir):
    if shutil.which("docker") is None:
        pytest.skip("docker no disponible")
    config = json.loads(
        compose(compose_dir, [MAIN, TUTOR], "config", "--format", "json")
    )
    services = config["services"]
    for name, host_port in (("tutor-webui", "8080"), ("tutor-oauth2-proxy", "4180")):
        svc = services[name]
        assert svc["restart"] == "no"
        ports = svc.get("ports", [])
        assert ports, f"{name} no publica puertos"
        for port in ports:
            assert port["host_ip"] == "127.0.0.1"
            assert str(port["published"]) == host_port


def test_bd_del_tutor_separada(compose_dir):
    if shutil.which("docker") is None:
        pytest.skip("docker no disponible")
    config = json.loads(
        compose(compose_dir, [MAIN, TUTOR], "config", "--format", "json")
    )
    volumes = config["services"]["tutor-webui"].get("volumes", [])
    assert any(
        v.get("target") == "/app/backend/data" and v.get("source", "").endswith("tutor/data")
        for v in volumes
    )


def test_proxy_del_tutor_apunta_al_webui_del_tutor(compose_dir):
    if shutil.which("docker") is None:
        pytest.skip("docker no disponible")
    config = json.loads(
        compose(compose_dir, [MAIN, TUTOR], "config", "--format", "json")
    )
    command = config["services"]["tutor-oauth2-proxy"]["command"]
    assert "--upstream=http://tutor-webui:8080" in command


def test_make_tutor():
    result = subprocess.run(
        ["make", "-n", "-C", str(ROOT), "tutor"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "COMPOSE_FILE=docker-compose.yml:docker-compose.tutor.yml" in out
    assert "stop ingestor oauth2-proxy openwebui" in out
    assert "up -d qdrant vllm rag-api tutor-webui tutor-oauth2-proxy" in out


def test_make_ingest_y_web_paran_el_tutor():
    for target in ("ingest", "web"):
        result = subprocess.run(
            ["make", "-n", "-C", str(ROOT), target], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert "stop tutor-oauth2-proxy tutor-webui" in result.stdout, target


def test_make_tutor_off_vuelve_a_web():
    result = subprocess.run(
        ["make", "-n", "-C", str(ROOT), "tutor-off"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "stop tutor-oauth2-proxy tutor-webui" in out
    assert "up -d oauth2-proxy openwebui rag-api vllm qdrant" in out


def test_readme_documenta_el_modo_tutor():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Modo tutor" in readme
    assert "make tutor-off" in readme
    assert "tutor-ari" in readme
