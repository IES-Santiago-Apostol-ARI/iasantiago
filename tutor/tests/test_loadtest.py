"""Tests for scripts/loadtest_tutor.py against a simulated HTTP server.

No real vLLM or rag-api: a ThreadingHTTPServer records every request
(path, headers, JSON body) and answers according to the fixture's `mode`.
"""

import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "loadtest_tutor.py"

SSE_OK = (
    'data: {"choices":[{"delta":{"content":"Hola"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":" ¿qué has probado?"}}]}\n\n'
    'data: {"choices":[],"usage":{"completion_tokens":7}}\n\n'
    'data: [DONE]\n\n'
)
SSE_EMPTY = "data: [DONE]\n\n"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.server.requests.append(
            {"path": self.path, "headers": dict(self.headers), "body": body}
        )
        mode = self.server.mode
        if self.path == "/v1/chat/completions":
            if mode == "http500":
                data = b"boom"
                self.send_response(500)
            else:
                data = (SSE_OK if mode == "ok" else SSE_EMPTY).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/retrieve":
            data = json.dumps({"context": "FRAGMENTO-DE-PRUEBA"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def server(request):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.requests = []
    srv.mode = request.param
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def run_script(server, *extra, env=None):
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--students", "3",
        "--vllm-url", f"http://127.0.0.1:{server.server_address[1]}/v1",
    ]
    cmd += list(extra)
    if env is None:
        env = dict(os.environ)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)


def chat_requests(server):
    return [r for r in server.requests if r["path"] == "/v1/chat/completions"]


@pytest.mark.parametrize("server", ["ok"], indirect=True)
def test_todos_los_alumnos_ok(server):
    result = run_script(server)
    assert result.returncode == 0
    assert "succeeded: 3" in result.stdout
    assert "failed: 0" in result.stdout
    chats = chat_requests(server)
    assert len(chats) == 3
    for req in chats:
        assert req["body"]["model"] == "santiago"
        assert req["body"]["stream"] is True


@pytest.mark.parametrize("server", ["ok"], indirect=True)
def test_tokens_vienen_de_usage(server):
    result = run_script(server)
    assert "aggregate output:" in result.stdout
    assert "(21 tokens)" in result.stdout


@pytest.mark.parametrize("server", ["http500"], indirect=True)
def test_fallo_http_cuenta_como_fallido(server):
    result = run_script(server, "--students", "2")
    assert result.returncode == 1
    assert "FAILED HTTP 500" in result.stdout
    assert "failed: 2" in result.stdout


@pytest.mark.parametrize("server", ["empty"], indirect=True)
def test_sin_texto_es_fallo(server):
    result = run_script(server)
    assert result.returncode == 1
    assert "no text received" in result.stdout


@pytest.mark.parametrize("server", ["ok"], indirect=True)
def test_retrieve_antes_del_chat(server):
    port = server.server_address[1]
    result = run_script(
        server,
        "--students", "1",
        "--topic", "Programming",
        "--rag-key", "K",
        "--rag-url", f"http://127.0.0.1:{port}",
    )
    assert result.returncode == 0
    retrieve_idx = [i for i, r in enumerate(server.requests)
                    if r["path"] == "/retrieve"]
    chat_idx = [i for i, r in enumerate(server.requests)
                if r["path"] == "/v1/chat/completions"]
    assert len(retrieve_idx) == 1
    assert len(chat_idx) == 1
    assert retrieve_idx[0] < chat_idx[0]
    retrieves = [server.requests[i] for i in retrieve_idx]
    assert retrieves[0]["headers"]["Authorization"] == "Bearer K"
    assert retrieves[0]["body"]["topic"] == "Programming"
    assert retrieves[0]["body"]["query"]
    chats = chat_requests(server)
    assert len(chats) == 1
    user_msgs = [m for m in chats[0]["body"]["messages"] if m["role"] == "user"]
    assert user_msgs[0]["content"].startswith("FRAGMENTO-DE-PRUEBA")


@pytest.mark.parametrize("server", ["ok"], indirect=True)
def test_top_k_se_envia_a_retrieve(server):
    port = server.server_address[1]
    result = run_script(
        server,
        "--students", "1",
        "--topic", "Programming",
        "--top-k", "8",
        "--rag-key", "K",
        "--rag-url", f"http://127.0.0.1:{port}",
    )
    assert result.returncode == 0
    retrieves = [r for r in server.requests if r["path"] == "/retrieve"]
    assert len(retrieves) == 1
    assert retrieves[0]["body"]["top_k"] == 8


@pytest.mark.parametrize("server", ["ok"], indirect=True)
def test_sin_top_k_no_se_envia(server):
    port = server.server_address[1]
    result = run_script(
        server,
        "--students", "1",
        "--topic", "Programming",
        "--rag-key", "K",
        "--rag-url", f"http://127.0.0.1:{port}",
    )
    assert result.returncode == 0
    retrieves = [r for r in server.requests if r["path"] == "/retrieve"]
    assert len(retrieves) == 1
    assert "top_k" not in retrieves[0]["body"]


@pytest.mark.parametrize("server", ["ok"], indirect=True)
def test_prompt_file_va_como_system(server, tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("SOY-EL-PROMPT", encoding="utf-8")
    result = run_script(server, "--students", "1", "--prompt-file", str(prompt))
    assert result.returncode == 0
    chats = chat_requests(server)
    assert len(chats) == 1
    assert chats[0]["body"]["messages"][0] == {
        "role": "system",
        "content": "SOY-EL-PROMPT",
    }


@pytest.mark.parametrize("server", ["ok"], indirect=True)
def test_topic_sin_clave_es_error_de_uso(server):
    env = {k: v for k, v in os.environ.items() if k != "RAG_KEY"}
    result = run_script(server, "--students", "1", "--topic", "X", env=env)
    assert result.returncode == 2
    assert "--topic needs the rag-api key" in result.stderr


@pytest.mark.parametrize("server", ["ok"], indirect=True)
def test_sin_prompt_file_no_hay_system(server):
    result = run_script(server, "--students", "1")
    assert result.returncode == 0
    chats = chat_requests(server)
    assert len(chats) == 1
    assert chats[0]["body"]["messages"][0]["role"] == "user"
