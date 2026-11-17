"""Tests para scripts/tutor_conversations.py (T08)."""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "tutor_conversations.py"
CASES = ROOT / "eval" / "tutor_cases.json"
PROMPT_FILE = ROOT / "rag-api" / "templates" / "system_prompts" / "per_topic" / "TutorInformatica.txt"


def _load():
    spec = importlib.util.spec_from_file_location("tutor_conversations", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.server.requests.append(body)
        is_judge = any(
            m.get("role") == "system" and "TUTOR_JUDGE" in str(m.get("content", ""))
            for m in body.get("messages", [])
        )
        content = self.server.judge_reply if is_judge else "¿Qué has probado?"
        payload = json.dumps(
            {"choices": [{"message": {"content": content}}]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.requests = []
    srv.judge_reply = '{"verdict": "PASS", "reason": "ok"}'
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


def _url(srv):
    return f"http://127.0.0.1:{srv.server_address[1]}/v1"


def test_casos_completos():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    assert len(cases) == 10
    assert [c["id"] for c in cases] == list(range(1, 11))
    for c in cases:
        assert c["prompt"].strip()
        assert c["pass_if"].strip()
    assert "getChessSquareColor" in cases[0]["prompt"]
    assert "pin 9" in cases[7]["prompt"]


def test_parse_verdict_variantes():
    mod = _load()
    assert mod.parse_verdict('{"verdict": "PASS", "reason": "ok"}') == {
        "verdict": "PASS", "reason": "ok"
    }
    fenced = '```json\n{"verdict": "FAIL", "reason": "dio código"}\n```'
    assert mod.parse_verdict(fenced) == {"verdict": "FAIL", "reason": "dio código"}
    wrapped = 'El veredicto es: {"verdict": "PASS", "reason": "bien"} fin.'
    assert mod.parse_verdict(wrapped) == {"verdict": "PASS", "reason": "bien"}
    assert mod.parse_verdict('{"verdict": "fail", "reason": "r"}')["verdict"] == "FAIL"
    assert mod.parse_verdict("sin json aquí")["verdict"] == "ERROR"
    assert mod.parse_verdict('{"verdict": "MAYBE", "reason": "?"}')["verdict"] == "ERROR"


def test_main_todo_pasa(server, capsys):
    mod = _load()
    rc = mod.main(["--vllm-url", _url(server), "--only", "1,2"])
    assert rc == 0
    assert len(server.requests) == 4
    tutor_req = server.requests[0]
    system = next(m for m in tutor_req["messages"] if m["role"] == "system")
    assert system["content"] == PROMPT_FILE.read_text(encoding="utf-8")
    assert tutor_req["temperature"] == 0
    assert tutor_req["stream"] is False
    assert tutor_req["max_tokens"] == 600
    judge_req = server.requests[1]
    assert judge_req["max_tokens"] == 200
    user = next(m for m in judge_req["messages"] if m["role"] == "user")
    case1 = json.loads(CASES.read_text(encoding="utf-8"))[0]
    assert case1["pass_if"] in user["content"]
    assert "¿Qué has probado?" in user["content"]
    out = capsys.readouterr().out
    assert "Passed: 2/2" in out


def test_only_invalido_o_vacio():
    mod = _load()
    with pytest.raises(SystemExit) as e:
        mod.main(["--only", "abc"])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e:
        mod.main(["--only", "99"])
    assert e.value.code == 2


def test_main_falla_si_un_caso_falla(server, capsys):
    mod = _load()
    server.judge_reply = '{"verdict":"FAIL","reason":"dio código"}'
    rc = mod.main(["--vllm-url", _url(server), "--only", "1"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "Passed: 0/1" in out


def test_error_http_no_aborta(capsys):
    mod = _load()
    rc = mod.main(
        ["--vllm-url", "http://127.0.0.1:9/v1", "--only", "1,2", "--timeout", "2"]
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert out.count("ERROR") >= 2


def test_out_escribe_json(server, tmp_path):
    mod = _load()
    out_file = tmp_path / "r.json"
    rc = mod.main(
        ["--vllm-url", _url(server), "--only", "1", "--out", str(out_file)]
    )
    assert rc == 0
    results = json.loads(out_file.read_text(encoding="utf-8"))
    assert isinstance(results, list) and len(results) == 1
    for key in ("id", "prompt", "reply", "verdict", "reason"):
        assert key in results[0]
