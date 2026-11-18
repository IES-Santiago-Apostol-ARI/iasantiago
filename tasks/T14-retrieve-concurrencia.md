# T14 — `/retrieve` deja de bloquear el bucle de eventos

## Objetivo
Hoy `async def retrieve` ejecuta el embedder, Qdrant y el reranker de forma síncrona en
el único worker de uvicorn, así que las búsquedas se atienden de una en una y `/healthz`
espera detrás. La parte síncrona pasa a un hilo, con un límite de búsquedas simultáneas
configurable. Además, se pueden fijar los hilos de torch y el tokenizer se carga al
arrancar.

## Ficheros que puedes tocar (SOLO estos)
- `rag-api/app.py`
- `rag-api/core/cache.py`
- `rag-api/tests/test_retrieve_timings.py` (solo el cambio indicado abajo)
- `rag-api/tests/test_retrieve_concurrency.py` (nuevo)

## Entorno de tests (ya preparado; NO instales nada)
```
cd rag-api && /datos/lab-wt/.venv-rag/bin/python -m pytest tests -q -p no:cacheprovider
```
Antes de tu cambio pasan 75 tests.

## Cambios en `rag-api/app.py`
1. Imports: `import asyncio`, `import functools` y `import anyio` (anyio ya viene con
   starlette; no lo añadas a requirements).
2. Constante de módulo, junto a las demás de configuración del fichero:
   `RETRIEVE_MAX_CONCURRENCY = int(os.getenv("RETRIEVE_MAX_CONCURRENCY", "4"))`.
3. Función nueva:
   ```python
   _limiters: dict = {}

   def _get_retrieve_limiter() -> anyio.CapacityLimiter:
       """Un CapacityLimiter por (bucle de eventos, tamaño). Se crea dentro del bucle
       que lo usa (no al importar), y se rehace si cambia RETRIEVE_MAX_CONCURRENCY."""
       key = (id(asyncio.get_running_loop()), RETRIEVE_MAX_CONCURRENCY)
       if key not in _limiters:
           _limiters[key] = anyio.CapacityLimiter(RETRIEVE_MAX_CONCURRENCY)
       return _limiters[key]
   ```
   Lee `RETRIEVE_MAX_CONCURRENCY` en el momento de la llamada (los tests lo cambian con
   `monkeypatch.setattr(app_module, "RETRIEVE_MAX_CONCURRENCY", n)`).
4. Función síncrona nueva `_retrieve_sync(req, context_token_limit, t_enqueued)`. Hace
   EXACTAMENTE lo que hoy hace `retrieve` desde `choose_retrieval(...)` hasta
   `attach_citations(...)`, con las mismas mediciones de T13. Al empezar calcula
   `queue_s = time.perf_counter() - t_enqueued`. Devuelve
   `(retrieved, meta, context_text, cited, t_queue, t_retrieval, t_rerank, t_trim, t_citations)`.
   Las llamadas se hacen por nombre de módulo (`choose_retrieval(...)` etc., como ahora)
   para que los `monkeypatch.setattr(app_module, ...)` de los tests sigan funcionando.
5. En `retrieve`, ese tramo se sustituye por:
   ```python
   t_enqueued = time.perf_counter()
   (retrieved, meta, context_text, cited,
    t_queue, t_retrieval, t_rerank, t_trim, t_citations) = await anyio.to_thread.run_sync(
       functools.partial(_retrieve_sync, req, context_token_limit, t_enqueued),
       limiter=_get_retrieve_limiter(),
   )
   ```
   Lo de antes (validación 400, `collection_exists`, cálculo de `context_token_limit`)
   y lo de después (`telemetry_log`, `timings_ms`, log y `return`) no cambian, salvo:
   - `timings_ms` gana la clave `"queue"` (ms de espera hasta entrar en el hilo),
     colocada justo ANTES de `"retrieval"`;
   - la línea de log pasa a empezar por
     `"[/retrieve] tiempos ms: queue=%d retrieval=%d ..."`, con el resto igual.
6. `TORCH_NUM_THREADS`: en `lifespan`, ANTES de llamar a `ensure_models_loaded()`:
   ```python
   n = os.getenv("TORCH_NUM_THREADS")
   if n:
       import torch
       torch.set_num_threads(int(n))
       logger.info(f"torch.set_num_threads({int(n)})")
   ```
   Si la variable no existe, no se hace nada.
7. `ensure_models_loaded()`: al final del `try`, después del reranker, precarga el
   tokenizer: `ModelCache.get_tokenizer()`, con un `logger.info` antes y otro después,
   en el mismo estilo que los del embedder y el reranker. Importa `ModelCache` desde
   `core.cache` dentro de la función.
8. Registra en el log al arrancar (en `lifespan`) el valor de `RETRIEVE_MAX_CONCURRENCY`.

## Cambios en `rag-api/core/cache.py`
- `import threading` y un atributo de clase `_thread_lock = threading.Lock()`. NO
  toques el `_lock = asyncio.Lock()` que ya existe.
- En `get_embedder`, `get_reranker` y `get_tokenizer`: carga con doble comprobación.
  Si ya está en caché se devuelve sin lock; si no, `with cls._thread_lock:` se vuelve a
  comprobar y solo entonces se carga. El comportamiento para quien llama es el mismo.

## Cambio en `rag-api/tests/test_retrieve_timings.py`
En `test_meta_lleva_los_tiempos`, el conjunto exacto de claves pasa a ser
`queue, retrieval, rerank, trim, citations, total`. Es el único cambio permitido en
ese fichero; si algún otro test falla por la clave nueva, ajusta solo la parte de las
claves.

## Tests nuevos (`rag-api/tests/test_retrieve_concurrency.py`)
- Usa `httpx.AsyncClient(transport=httpx.ASGITransport(app=app_module.app), base_url="http://t")`
  dentro de `asyncio.run(...)`. Sin pytest-asyncio. No se ejecuta el lifespan.
- Mismos parches que `test_retrieve_timings.py`: `TOPIC_LABELS=["Latin"]`,
  `collection_exists` → True, `telemetry_log` y `_build_citations` neutros,
  `rerank_passages` y `soft_trim_context` devuelven lo que reciben, y
  `attach_citations` → `("ctx", [])`.
  `choose_retrieval` hace `time.sleep(0.3)` y devuelve un fragmento falso, como en T13.

Tests:
- `test_cuatro_a_la_vez_con_limite_4`: `RETRIEVE_MAX_CONCURRENCY=4`; 4 POST simultáneos
  con `asyncio.gather` → todos 200 y el tiempo total < 0,8 s.
- `test_en_serie_con_limite_1`: `RETRIEVE_MAX_CONCURRENCY=1`; los mismos 4 → tiempo
  total ≥ 1,2 s, y la mayor `timings_ms["queue"]` es ≥ 800.
- `test_healthz_no_espera_a_retrieve`: con `choose_retrieval` durmiendo 0,6 s, lanza un
  POST `/retrieve` y, 0,1 s después, un GET `/healthz` → `/healthz` responde en menos de
  0,3 s, medido desde que se envía.
- `test_queue_en_meta`: una sola petición → `timings_ms` tiene `queue` y es un `int` ≥ 0.
- `test_lock_de_cache_carga_una_vez`: con `threading`, 8 hilos llaman a la vez a
  `ModelCache.get_reranker("x")`, con `CrossEncoderReranker` sustituido en `core.cache`
  por una clase falsa que cuenta las instancias y duerme 0,05 s en `__init__`. Se crea
  exactamente 1 instancia. Restaura `ModelCache._reranker = None` antes y después.

## Criterios de aceptación
- `cd rag-api && /datos/lab-wt/.venv-rag/bin/python -m pytest tests -q -p no:cacheprovider`
  → todo verde (75 anteriores + 5 nuevos).
- `python3 -m pytest tutor/tests -q` (desde la raíz) sigue verde.
- El contrato de `/retrieve` no cambia: mismos códigos de estado y mismas claves de
  respuesta. Lo único nuevo es `meta.timings_ms.queue`.
- `git diff --stat tutor...HEAD` solo lista los ficheros permitidos.

## Comando de verificación
```
cd rag-api && /datos/lab-wt/.venv-rag/bin/python -m pytest tests -q -p no:cacheprovider
```

## Al terminar
`git add -A && git commit -m 'T14: /retrieve en un hilo con límite de concurrencia; hilos de torch y precarga del tokenizer'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
