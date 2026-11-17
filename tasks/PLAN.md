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
