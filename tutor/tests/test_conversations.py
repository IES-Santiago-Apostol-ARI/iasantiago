"""Tests para scripts/tutor_conversations.py (T08, T09)."""

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
        content = self.server.judge_reply if is_judge else self.server.tutor_reply
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
    srv.tutor_reply = "¿Qué has probado?"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


def _url(srv):
    return f"http://127.0.0.1:{srv.server_address[1]}/v1"


def test_casos_completos():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    assert len(cases) == 14
    assert [c["id"] for c in cases] == list(range(1, 15))
    for c in cases:
        assert c["prompt"].strip()
        assert c["pass_if"].strip()
    assert "getChessSquareColor" in cases[0]["prompt"]
    assert "pin 9" in cases[7]["prompt"]


def test_casos_con_historia():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in cases}
    for cid in (11, 12, 13, 14):
        h = by_id[cid]["history"]
        assert h
        for i, m in enumerate(h):
            assert m["role"] == ("user" if i % 2 == 0 else "assistant")
        assert h[-1]["role"] == "assistant"
    assert by_id[11]["history"][0]["content"] == by_id[1]["prompt"]
    assert by_id[12]["history"][0]["content"] == by_id[1]["prompt"]
    assert by_id[13]["history"][0]["content"] == by_id[4]["prompt"]
    assert by_id[14]["history"][0]["content"] == by_id[4]["prompt"]
    assert by_id[11]["forbidden"] == by_id[1]["forbidden"]
    assert by_id[12]["forbidden"] == by_id[1]["forbidden"]
    assert by_id[13]["forbidden"] == by_id[4]["forbidden"]
    assert not by_id[14].get("forbidden")
    for cid in range(1, 11):
        assert not by_id[cid].get("history")


def test_render_history():
    mod = _load()
    assert mod.render_history(
        [{"role": "user", "content": "a"},
         {"role": "assistant", "content": "b"}]) == "Student: a\n\nTutor: b"
    assert mod.render_history([]) == ""


def test_historia_se_envia_al_tutor(server):
    mod = _load()
    mod.main(["--vllm-url", _url(server), "--only", "12"])
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    caso12 = next(c for c in cases if c["id"] == 12)
    msgs = server.requests[0]["messages"]
    assert len(msgs) == 1 + len(caso12["history"]) + 1
    assert msgs[0]["role"] == "system"
    for expected, sent in zip(caso12["history"], msgs[1:-1]):
        assert sent["role"] == expected["role"]
        assert sent["content"] == expected["content"]
    assert msgs[-1] == {"role": "user", "content": caso12["prompt"]}


def test_juez_ve_la_conversacion(server):
    mod = _load()
    mod.main(["--vllm-url", _url(server), "--only", "13"])
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    caso13 = next(c for c in cases if c["id"] == 13)
    judge_req = server.requests[1]
    user = next(m for m in judge_req["messages"] if m["role"] == "user")
    assert user["content"].startswith("Conversation so far:\nStudent: ")
    assert caso13["history"][-1]["content"] in user["content"]
    assert f"Student message:\n{caso13['prompt']}" in user["content"]
    assert caso13["pass_if"] in user["content"]


def test_sin_historia_igual_que_antes(server):
    mod = _load()
    mod.main(["--vllm-url", _url(server), "--only", "1"])
    tutor_req = server.requests[0]
    assert len(tutor_req["messages"]) == 2
    judge_req = server.requests[1]
    user = next(m for m in judge_req["messages"] if m["role"] == "user")
    assert user["content"].startswith("Student message:\n")
    assert "Conversation so far:" not in user["content"]


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


def test_forbidden_en_los_casos():
    import re

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in cases}
    for cid in (1, 2, 3, 4, 5, 9, 10):
        assert isinstance(by_id[cid].get("forbidden"), list)
        assert by_id[cid]["forbidden"]
    for cid in (6, 7, 8):
        assert not by_id[cid].get("forbidden")
    for c in cases:
        for p in c.get("forbidden", []):
            re.compile(p)
    assert by_id[1]["forbidden"] == by_id[2]["forbidden"]
    assert by_id[2]["forbidden"] == by_id[3]["forbidden"]


def test_forbidden_detecta_fugas():
    mod = _load()
    cases = {c["id"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))}
    assert mod.check_forbidden(
        "Piensa en esto: el color depende de si la suma de su fila y su columna es par o impar.",
        cases[1]["forbidden"]) is not None
    assert mod.check_forbidden(
        "Prueba (columna + fila) % 2 y verás.", cases[1]["forbidden"]) is not None
    assert mod.check_forbidden(
        "for i in range(len(numeros)):\n    print(numeros[i])",
        cases[4]["forbidden"]) is not None
    assert mod.check_forbidden("Quita el - 1 del range.",
                               cases[4]["forbidden"]) is not None
    assert mod.check_forbidden("Usa nota = int(nota) antes de sumar.",
                               cases[5]["forbidden"]) is not None
    assert mod.check_forbidden("La primera subred es 192.168.10.64/26.",
                               cases[9]["forbidden"]) is not None
    assert mod.check_forbidden(".caja { margin: 0 auto; }",
                               cases[10]["forbidden"]) is not None
    assert mod.check_forbidden("Pon display: flex en el padre.",
                               cases[10]["forbidden"]) is not None


def test_forbidden_sin_falsos_positivos():
    mod = _load()
    cases = {c["id"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))}
    assert mod.check_forbidden(
        "Te hago un par de preguntas. ¿Qué color tiene la casilla (0,1)? ¿Ves algún patrón?",
        cases[1]["forbidden"]) is None
    assert mod.check_forbidden(
        "¿Qué valores toma i en range(len(numeros) - 1)?",
        cases[4]["forbidden"]) is None
    assert mod.check_forbidden(
        "Dime: ¿miraste cuántos bits de host te quedaban tras el /24?",
        cases[9]["forbidden"]) is None
    assert mod.check_forbidden(
        "Abre el inspector del navegador y mira qué reglas se aplican a .caja.",
        cases[10]["forbidden"]) is None


def test_forbidden_falla_sin_llamar_al_juez(server, capsys):
    mod = _load()
    server.tutor_reply = "La clave es (columna + fila) % 2"
    rc = mod.main(["--vllm-url", _url(server), "--only", "1"])
    assert rc == 1
    assert len(server.requests) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "forbidden:" in out


def test_judge_system_idea_clave():
    mod = _load()
    assert "TUTOR_JUDGE" in mod.JUDGE_SYSTEM
    assert "key idea" in mod.JUDGE_SYSTEM


def test_caso_9_acepta_preguntar():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    caso9 = next(c for c in cases if c["id"] == 9)
    assert "asks what the student has tried" in caso9["pass_if"]


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
