# T13 — `/retrieve` mide cuánto tarda cada etapa

## Objetivo
Saber en qué se va el segundo que tarda cada búsqueda: recuperar, reordenar
(reranker), recortar o citar. `/retrieve` devuelve los tiempos en `meta["timings_ms"]`
y los escribe en una línea de log. No cambia nada más del comportamiento.

## Ficheros que puedes tocar (SOLO estos)
- `rag-api/app.py` (solo la función `retrieve` y, si hace falta, `import time` arriba)
- `rag-api/tests/test_retrieve_timings.py` (nuevo)

## Entorno de tests (ya preparado; NO instales nada)
Los tests de `rag-api` necesitan `torch`, y el `python3` del sistema no lo tiene. Usa
siempre el venv ya preparado, ejecutando desde la carpeta `rag-api` de tu worktree:
```
cd rag-api && /datos/lab-wt/.venv-rag/bin/python -m pytest tests -q -p no:cacheprovider
```
Antes de tu cambio deben pasar los 69 tests que ya existen.

## Cambios exactos en `retrieve` (`rag-api/app.py`)
1. Si no está, añade `import time` junto a los demás `import` del principio del fichero.
2. Como primera línea del cuerpo de `retrieve` (antes de calcular `user_ref`):
   `t_start = time.perf_counter()`.
3. Mide con `time.perf_counter()` cada una de estas llamadas, que ya existen. No
   cambies sus argumentos ni el orden:
   - `choose_retrieval(...)` → `retrieval`
   - `rerank_passages(...)` → `rerank` (0 si no se ejecuta: lista vacía o `req.rerank` falso)
   - `soft_trim_context(...)` → `trim` (0 si no se ejecuta: lista vacía)
   - `attach_citations(...)` → `citations`
4. Justo antes del `return` final (después de `telemetry_log`), calcula
   `total` = desde `t_start` hasta ese punto. Construye
   ```python
   timings_ms = {
       "retrieval": ..., "rerank": ..., "trim": ..., "citations": ..., "total": ...,
   }
   ```
   Cada valor es `int(round(segundos * 1000))`.
5. Escribe una línea de log, en este formato exacto:
   ```python
   logger.info(
       "[/retrieve] tiempos ms: retrieval=%d rerank=%d trim=%d citations=%d total=%d topic=%s chunks=%d",
       timings_ms["retrieval"], timings_ms["rerank"], timings_ms["trim"],
       timings_ms["citations"], timings_ms["total"], req.topic, len(retrieved),
   )
   ```
6. Añade `"timings_ms": timings_ms` como ÚLTIMA clave del diccionario `meta` del
   `return` final. Las demás claves no cambian.
7. Las dos salidas tempranas (400 por tema desconocido y 200 vacío por colección
   inexistente) NO cambian y NO llevan `timings_ms`.

## Tests (`rag-api/tests/test_retrieve_timings.py`)
Sigue el estilo de `tests/test_retrieve_topic_validation.py`:
- `TestClient(app_module.app)` SIN `with`, para que no se carguen modelos.
- La cabecera `AUTH`.
- Una fixture que fija `TOPIC_LABELS` a `["Latin"]`.
- Parches con `monkeypatch.setattr(app_module, ...)` para `collection_exists`
  (→ True), `telemetry_log` (→ None) y `_build_citations` (→ []).

Las etapas falsas duermen con `time.sleep` y devuelven datos fijos:
- `choose_retrieval`: duerme 0,03 s y devuelve
  `([{"text": "t", "file_path": "f.pdf", "page": 1, "chunk_id": "c1"}], {"mode": "hybrid", "original_language": "es", "final_topk": 5})`.
- `rerank_passages`: duerme 0,03 s y devuelve la lista que recibe.
- `soft_trim_context`: devuelve la lista que recibe.
- `attach_citations`: devuelve `("ctx", [])`.

Tests:
- `test_meta_lleva_los_tiempos`: 200; `meta["timings_ms"]` tiene exactamente las claves
  `retrieval, rerank, trim, citations, total`; todos son `int` y ≥ 0;
  `retrieval >= 25`, `rerank >= 25`; y `total >= retrieval + rerank + trim + citations - 4`.
- `test_sin_rerank_cuenta_cero`: con `"rerank": false` en el cuerpo, `timings_ms["rerank"] == 0`
  y `rerank_passages` no se llamó (usa una lista para registrar llamadas).
- `test_sin_resultados_rerank_y_trim_cero`: `choose_retrieval` devuelve `([], {...})` →
  `rerank == 0` y `trim == 0`, y la clave `timings_ms` sigue estando.
- `test_linea_de_log`: con `caplog.at_level(logging.INFO)`, algún mensaje contiene
  `[/retrieve] tiempos ms: retrieval=` y `total=` y `topic=Latin`.
- `test_el_resto_de_meta_no_cambia`: `meta` conserva `topic, mode, generative, num_chunks,
  final_topk, original_language, context_token_limit` con los valores de siempre
  (`num_chunks == 1`, `mode == "hybrid"`), y `timings_ms` es la última clave.
- `test_coleccion_inexistente_sin_tiempos`: `collection_exists` → False ⇒ 200 y
  `"timings_ms" not in meta`.

## Criterios de aceptación
- `cd rag-api && /datos/lab-wt/.venv-rag/bin/python -m pytest tests -q -p no:cacheprovider`
  → todo verde (69 anteriores + 6 nuevos).
- `python3 -m pytest tutor/tests -q` (desde la raíz) sigue verde.
- `git diff tutor...HEAD -- rag-api/app.py` solo toca `import time` y el cuerpo de `retrieve`.
- `git diff --stat tutor...HEAD` solo lista los 2 ficheros permitidos.

## Comando de verificación
```
cd rag-api && /datos/lab-wt/.venv-rag/bin/python -m pytest tests -q -p no:cacheprovider
```

## Al terminar
`git add -A && git commit -m 'T13: /retrieve mide el tiempo de cada etapa'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
