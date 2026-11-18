# Archivo: rag-api/tests/test_retrieve_timings.py
# Descripción: /retrieve devuelve los tiempos de cada etapa en meta["timings_ms"]
# y los escribe en una línea de log, sin cambiar nada más del comportamiento.
#
# Se usa TestClient sin `with`, así que NO se ejecuta el lifespan y no se carga
# ningún modelo: las etapas de retrieval se parchean con fakes que duermen un
# poco para que los tiempos medidos sean distinguibles de cero.

import logging
import time

import pytest
from fastapi.testclient import TestClient

import app as app_module
from config.settings import OPENAI_API_KEY

AUTH = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

FAKE_CHUNKS = [
    {"text": "t", "file_path": "f.pdf", "page": 1, "chunk_id": "c1"},
]
FAKE_META = {"mode": "hybrid", "original_language": "es", "final_topk": 5}


@pytest.fixture
def client():
    return TestClient(app_module.app)


@pytest.fixture
def topics(monkeypatch):
    """TOPIC_LABELS conocido y fijo, para no depender del .env de la máquina."""
    labels = ["Latin"]
    monkeypatch.setattr(app_module, "TOPIC_LABELS", labels)
    return labels


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Parchea todas las etapas de /retrieve con fakes deterministas.

    `choose_retrieval` y `rerank_passages` duermen 0,03 s para que sus tiempos
    medidos no sean cero; el resto devuelve datos fijos sin dormir.
    Devuelve una lista `llamadas` con el nombre de cada etapa que se ejecutó,
    para comprobar qué se llamó y qué no.
    """
    llamadas = []

    def choose_retrieval(*a, **k):
        llamadas.append("choose_retrieval")
        time.sleep(0.03)
        return FAKE_CHUNKS, dict(FAKE_META)

    def rerank_passages(query, passages, rerank_topk=None):
        llamadas.append("rerank_passages")
        time.sleep(0.03)
        return passages

    def soft_trim_context(passages, limit):
        llamadas.append("soft_trim_context")
        return passages

    def attach_citations(passages, topic):
        llamadas.append("attach_citations")
        return ("ctx", [])

    monkeypatch.setattr(app_module, "choose_retrieval", choose_retrieval)
    monkeypatch.setattr(app_module, "rerank_passages", rerank_passages)
    monkeypatch.setattr(app_module, "soft_trim_context", soft_trim_context)
    monkeypatch.setattr(app_module, "attach_citations", attach_citations)
    monkeypatch.setattr(app_module, "collection_exists", lambda t: True)
    monkeypatch.setattr(app_module, "telemetry_log", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "_build_citations", lambda *a, **k: [])
    return llamadas


def _body(**extra) -> dict:
    body = {"query": "quid est", "topic": "Latin"}
    body.update(extra)
    return body


# ---------------------------------------------------------------- timings_ms


def test_meta_lleva_los_tiempos(client, topics, fake_pipeline):
    r = client.post("/retrieve", json=_body(), headers=AUTH)
    assert r.status_code == 200
    timings = r.json()["meta"]["timings_ms"]
    assert set(timings) == {"queue", "retrieval", "rerank", "trim", "citations", "total"}
    for valor in timings.values():
        assert isinstance(valor, int)
        assert valor >= 0
    # Las etapas que duermen 0,03 s tienen que verse en la medición.
    assert timings["retrieval"] >= 25
    assert timings["rerank"] >= 25
    # `total` cubre al menos la suma de las etapas (el redondeo a ms puede
    # restar hasta 1 ms por etapa).
    assert timings["total"] >= (
        timings["retrieval"] + timings["rerank"] + timings["trim"]
        + timings["citations"] - 4
    )


def test_sin_rerank_cuenta_cero(client, topics, fake_pipeline):
    r = client.post("/retrieve", json=_body(rerank=False), headers=AUTH)
    assert r.status_code == 200
    timings = r.json()["meta"]["timings_ms"]
    assert timings["rerank"] == 0
    assert "rerank_passages" not in fake_pipeline


def test_sin_resultados_rerank_y_trim_cero(client, topics, monkeypatch, fake_pipeline):
    monkeypatch.setattr(
        app_module,
        "choose_retrieval",
        lambda *a, **k: ([], dict(FAKE_META)),
    )
    r = client.post("/retrieve", json=_body(), headers=AUTH)
    assert r.status_code == 200
    timings = r.json()["meta"]["timings_ms"]
    assert timings["rerank"] == 0
    assert timings["trim"] == 0
    # La clave sigue estando aunque todo sea cero.
    assert set(timings) == {"queue", "retrieval", "rerank", "trim", "citations", "total"}


# ---------------------------------------------------------------- log


def test_linea_de_log(client, topics, fake_pipeline, caplog):
    caplog.set_level(logging.INFO)
    r = client.post("/retrieve", json=_body(), headers=AUTH)
    assert r.status_code == 200
    mensajes = [rec.message for rec in caplog.records]
    assert any(
        "[/retrieve] tiempos ms: queue=" in m
        and "total=" in m
        and "topic=Latin" in m
        for m in mensajes
    )


# ---------------------------------------------------------------- resto de meta


def test_el_resto_de_meta_no_cambia(client, topics, fake_pipeline):
    r = client.post("/retrieve", json=_body(), headers=AUTH)
    assert r.status_code == 200
    meta = r.json()["meta"]
    assert meta["topic"] == "Latin"
    assert meta["mode"] == "hybrid"
    assert meta["generative"] is False
    assert meta["num_chunks"] == 1
    assert meta["final_topk"] == 5
    assert meta["original_language"] == "es"
    assert meta["context_token_limit"] is not None
    # timings_ms es la última clave del diccionario.
    assert list(meta)[-1] == "timings_ms"


# ---------------------------------------------------------------- salidas tempranas


def test_coleccion_inexistente_sin_tiempos(client, topics, monkeypatch):
    monkeypatch.setattr(app_module, "collection_exists", lambda t: False)
    r = client.post("/retrieve", json=_body(), headers=AUTH)
    assert r.status_code == 200
    assert "timings_ms" not in r.json()["meta"]
