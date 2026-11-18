"""Tests de la valve top_k_map del Filter de RAG (T15).

Se ejecutan con el python3 del sistema, que tiene pydantic pero no aiohttp:
antes de importar el Filter se mete un aiohttp falso en sys.modules.
"""

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

FILTER_PATH = (
    Path(__file__).resolve().parents[2]
    / "openwebui"
    / "functions"
    / "rag_retrieval_filter.py"
)


def _install_fake_aiohttp():
    fake = types.ModuleType("aiohttp")
    sent = []

    class ClientTimeout:
        def __init__(self, total=None):
            self.total = total

    class _PostCtx:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self):
            return {"context": "ctx", "meta": {"num_chunks": 1}}

    class ClientSession:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, json=None, headers=None):
            sent.append(json)
            return _PostCtx()

    fake.ClientTimeout = ClientTimeout
    fake.ClientSession = ClientSession
    fake.sent = sent
    sys.modules["aiohttp"] = fake
    return fake


_fake = _install_fake_aiohttp()
_spec = importlib.util.spec_from_file_location("rag_retrieval_filter", FILTER_PATH)
_filter_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_filter_mod)
Filter = _filter_mod.Filter


def run_inlet(valves_kwargs, model):
    f = Filter()
    for key, value in valves_kwargs.items():
        setattr(f.valves, key, value)
    _fake.sent.clear()
    asyncio.run(
        f.inlet(
            {"messages": [{"role": "user", "content": "hola"}]},
            __model__=model,
        )
    )
    return _fake.sent[-1]


def test_top_k_por_id():
    payload = run_inlet(
        {"top_k_map": '{"tutor-ari": 8}'},
        {"id": "tutor-ari", "name": "Tutor Informática"},
    )
    assert payload["top_k"] == 8


def test_top_k_por_nombre():
    payload = run_inlet(
        {"top_k_map": '{"Tutor Informática": 6}'},
        {"id": "tutor-ari", "name": "Tutor Informática"},
    )
    assert payload["top_k"] == 6


def test_otro_modelo_sin_top_k():
    payload = run_inlet(
        {"top_k_map": '{"tutor-ari": 8}'},
        {"id": "quimica", "name": "Química"},
    )
    assert "top_k" not in payload


def test_reserva_global():
    payload = run_inlet(
        {"top_k": 12, "top_k_map": '{"quimica": 8}'},
        {"id": "latino", "name": "Latín"},
    )
    assert payload["top_k"] == 12
    payload = run_inlet(
        {"top_k": 12, "top_k_map": '{"quimica": 8}'},
        {"id": "quimica", "name": "Química"},
    )
    assert payload["top_k"] == 8


def test_mapa_invalido_no_rompe():
    payload = run_inlet(
        {"top_k_map": "{oops"},
        {"id": "tutor-ari", "name": "Tutor Informática"},
    )
    assert "top_k" not in payload
    payload = run_inlet(
        {"top_k_map": "[1,2]"},
        {"id": "tutor-ari", "name": "Tutor Informática"},
    )
    assert "top_k" not in payload


def test_valores_no_validos_se_ignoran():
    bad = {"a": 0, "b": -3, "c": "abc", "d": True, "e": None}
    payload = run_inlet(
        {"top_k": 5, "top_k_map": json.dumps(bad)},
        {"id": "a", "name": "A"},
    )
    assert payload["top_k"] == 5


def test_resolve_top_k_sin_modelo():
    f = Filter()
    f.valves.top_k = 0
    assert f._resolve_top_k(None) == 0


def test_version():
    text = FILTER_PATH.read_text(encoding="utf-8")
    assert "version: 0.3.0" in text
