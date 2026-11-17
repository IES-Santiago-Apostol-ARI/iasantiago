# T02 — Prueba de carga del tutor en el repo, con tests

## Objetivo
Traer `loadtest.py` al repo como `scripts/loadtest_tutor.py` y cubrirlo con tests
contra un servidor HTTP simulado (sin vLLM ni rag-api reales).

## Ficheros que puedes tocar (SOLO estos)
- `scripts/loadtest_tutor.py` (nuevo)
- `tutor/tests/test_loadtest.py` (nuevo)

## Pasos (TDD)
1. Escribe primero `tutor/tests/test_loadtest.py` (abajo). Ejecútalo: FALLA (rojo),
   porque el script aún no existe.
2. `cp /datos/Clases/tutor/loadtest.py scripts/loadtest_tutor.py`
3. En `scripts/loadtest_tutor.py` cambia SOLO el docstring del módulo:
   - `See PLAN.md, Phase 2.` → `See tasks/PLAN.md and the tutor plan, Phase 2.`
   - En los dos ejemplos de uso, `python3 loadtest.py --prompt-file tutor-prompt.md`
     pasa a
     `python3 scripts/loadtest_tutor.py --prompt-file rag-api/templates/system_prompts/per_topic/TutorInformatica.txt`
   No cambies el código. Si un test exige cambiar código, PARA y pregunta con `hc send`.
4. Ejecuta los tests: PASAN (verde).

## Tests que debe contener `tutor/tests/test_loadtest.py`
Solo stdlib + pytest. Ejecuta el script como subproceso:
`subprocess.run([sys.executable, str(SCRIPT), ...], capture_output=True, text=True, timeout=60)`
con `SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "loadtest_tutor.py"`.

Servidor simulado: una fixture que arranca `http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)`
en un `threading.Thread(daemon=True)` y lo para con `shutdown()` al final. El
handler guarda cada petición recibida (ruta, cabeceras, cuerpo JSON) en una lista
compartida, y su comportamiento lo decide un atributo `mode` de la fixture:
- `mode="ok"`: `POST /v1/chat/completions` responde 200, `Content-Type: text/event-stream`,
  con estas líneas (cada una seguida de `\n\n`):
  `data: {"choices":[{"delta":{"content":"Hola"}}]}`,
  `data: {"choices":[{"delta":{"content":" ¿qué has probado?"}}]}`,
  `data: {"choices":[],"usage":{"completion_tokens":7}}`,
  `data: [DONE]`.
  `POST /retrieve` responde 200 con JSON `{"context": "FRAGMENTO-DE-PRUEBA"}`.
- `mode="http500"`: `POST /v1/chat/completions` responde 500 con cuerpo `boom`.
- `mode="empty"`: `POST /v1/chat/completions` responde 200 SSE con solo `data: [DONE]`.

Tests:
- `test_todos_los_alumnos_ok`: `--students 3 --vllm-url http://127.0.0.1:<port>/v1`
  → returncode 0, la salida contiene `succeeded: 3` y `failed: 0`, y el servidor
  recibió 3 peticiones a `/v1/chat/completions` con `"model": "santiago"` y `"stream": true`.
- `test_tokens_vienen_de_usage`: en `mode="ok"` la salida contiene `aggregate output:`
  y `(21 tokens)` (3 alumnos × 7).
- `test_fallo_http_cuenta_como_fallido`: `mode="http500"`, `--students 2` →
  returncode 1, la salida contiene `FAILED HTTP 500` y `failed: 2`.
- `test_sin_texto_es_fallo`: `mode="empty"` → returncode 1 y `no text received`.
- `test_retrieve_antes_del_chat`: `--students 1 --topic Programming --rag-key K
  --rag-url http://127.0.0.1:<port>` → returncode 0; el servidor recibió un
  `POST /retrieve` con cabecera `Authorization: Bearer K` y cuerpo
  `{"query": ..., "topic": "Programming"}`, y el mensaje `user` enviado al chat
  empieza por `FRAGMENTO-DE-PRUEBA`.
- `test_prompt_file_va_como_system`: escribe un fichero temporal con `SOY-EL-PROMPT`,
  pásalo con `--prompt-file` → el primer mensaje enviado al chat es
  `{"role": "system", "content": "SOY-EL-PROMPT"}`.
- `test_topic_sin_clave_es_error_de_uso`: `--topic X` sin `--rag-key` y con la
  variable `RAG_KEY` quitada del entorno (`env` sin `RAG_KEY`) → returncode 2.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_loadtest.py -q` → 7 passed en menos de 30 s.
- `diff /datos/Clases/tutor/loadtest.py scripts/loadtest_tutor.py` solo muestra
  cambios en el docstring.
- `git diff --stat tutor...HEAD` solo lista los 2 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T02: prueba de carga del tutor con tests contra servidor simulado'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
