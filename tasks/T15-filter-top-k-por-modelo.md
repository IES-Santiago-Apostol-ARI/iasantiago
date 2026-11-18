# T15 — `top_k` por modelo en el Filter de Open WebUI

## Objetivo
El reranker se lleva el 90 % del tiempo de cada búsqueda y tarda en proporción al
número de fragmentos. El tutor reordenará 8 fragmentos en lugar de 18 sin cambiar las
demás asignaturas. Para eso, el Filter acepta un `top_k` distinto por modelo. Además,
`loadtest_tutor.py` gana `--top-k` para poder medirlo.

## Ficheros que puedes tocar (SOLO estos)
- `openwebui/functions/rag_retrieval_filter.py`
- `openwebui/tests/test_filter_top_k.py` (nuevo)
- `scripts/loadtest_tutor.py`
- `tutor/tests/test_loadtest.py`

## Cambios en `openwebui/functions/rag_retrieval_filter.py`
1. En la cabecera, `version: 0.2.0` pasa a `version: 0.3.0`.
2. En `Valves`, justo DESPUÉS del campo `top_k`, añade:
   ```python
   top_k_map: str = Field(
       default="{}",
       description=(
           'JSON {"<model_id o nombre>": N}: profundidad por modelo, con prioridad '
           'sobre top_k. Ej: {"tutor-ari": 8}'
       ),
   )
   ```
3. Método nuevo, junto a `_resolve_topic`:
   ```python
   def _resolve_top_k(self, model: Optional[dict]) -> int:
       """top_k_map[id] -> top_k_map[name] -> valves.top_k (si > 0) -> 0 (sin override).
       JSON inválido o que no sea un objeto = {}. Valores que no sean enteros > 0 se ignoran."""
   ```
   El id y el nombre se obtienen como en `_resolve_topic`: `model.get("id")` y
   `model.get("name") or (model.get("info") or {}).get("name")`. Con `model=None` no
   falla. Un valor como `"8"` o `8.0` cuenta si `int(valor) > 0`; un `bool` NO cuenta.
4. En `inlet`, el bloque
   ```python
   if self.valves.top_k > 0:
       payload["top_k"] = self.valves.top_k
   ```
   pasa a ser
   ```python
   top_k = self._resolve_top_k(__model__)
   if top_k > 0:
       payload["top_k"] = top_k
   ```
No cambies nada más del Filter.

## Tests del Filter (`openwebui/tests/test_filter_top_k.py`)
Se ejecutan con el `python3` del sistema, que tiene pydantic pero no `aiohttp`. Antes de
importar el Filter, mete en `sys.modules["aiohttp"]` un módulo falso (`types.ModuleType`)
con:
- `ClientTimeout(total=...)`, que no hace nada;
- `ClientSession(timeout=...)`, que funciona como contexto asíncrono y cuyo
  `post(url, json=..., headers=...)` guarda `json` en una lista y devuelve un contexto
  asíncrono con `status = 200` y un `async def json()` que devuelve
  `{"context": "ctx", "meta": {"num_chunks": 1}}`.

Importa el Filter con `importlib.util.spec_from_file_location`, usando la ruta absoluta
desde `Path(__file__).resolve().parents[2]`. Ejecuta
`asyncio.run(f.inlet({"messages": [{"role": "user", "content": "hola"}]}, __model__=modelo))`
y mira el último `json` guardado.

Tests:
- `test_top_k_por_id`: `top_k_map='{"tutor-ari": 8}'`, modelo `{"id": "tutor-ari", "name": "Tutor Informática"}` → `payload["top_k"] == 8`.
- `test_top_k_por_nombre`: `top_k_map='{"Tutor Informática": 6}'` → 6.
- `test_otro_modelo_sin_top_k`: mismo mapa que el primero, modelo `{"id": "quimica", "name": "Química"}` → `"top_k" not in payload`.
- `test_reserva_global`: `top_k=12`, mapa sin ese modelo → 12; y con el modelo en el mapa (8) gana el mapa.
- `test_mapa_invalido_no_rompe`: `top_k_map="{oops"` y también `top_k_map="[1,2]"` → sin `top_k` y sin excepción.
- `test_valores_no_validos_se_ignoran`: valores `0`, `-3`, `"abc"`, `true` y `null` en el mapa → se usa la reserva (`top_k=5` → 5).
- `test_resolve_top_k_sin_modelo`: `_resolve_top_k(None)` con `top_k=0` → 0.
- `test_version`: el fichero contiene la línea `version: 0.3.0`.

## Cambios en `scripts/loadtest_tutor.py`
- Argumento nuevo `--top-k` (`type=int`, por defecto `None`), con
  `help="top_k to send to /retrieve (only with --topic)"`.
- En `student`, el cuerpo de `/retrieve` pasa a ser
  `{"query": question, "topic": args.topic}`, más `"top_k": args.top_k` solo si
  `args.top_k` no es `None`.
- Añade al docstring del principio una línea de ejemplo con `--top-k 8`.

## Tests en `tutor/tests/test_loadtest.py` (añadir; no cambies los existentes)
- `test_top_k_se_envia_a_retrieve`: con `--topic Programming --top-k 8`, el cuerpo del
  `/retrieve` recibido tiene `top_k == 8`.
- `test_sin_top_k_no_se_envia`: con `--topic Programming` sin `--top-k` →
  `"top_k" not in body`.

Copia de `test_retrieve_antes_del_chat` la forma de lanzar `main` y de leer
`server.requests`.

## Criterios de aceptación
- `python3 -m pytest openwebui/tests -q` → 8 passed.
- `python3 -m pytest tutor/tests -q` → todo verde (con 2 tests más).
- `git diff --stat tutor...HEAD` solo lista los 4 ficheros permitidos.
- `git diff tutor...HEAD -- openwebui/functions/` solo toca la versión, la valve nueva,
  el método nuevo y las 3 líneas de `inlet`.

## Comando de verificación
```
python3 -m pytest openwebui/tests tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T15: top_k por modelo en el Filter y --top-k en el loadtest'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
