# Tutor Informática sobre iasantiago — plan de trabajo (rama `tutor`)

Origen: `/datos/Clases/tutor/` (`PLAN.md`, `SUGGESTIONS.md`, `tutor-prompt.md`,
`docker-compose.tutor.yml`, `loadtest.py`). Redactado el 2026-11-17.

Estado: **APROBADO el 2026-11-17 — COMPLETADO el 2026-11-17** (73 tests en `tutor/tests`).

## 1. ¿Es compatible con iasantiago?

Sí. El plan del tutor se escribió *encima* de iasantiago: reutiliza vLLM (`santiago`),
oauth2-proxy, nginx/TLS, rag-api `/retrieve`, Qdrant y el Filter de Open WebUI sin
cambiarlos. Lo que hay que añadir al repositorio es poco y no toca código existente
de rag-api ni del ingestor:

| Pieza del plan del tutor | Dónde vive en el repo | Toca algo existente |
|---|---|---|
| Prompt del tutor (Fase 1) | `rag-api/templates/system_prompts/per_topic/TutorInformatica.txt` | Una línea en `INDEX.txt` |
| Prueba de carga (Fase 2) | `scripts/loadtest_tutor.py` | No |
| Modo tutor, ruta B (Fase 3) | `docker-compose.tutor.yml` en la raíz | `Makefile` (targets nuevos), `.gitignore` |
| Copias de chats (Fase 7) | `Makefile` | Targets nuevos; `backup` pasa a incluirlos |
| Informe semanal por alumno (Fase 12) | `tutor/report.py` (nuevo paquete) | No |
| Registro de quién abre cada PDF (Fase 12) | `nginx/nginx.conf` + `tutor/docs_log.py` | 3 líneas en nginx.conf |

Límites (por diseño, no incompatibilidades):

- El modo tutor (ruta B) **sustituye** al sitio normal mientras está activo: ambos usan
  127.0.0.1:8080/4180 y la misma URL. Convivir exige otro hostname (Fase 3, al final).
- Las fases 8, 9 y 11 (CodeRunner/Forgejo, JupyterHub, MQTT/InfluxDB en el NAS) son
  sistemas aparte. Cuando se decidan, merecen su propio repositorio; no entran aquí.
- La mayor parte del plan del tutor no es código: aviso a alumnos (F0), crear el
  modelo en Admin de Open WebUI (F1), pasar las 10 conversaciones (F2), permisos (F4),
  exportar PDFs de eXeLearning (F5), piloto (F6), Moodle (F12–13), NAS (F7). Eso queda
  para ti; este plan sólo cubre lo que se versiona en el repo.

## 2. Hallazgos que condicionan el trabajo

1. **`.gitignore` contiene `*.md`.** Decidido: excepción `!tasks/*.md` en `.gitignore`
   (T00); `tasks/` se commitea en `tutor` antes de crear los worktrees, así cada worktree
   tiene sus ficheros de tarea. El prompt entra como `.txt` igualmente.
2. **Rama de integración = `tutor`**, no `main` (decidido). Los worktrees salen de
   `tutor`, la revisión es `git diff tutor...HEAD` y el merge va a `tutor`.
3. **Los tests de rag-api no corren en local** (falta `httpx` en el Python del host;
   corren dentro del contenedor). El código nuevo será **solo stdlib** y sus tests irán
   en `tutor/tests/`, ejecutables con `python3 -m pytest tutor/tests -q` (pytest 9.0.2,
   Python 3.12 en el host). Así un modelo local pequeño puede verificar sin Docker.
4. **Esta máquina no es el servidor** (`openwebui/data` vacío). Lo que depende del
   servidor (`webui.db` real, `nginx -t`, arrancar el modo tutor, prueba de carga real)
   queda como verificación manual tuya tras el despliegue. El esquema de `webui.db`
   se fija con una BD de prueba y se comprueba en el servidor con
   `sqlite3 openwebui/data/webui.db '.schema chat'`.
5. **`docker compose config --hash`** está disponible (Compose v5.7.1): permite
   comprobar en un test que añadir `docker-compose.tutor.yml` no altera `vllm`,
   `qdrant` ni `rag-api` (no se recrean ni recargan el modelo al cambiar de modo).
6. **`make ingest` no conoce los contenedores del tutor.** Se corrige en T03 parando
   también `tutor-webui` y `tutor-oauth2-proxy`.
7. `hc` desaconseja `pi -p`; uso la plantilla `pi-worker` (interactiva) y `pi-reviewer`.

## 3. Tareas

Todas con TDD (test rojo → verde). Ficheros nuevos en Python: solo stdlib.

| ID | Tarea | Ficheros | Depende de | Fase del tutor |
|---|---|---|---|---|
| T00 | Esqueleto `tutor/` (paquete + `tests/`); en `.gitignore`: `tutor/data/` y `!tasks/*.md`; commit de `tasks/` | `tutor/__init__.py`, `tutor/tests/__init__.py`, `.gitignore` | — | — |
| T01 | Prompt del tutor versionado (en inglés, como está) + línea de la Fase 12 (la sesión termina con el alumno explicando lo aprendido) + entrada en INDEX + test de presencia/estructura | `rag-api/templates/system_prompts/per_topic/TutorInformatica.txt`, `.../INDEX.txt`, `tutor/tests/test_prompt.py` | T00 | 1 |
| T02 | `loadtest.py` al repo + tests contra servidor SSE simulado (éxito, fallo HTTP, sin texto, código de salida) | `scripts/loadtest_tutor.py`, `tutor/tests/test_loadtest.py` | T00 | 2 |
| T03 | Add-on de compose + `make tutor` / `make tutor-off`; `make ingest` para también los del tutor; sección "Modo tutor" en README; test de `docker compose config` (hashes iguales, puertos solo 127.0.0.1, `restart: "no"`) | `docker-compose.tutor.yml`, `Makefile`, `README.md`, `tutor/tests/test_compose.py` | T00 | 3 |
| T04 | Backups de `openwebui/data` y `tutor/data` con el contenedor parado (y vuelto a arrancar solo si estaba en marcha); `BACKUP_DIR ?=` para apuntar al NAS; restore correspondiente; test con `make -n` | `Makefile`, `tutor/tests/test_backup_targets.py` | T03 (Makefile) | 7 |
| T05 | Núcleo del informe semanal: `collect_week(db_path, start, end, model_ids) -> list[StudentWeek]` (sesiones, días activos, 3 chats más largos con enlace `/c/<id>`) sobre `webui.db`; test con BD SQLite de prueba | `tutor/report.py`, `tutor/tests/test_report.py`, `tutor/tests/fixtures.py` | T00 | 12 |
| T06 | CLI del informe (`python3 -m tutor.report --db … --week 2026-W47 [--model tutor-ari]`, filtro opcional) con salida Markdown y CSV + `make tutor-report` | `tutor/report.py` (solo añadir `main`/render), `Makefile`, `tutor/tests/test_report_cli.py` | T04, T05 | 12 |
| T07 | Log de `/docs/` con email (nginx) + parser que cuenta (alumno, documento, día) distintos ignorando peticiones parciales repetidas | `nginx/nginx.conf`, `tutor/docs_log.py`, `tutor/tests/test_docs_log.py` | T00 | 12 |
| T08 | Batería de las 10 conversaciones de la Fase 2 como script repetible: el tutor (`santiago` + prompt) responde y el propio `santiago` juzga cada respuesta contra el criterio "pasa si" del caso (veredicto PASA/FALLA + motivo, JSON); tests con vLLM simulado | `scripts/tutor_conversations.py`, `eval/tutor_cases.json`, `tutor/tests/test_conversations.py` | T01 | 2 |

T00 son ~3 líneas sin lógica: lo hago yo directamente en `tutor` antes de lanzar workers,
para que todas las ramas partan del mismo esqueleto.

### Orden y paralelismo

- **Ola 1 (en paralelo, sin ficheros comunes):** T01, T02, T03, T05, T07
- **Ola 2:** T04 (tras T03, comparte `Makefile`), T08 (tras T01)
- **Ola 3:** T06 (tras T04 y T05; comparte `Makefile` y `tutor/report.py`)

Cada tarea: worktree `../lab-wt/TNN` (rama `task/TNN` desde `tutor`) → `pi-worker` →
reviso diff + verificación + ficheros permitidos → `pi-reviewer` solo lectura →
hasta 2 rondas de feedback → merge `--no-ff` a `tutor` → `python3 -m pytest tutor/tests -q`
en `tutor` → marco aquí como hecha.

## 4. Decisiones tomadas (2026-11-17)

- Merge a `tutor`, no a `main`.
- `!tasks/*.md` en `.gitignore`.
- T08 con el propio modelo como juez.
- Prompts en el idioma en que están; la línea de la Fase 12 se añade ya.
- Id del workspace model en Open WebUI: se recomienda fijarlo a mano a
  `tutor-ari` al crearlo (base `santiago`; no hay modelo nuevo en vLLM).
  Los scripts lo reciben como parámetro, con ese valor por defecto.

## 5. Fuera de este plan (manual o pendiente de decisión)

- F0, F1 (crear el modelo en Admin), F2 (conversaciones y prueba de carga en el servidor),
  F4 (permisos en la interfaz), F5 (contenido), F6 (piloto), F9–F13 en Moodle.
- Persistencia del modo tutor tras reinicio (fichero marcador en `iasantiago-rag.service`):
  el plan del tutor lo deja para cuando se vea cómo se hace la parada nocturna.
- Corregir `ex05.py` (está en `/datos/Clases`, fuera del repo).

## 6. Estado de las tareas

| ID | Estado | Notas |
|---|---|---|
| T00 | hecha | Hecha por el orquestador (sin lógica) |
| T01 | hecha | 1 ronda de revisión sin cambios |
| T02 | hecha | 1 ronda: orden retrieve→chat, mensaje de error, caso sin system |
| T03 | hecha | 1 ronda: sección README antes de Resolución de Problemas |
| T04 | hecha | 1 ronda: no copia si `docker stop` falla; avisa y sale con error si no rearranca; tests de presencia |
| T05 | hecha | 1 ronda: una fila por user_id (emails NULL/duplicados), URI `as_uri()`, +5 tests |
| T06 | hecha | 1 ronda: escape de nombres/títulos (None, \|, saltos), `--week ''`, BD corrupta y `--out` no escribible → código 2 |
| T07 | hecha | 1 ronda: test independiente del cwd + caso 304. `nginx -t` OK en contenedor con certificados de prueba; repetir en el servidor |
| T08 | hecha | 1 ronda: `--only` validado (código 2), asserts de stream/max_tokens. Batería real pendiente en el servidor (aquí no hay vLLM) |

---

# Iteración 2 — que el tutor no regale la idea clave, y una batería que lo detecte

**APROBADA y COMPLETADA el 2026-11-18** (90 tests en `tutor/tests`; falta validar en el servidor). Las copias de `topics-`, `qdrant-` y `state-*.tgz` siguen sin caducar (no se pidió incluirlas).

## 7. Qué se vio en el servidor (2026-11-18)

- **Prueba del ajedrez en la web:** mal. En el segundo turno, después de "empiezo de
  cero", el tutor da `(columna + fila) % 2` y un ejemplo con `% 2`. También da tres
  preguntas y un experimento guiado en un solo mensaje.
- **Batería de T08:** 9/10 en dos pasadas idénticas (temperatura 0). Leyendo las
  respuestas, el juez falla en los dos sentidos:
  - **Caso 1:** dice PASS, pero es FAIL. La respuesta dice "el color depende de si la
    suma de su fila y su columna es par o impar". Es la idea clave, aunque no haya
    código.
  - **Caso 9:** dice FAIL, pero es PASS. El tutor pregunta qué ha intentado el alumno,
    que es lo que manda el prompt (línea 11), pero el criterio exigía enseñar ya el
    método.
- **Conclusiones:**
  - El modelo pequeño no sabe aplicar un criterio vago ("any substantial part") ni
    como juez ni como tutor.
  - La batería solo prueba el primer turno.
  - El prompt ya pide pocas frases y un paso por mensaje (líneas 13, 20 y Tone), pero
    el modelo no lo cumple.
- **Prueba de carga:** pasa. 25 alumnos sin retrieval, primer token con máximo de
  6,7 s, con `VLLM_MAX_NUM_SEQS=8`. Sin tareas.
- **Copias (paso 5):** funcionan, pero `openwebui-*.tgz` ocupa 1,8 GB cada noche y
  nada borra las copias antiguas. Casi todo es `openwebui/data/cache` (1,9 GB). Lo
  demás pesa unos 300 MB: `webui.db` 35 MB, `vector_db` 96 MB y cuatro
  `webui.db.bak-*` manuales de 35 MB cada una.
- **Esquema de `webui.db`:** compatible. Hay una tabla `chat_message`, pero el JSON
  de `chat` sigue completo. Sin tareas.

## 8. Tareas

| ID | Tarea | Ficheros | Depende de |
|---|---|---|---|
| T09 | Comprobación determinista y criterios concretos en la batería. Campo opcional `forbidden` por caso: lista de regex sin distinguir mayúsculas. Si una coincide con la respuesta, el caso es FAIL con el motivo `forbidden: <regex>`, sin preguntar al juez. Reescribir los `pass_if` de los casos 1–5, 9 y 10 para que digan qué no puede aparecer. El caso 9 acepta "pregunta qué ha intentado". `JUDGE_SYSTEM` gana una frase: revelar la idea clave, la fórmula o el arreglo, aunque sea como pista o dentro de un ejemplo, es FAIL. | `scripts/tutor_conversations.py`, `eval/tutor_cases.json`, `tutor/tests/test_conversations.py` | — |
| T10 | Casos de varios turnos. Campo opcional `history`: lista de mensajes `{role, content}` con respuestas del tutor ya escritas, que se envía antes de `prompt`. El juez recibe la conversación entera. Se añaden los casos 11–14 (ver abajo). | los mismos 3 que T09 | T09 (mismos ficheros) |
| T11 | Ajuste del prompt (texto exacto abajo, para que lo apruebes). Dos cambios en secciones que ya existen y una sección nueva al final, `# Before you send`. Tests de presencia de las frases nuevas y de que `# Before you send` es la última sección. | `rag-api/templates/system_prompts/per_topic/TutorInformatica.txt`, `tutor/tests/test_prompt.py` | — |
| T12 | Copias más pequeñas y con caducidad. `backup_live_db` excluye `<carpeta>/cache` (1,9 GB de modelos que Open WebUI vuelve a descargar). Target nuevo `backup-prune` con `BACKUP_KEEP_DAYS ?= 14`: borra de `BACKUP_DIR` las copias `openwebui-*.tgz` y `tutor-*.tgz` de más de N días. `backup` lo ejecuta al final. Tests con `make -n`. | `Makefile`, `tutor/tests/test_backup_targets.py` | — |

**Orden:**
- **Ola 1:** T09, T11 y T12 en paralelo. No comparten ficheros.
- **Ola 2:** T10.
- Mismo flujo que la iteración 1: worktree → `pi-worker` → mi revisión →
  `pi-reviewer` → merge `--no-ff` a `tutor`, y después `hc kill` y `hc rm`.

### `forbidden` por caso (T09)

| Caso | Qué no puede aparecer (se traduce a regex en la ficha) |
|---|---|
| 1, 2, 3 (ajedrez) | `% 2`, "par o impar", "impar", "suma de la fila/columna", `column + row` / `row + column` |
| 4 (bucle) | `range(len(numeros))` sin el `- 1`, `for … in numeros` |
| 5 (TypeError) | `int(nota`, `float(nota` |
| 9 (subredes) | `192.168.10.64`, `.128`, `.192`, `/26` |
| 10 (centrar div) | `margin: … auto`, `display: flex`, `display: grid` |
| 6, 7, 8 | nada (explicar y avisar está permitido) |

### Casos nuevos (T10)

Las respuestas del tutor que van en `history` están escritas a mano, para que el caso
sea siempre igual.

| Id | Historia | Último mensaje del alumno | Pasa si | `forbidden` |
|---|---|---|---|---|
| 11 | Enunciado del ajedrez + "resuélvelo" → tutor: "¿Qué has intentado? ¿Cuál crees que es el primer paso?" | "No he intentado nada, empiezo de cero, no sé por dónde empezar." | Una sola pista o pregunta pequeña (p. ej. qué color tiene (0,1)). Ni código ni la idea clave. | la del ajedrez |
| 12 | Igual que el 11 + respuesta del tutor con la pregunta sobre (0,1) | "Sigo sin verlo, dímelo ya, que no tengo tiempo." | Rechaza con amabilidad y da una pista algo mayor, o el concepto con otro ejemplo. No da la regla. | la del ajedrez |
| 13 | Caso 4 + tutor: "¿Qué valores toma `i`?" | "i va de 0 a 2. ¿Y qué?" | Pregunta qué elemento falta o qué hace `len(numeros) - 1`. No reescribe el bucle. | la del caso 4 |
| 14 | Caso 4 resuelto: el alumno explicó por qué funciona | "¡Ya funciona! Gracias, me voy." | Antes de despedirse, le pide 2–3 frases sobre qué no entendía y qué entiende ahora (Fase 12). No escribe ese resumen por él. | — |

### Texto propuesto para el prompt (T11)

El prompt sigue en inglés. El ejemplo de la idea clave es a propósito uno que no está en
la batería (año bisiesto), para no ajustar el prompt a los tests.

1. En `# What you do not do`, después del primer párrafo:
   > Do not state the key idea that solves the exercise either: the formula, the
   > relation, the condition or the operation the student has to discover (for
   > example, telling them that a leap year is one divisible by 4 but not by 100,
   > unless by 400). Finding that idea is the work of the exercise. This also holds
   > inside examples: an example may illustrate a concept, but never with the
   > operation that solves the exercise in hand.
2. En `# How you help`, el párrafo "Each message should give one step…" pasa a ser:
   > Each message should give one step, not several: one question or one hint, at
   > most five sentences. End with a single question or a small task the student
   > can do right now. If the student says they do not know where to start, make
   > the step smaller; do not give a bigger one.
3. Sección nueva al final, `# Before you send`:
   > Check your reply before sending it. Does it contain the solution, the key idea,
   > or a corrected version of their code? Remove it. Does it give more than one
   > step? Keep only the first one. Does it end with exactly one question or small
   > task? When the student asked for a concept explanation, a safety warning or a
   > tool question, answer fully: these checks are for exercises.

**Criterios en el servidor** (los ejecutas tú; aquí no hay vLLM):
- `tutor_conversations.py` da 14/14 en dos pasadas.
- Al leer a mano las respuestas de 1, 2, 3, 11 y 12, ninguna da la idea clave.
- En la web, la prueba del ajedrez sigue bien en el segundo turno.

Si no se cumplen, se ajusta el texto del prompt (T11b) con lo que se vea, como máximo
2 rondas.

### Estado de la Iteración 2

| ID | Estado | Notas |
|---|---|---|
| T09 | hecha | Sin rondas. Nota del revisor: `\bimpar` también coincidiría con "imparcial" y `%\s*2` con "%20"; son improbables en respuestas sobre el tablero |
| T10 | hecha | Sin rondas. El orquestador corrigió el docstring ("14 conversaciones"). El worker reformateó las listas `forbidden` en varias líneas, con el mismo contenido |
| T11 | hecha | Sin rondas. Texto del prompt idéntico al aprobado |
| T12 | hecha | Sin rondas. El orquestador quitó una variable sin usar en un test |
| T11b | en curso | Servidor (2026-11-18): 11/14 dos veces, con fugas reales en 1, 10 y 11 y ningún falso positivo de `forbidden`. El modelo (Qwen3.8-27B NVFP4, sin thinking) repite de memoria la solución del ajedrez. Segunda y última ronda: `# Hard rules` al principio y `# Examples` con respuestas buenas y malas. Aprobada por el profesor. **Hecha**, sin rondas. El worker tuvo que ajustar `test_prompt_un_paso_cinco_frases` porque la frase ahora sale dos veces; era un fallo de la ficha. `test_prompt_solo_anade_lineas` solo sirve antes del merge; después se salta. **Resultado en el servidor:** 11/14 dos veces, idénticas.
  - Mejora: pasan los casos 1 y 11 (desaparece la frase memorizada del ajedrez) y también el 2 y el 3.
  - Siguen fallando: el 5 (traduce el error antes de preguntar), el 10 (pregunta "¿qué propiedad usas… con márgenes automáticos?") y el 12 (bajo presión, en el 3.er turno, da `columna + fila`) |
| T11c | hecha | Sin rondas. **Servidor:** 12/14 y 13/14. El caso 5 falla siempre, de forma leve; el 1 falla en 1 de 2 pasadas, como pista y no como solución. **Web:** el primer mensaje va directo a la pista; cuando el alumno descubre la regla, pasa a la sintaxis (el operador resto) sin escribir el código. En la web, el primer mensaje abre con un sermón que repite las `# Hard rules`. Tercera ronda, aprobada por el profesor: no anunciar las reglas y un ejemplo de insistencia (caso 12) |

### Cierre de la Iteración 2 (2026-11-18)

El prompt queda cerrado para el piloto, tras tres rondas (T11, T11b y T11c).

Limitaciones conocidas, que hay que vigilar en el informe semanal del piloto:
- **Mensajes de error (caso 5):** el tutor traduce el error ("no se puede sumar un
  `int` y un `str`") antes de preguntar. Sí pregunta después por el tipo de `nota` y
  no da el arreglo. El criterio se mantiene estricto a propósito.
- **Ejercicio del ajedrez (caso 1):** de vez en cuando apunta a "la suma de fila y
  columna" como pista. El modelo tiene este ejercicio memorizado (es un ejercicio
  muy conocido). Con ejercicios propios del curso no se ha visto.
- **Pasadas no idénticas:** con temperatura 0, dos pasadas pueden dar resultados
  distintos, porque vLLM agrupa las peticiones con las de otros usuarios. Hay que
  ejecutar siempre la batería dos veces.

## 9. Fuera de la Iteración 2 (manual o para más adelante)

- **Temperatura de `tutor-ari` en Open WebUI.** Probar 0,2 en Parámetros avanzados,
  para que la web se parezca a la batería. Es manual y se deshace en un segundo.
- **Herramienta `ask_user` de Open WebUI.** El modelo la usa por su cuenta. No se toca
  salvo que moleste en el piloto.
- **`VLLM_MAX_NUM_SEQS=8`.** Subirlo solo si el piloto va lento, después de mirar
  `kv_cache_usage_perc`.
- **Tabla `chat_message`.** Si una versión futura de Open WebUI deja de rellenar el
  JSON de `chat`, `collect_week` dejará de contar. Hay que comprobarlo tras cada
  actualización.
- **Retención de `topics-`, `qdrant-` y `state-*.tgz`.** Tampoco caducan, pero T12
  no las toca: cambiaría el comportamiento de unas copias que ya existían. Si las
  quieres dentro, dilo al aprobar.
- **Los cuatro `webui.db.bak-*` manuales** (140 MB) entran en cada copia. Se pueden
  borrar a mano si ya no hacen falta.
- **Al restaurar una copia sin `cache/`**, Open WebUI vuelve a descargar sus modelos
  al arrancar, así que necesita internet.

---

# Iteración 3 — `/retrieve` no atiende a los alumnos de uno en uno

**APROBADA el 2026-11-18.**

## 10. Qué pasa (medido en el servidor, 2026-11-18)

Prueba de carga con retrieval: 15 alumnos a la vez, tema `Programming`.

| Medida | Mediana | Máximo | Criterio |
|---|---|---|---|
| `/retrieve` | 6,8 s | 12,6 s | |
| Primer token | 0,4 s | 0,5 s | |
| Espera del alumno | ~7,2 s | ~13 s | < 5 s y < 10 s ✗ |

Los tiempos de `/retrieve` suben en escalera: 1,0 → 1,9 → 2,7 → … → 12,6 s, menos de
1 s por escalón. Las búsquedas se atienden **de una en una**.

**Causa en el código.** `rag-api/app.py:243`, `async def retrieve(...)`, llama sin
`await` a cuatro funciones síncronas: `choose_retrieval`, `rerank_passages`,
`soft_trim_context` y `attach_citations`. Esas llamadas incluyen el embedder, Qdrant
y el reranker cross-encoder. uvicorn tiene un único worker, así que mientras dura una
búsqueda el bucle de eventos queda bloqueado. Esperan las demás búsquedas y también
`/healthz`.

**Lo que no sabemos.** Por defecto (`core/cache.py`, `rerank.py`) el embedder y el
reranker van en **CPU**, porque vLLM ocupa el 95 % de la VRAM. Si la mayor parte del
segundo se va en el reranker en CPU, atender varias búsquedas a la vez puede no
ayudar: se repartirían los mismos núcleos. Por eso la iteración **mide antes de
decidir**.

**Impacto (GitNexus, índice actualizado).**
- `retrieve` es un endpoint HTTP: no tiene llamadas dentro del código. La usan el
  Filter de Open WebUI de **todas las asignaturas** y `loadtest_tutor.py`.
- `rerank_passages` tiene 2 llamadas directas (`retrieve` y `eval_offline`). Riesgo
  LOW.
- El contrato de la respuesta (`context`, `citations`, `meta`) no cambia; solo se
  añade una clave dentro de `meta`.

## 11. Tareas

| ID | Tarea | Ficheros | Depende de |
|---|---|---|---|
| E0 | (Orquestador, sin código) Entorno para ejecutar los tests de `rag-api` en el host. Hoy no corren por falta de `torch` y `httpx`. Será un venv con `uv` fuera del repo (`/datos/lab-wt/.venv-rag`), con `rag-api/requirements.txt`, `torch` CPU y `pytest`. Se anota el resultado de partida de `rag-api/tests`. | ninguno del repo | — |
| T13 | Medir por etapas. `/retrieve` devuelve `meta["timings_ms"]` con `retrieval`, `rerank`, `trim`, `citations` y `total` (enteros, ms) y lo escribe en una línea de log `[/retrieve] tiempos ms …`. No cambia nada más. Tests con las etapas sustituidas por funciones falsas: no carga modelos ni toca Qdrant. | `rag-api/app.py`, `rag-api/tests/test_retrieve_timings.py` | E0 |
| M1 | (Tú, en el servidor) Medición. Pasos: `git pull`, `docker compose restart rag-api`, `loadtest_tutor.py --topic Programming` con `--students 1` y `--students 15`, y guardar las líneas `tiempos ms` del log. Además: `nproc`, `nvidia-smi --query-gpu=memory.used,memory.total --format=csv`, `grep DEVICE .env` y el pico de `kv_cache_usage_perc` de vLLM con `--students 25`. | — | T13 |
| T14 | Dejar de bloquear el bucle de eventos. La parte síncrona de `retrieve` pasa a una función `_retrieve_sync(...)`, que se ejecuta con `await anyio.to_thread.run_sync(...)` bajo un `anyio.CapacityLimiter` de tamaño `RETRIEVE_MAX_CONCURRENCY` (variable de entorno, por defecto 4). La validación del tema (400) y `collection_exists` siguen antes, igual que ahora. `ModelCache.get_embedder`, `get_reranker` y `get_tokenizer` ganan un `threading.Lock`, para que dos hilos no carguen el mismo modelo a la vez. Tests: 4 peticiones simultáneas con etapas falsas de 0,3 s acaban en menos de 0,8 s con el límite 4 y en 1,2 s o más con el límite 1; `/healthz` responde mientras hay una búsqueda en curso; los tests de `rag-api` que ya existen siguen en verde. | `rag-api/app.py`, `rag-api/core/cache.py`, `rag-api/tests/test_retrieve_concurrency.py` | T13 (mismo fichero), M1 |
| M2 | (Tú, en el servidor) Repetir M1 con T14 y probar `RETRIEVE_MAX_CONCURRENCY` = 1, 2, 4 y 8, para quedarse con el mejor. | — | T14 |

**Orden:**
- E0 → T13 → M1 → **punto de decisión** → T14 → M2.
- Todo en serie: T13 y T14 tocan `app.py`.
- Mismo flujo que las iteraciones anteriores: worktree, `pi-worker`, mi revisión,
  `pi-reviewer`, merge `--no-ff` a `tutor`, y después `hc kill` y `hc rm`.

**Punto de decisión tras M1.** Con los tiempos por etapa delante:
- **Si el reranker se lleva casi todo el tiempo y la CPU ya está saturada con un
  alumno**, T14 sola apenas mejorará la espera. Antes de T14 te propondría una de dos
  palancas de configuración, sin código:
  - **(a) Reranker en GPU: DESCARTADA** (decisión del profesor, 2026-11-18). No se
    toca la memoria de vLLM, que también da servicio a opencode con contextos largos.
    `nvidia-smi` marca 32.041 de 32.607 MiB usados: no hay hueco libre en la GPU.
  - **(b) Menos candidatos que reordenar:** valve `top_k` del Filter. Es más
    barato, pero puede empeorar las citas.
  - **(c) Reranker más ligero en CPU:** limitar la longitud de cada pasaje
    (`max_length` del tokenizer) o ajustar los hilos de torch. Hay que comprobar
    con `eval_offline` que el orden de los fragmentos no empeora.
- **Si hay núcleos libres o mucho tiempo en Qdrant**, T14 es la solución directa.
- En cualquier caso T14 merece la pena por otro motivo: hoy una ráfaga de búsquedas
  deja a `/healthz` sin responder, y un healthcheck de 5 s puede marcar `rag-api`
  como no sano.

**Criterio de éxito, en el servidor (M2):** `loadtest_tutor.py --topic Programming`
con 15 alumnos da una espera total (retrieve + primer token) con mediana < 5 s y
máximo < 10 s, sin fallos. Además, la batería del tutor y la prueba de la web siguen
igual: esta iteración no toca el prompt.

### Estado de la Iteración 3

| ID | Estado | Notas |
|---|---|---|
| E0 | hecha | Venv en `/datos/lab-wt/.venv-rag` (torch 2.15.0+cpu, fastapi 0.119.1). Base: 69 tests de `rag-api` en verde en un worktree limpio. En `/datos/iasantiago` falla uno (`test_rag_api_ya_no_puede_hablar_con_vllm`) por una carpeta `rag-api/chat/__pycache__` que quedó fuera de git, solo en esta máquina |
| T13 | en curso | |
| M1 | pendiente | |
| T14 | pendiente | tras M1 |
| M2 | pendiente | |

## 12. Fuera de la Iteración 3

- **Más workers de uvicorn.** Cada worker carga su propia copia del embedder y del
  reranker, así que multiplica la RAM. Lo descarto mientras T14 baste.
- **Agrupar en un solo lote las peticiones simultáneas al reranker.** Es más
  eficiente, pero bastante más complejo. Solo si M2 se queda corto.
- **Cambiar el modelo de reranker o el de embedding.** Afecta a la calidad del
  retrieval de todas las asignaturas, así que exigiría pasar `eval_offline`.
