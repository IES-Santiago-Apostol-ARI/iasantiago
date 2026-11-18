# Archivo: rag-api/tests/test_retrieve_concurrency.py
# Descripción: /retrieve corre la parte síncrona en un hilo con límite de
# concurrencia (T14): 4 búsquedas a la vez con el límite por defecto, en serie
# con límite 1, /healthz no queda detrás de un retrieve, y la caché de modelos
# carga una sola vez bajo 8 hilos.
#
# Se usa httpx.AsyncClient con ASGITransport (sin pytest-asyncio) y NO se
# ejecuta el lifespan, así que no se carga ningún modelo: las etapas de
# retrieval se parchean igual que en test_retrieve_timings.py, con
# choose_retrieval durmiendo para que la concurrencia sea medible.

import asyncio
import threading
import time

import httpx
import pytest

import app as app_module
from config.settings import OPENAI_API_KEY
from core import cache as core_cache

AUTH = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

FAKE_CHUNKS = [
    {"text": "t", "file_path": "f.pdf", "page": 1, "chunk_id": "c1"},
]
FAKE_META = {"mode": "hybrid", "original_language": "es", "final_topk": 5}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_module.app),
        base_url="http://t",
    )


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Mismos parches que test_retrieve_timings.py: TOPIC_LABELS fijo,
    collection_exists → True, telemetry y citaciones neutras, rerank y trim
    devuelven lo que reciben, y choose_retrieval duerme 0,3 s y devuelve un
    fragmento falso."""
    def choose_retrieval(*a, **k):
        time.sleep(0.3)
        return FAKE_CHUNKS, dict(FAKE_META)

    monkeypatch.setattr(app_module, "TOPIC_LABELS", ["Latin"])
    monkeypatch.setattr(app_module, "choose_retrieval", choose_retrieval)
    monkeypatch.setattr(app_module, "rerank_passages", lambda q, p, rerank_topk=None: p)
    monkeypatch.setattr(app_module, "soft_trim_context", lambda p, limit: p)
    monkeypatch.setattr(app_module, "attach_citations", lambda p, t: ("ctx", []))
    monkeypatch.setattr(app_module, "collection_exists", lambda t: True)
    monkeypatch.setattr(app_module, "telemetry_log", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "_build_citations", lambda *a, **k: [])


def _post(client: httpx.AsyncClient) -> httpx.Response:
    return client.post(
        "/retrieve", json={"query": "quid est", "topic": "Latin"}, headers=AUTH
    )


async def _four_posts() -> tuple:
    async with _client() as client:
        t0 = time.perf_counter()
        responses = await asyncio.gather(*[_post(client) for _ in range(4)])
        return time.perf_counter() - t0, responses


def test_cuatro_a_la_vez_con_limite_4(monkeypatch, fake_pipeline):
    monkeypatch.setattr(app_module, "RETRIEVE_MAX_CONCURRENCY", 4)
    elapsed, responses = asyncio.run(_four_posts())
    assert all(r.status_code == 200 for r in responses)
    # 4 búsquedas de 0,3 s en paralelo caben en un solo ciclo, con margen.
    assert elapsed < 0.8


def test_en_serie_con_limite_1(monkeypatch, fake_pipeline):
    monkeypatch.setattr(app_module, "RETRIEVE_MAX_CONCURRENCY", 1)
    elapsed, responses = asyncio.run(_four_posts())
    assert all(r.status_code == 200 for r in responses)
    # 4 búsquedas de 0,3 s en serie → ~1,2 s.
    assert elapsed >= 1.2
    # La última en entrar espera ~0,9 s en la cola (≥ 800 ms de margen).
    queues = [r.json()["meta"]["timings_ms"]["queue"] for r in responses]
    assert max(queues) >= 800


def test_healthz_no_espera_a_retrieve(monkeypatch, fake_pipeline):
    # choose_retrieval duerme 0,6 s: si /healthz se atendiera en el mismo
    # bucle bloqueado, tardaría más de 0,3 s en responder.
    def choose_retrieval(*a, **k):
        time.sleep(0.6)
        return FAKE_CHUNKS, dict(FAKE_META)

    monkeypatch.setattr(app_module, "choose_retrieval", choose_retrieval)

    async def main():
        async with _client() as client:
            retrieve_task = asyncio.ensure_future(_post(client))
            await asyncio.sleep(0.1)
            t0 = time.perf_counter()
            health = await client.get("/healthz")
            elapsed = time.perf_counter() - t0
            return elapsed, health, await retrieve_task

    elapsed, health, retrieve = asyncio.run(main())
    assert health.status_code == 200
    assert retrieve.status_code == 200
    assert elapsed < 0.3


def test_queue_en_meta(monkeypatch, fake_pipeline):
    async def main():
        async with _client() as client:
            return await _post(client)

    r = asyncio.run(main())
    assert r.status_code == 200
    queue = r.json()["meta"]["timings_ms"]["queue"]
    assert isinstance(queue, int)
    assert queue >= 0


def test_lock_de_cache_carga_una_vez(monkeypatch):
    instancias = 0

    class FakeReranker:
        def __init__(self, model_name):
            nonlocal instancias
            instancias += 1
            time.sleep(0.05)

    monkeypatch.setattr(core_cache, "CrossEncoderReranker", FakeReranker)
    monkeypatch.setattr(core_cache.ModelCache, "_reranker", None)

    def cargar():
        core_cache.ModelCache.get_reranker("x")

    hilos = [threading.Thread(target=cargar) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert instancias == 1
    monkeypatch.setattr(core_cache.ModelCache, "_reranker", None)
