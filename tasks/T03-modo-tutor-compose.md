# T03 — Modo tutor: add-on de compose y targets del Makefile

## Objetivo
Versionar `docker-compose.tutor.yml` en la raíz del repo, añadir `make tutor` y
`make tutor-off`, y hacer que `make ingest` y `make web` paren también los
contenedores del tutor (si no, chocan por los puertos 8080/4180).

## Ficheros que puedes tocar (SOLO estos)
- `docker-compose.tutor.yml` (nuevo)
- `Makefile`
- `README.md` (añadir una sección; no toques nada más del README)
- `tutor/tests/test_compose.py` (nuevo)

## Pasos (TDD)
1. Escribe primero `tutor/tests/test_compose.py` (abajo). Ejecútalo: FALLA (rojo).
2. `cp /datos/Clases/tutor/docker-compose.tutor.yml docker-compose.tutor.yml`
3. En la cabecera de comentarios de `docker-compose.tutor.yml`, cambia SOLO la frase
   `Copy it to /opt/iasantiago-rag/ and always load it together with the main file`
   por `It lives next to docker-compose.yml; always load it together with the main file`.
   Añade al final de la cabecera: `# Use "make tutor" / "make tutor-off" (see README, "Modo tutor").`
   No cambies servicios, puertos, variables ni volúmenes.
4. En el `Makefile`:
   a. Después de la línea `DATE := ...` añade:
      ```make
      # Modo tutor (docker-compose.tutor.yml): segundo Open WebUI que sustituye al normal.
      TUTOR := COMPOSE_FILE=docker-compose.yml:docker-compose.tutor.yml
      ```
   b. Añade `tutor tutor-off` a la lista `.PHONY` (en la última línea de la lista, junto a `ingest web`).
   c. En el target `ingest`, como PRIMERA línea de comandos (antes del `@echo`), añade:
      `$(TUTOR) docker compose stop tutor-oauth2-proxy tutor-webui || true`
   d. En el target `web`, como PRIMERA línea de comandos (antes del `@echo`), añade la misma línea.
   e. Justo después del target `web` añade:
      ```make
      tutor:
      	@echo "Parando el sitio normal y lanzando el modo tutor..."
      	docker compose stop ingestor oauth2-proxy openwebui || true
      	$(TUTOR) docker compose up -d qdrant vllm rag-api tutor-webui tutor-oauth2-proxy

      tutor-off:
      	@echo "Parando el modo tutor y volviendo al sitio normal..."
      	$(MAKE) web
      ```
      (Las recetas van con TABULADOR, no espacios. `tutor-off` no necesita parar el
      tutor por sí mismo porque `web` ya lo hace tras el paso d.)
5. En `README.md`, añade al final del documento una sección nueva `## Modo tutor`
   en español, de 10–20 líneas, que diga:
   - qué es: un segundo Open WebUI (`tutor-webui` + `tutor-oauth2-proxy`) con BD
     propia en `tutor/data/`, que sustituye al sitio normal mientras está activo
     (mismos puertos 127.0.0.1:8080/4180, misma URL, mismo login de Google);
   - `make tutor` lo enciende y `make tutor-off` vuelve al sitio normal;
     `vllm`, `qdrant` y `rag-api` no se recrean al cambiar de modo;
   - `make ingest` y `make web` paran el modo tutor;
   - los contenedores del tutor tienen `restart: "no"`: tras reiniciar el servidor
     vuelve el sitio normal y hay que repetir `make tutor`;
   - cómo crear la BD la primera vez: copia de `openwebui/data` con el sitio parado
     (`sudo cp -a openwebui/data tutor/data`) o vacía (`mkdir -p tutor/data`; el
     primero que entra es administrador);
   - el workspace model del tutor se crea con id `tutor-ari`, base `santiago`, y el
     prompt de `rag-api/templates/system_prompts/per_topic/TutorInformatica.txt`.
6. Ejecuta los tests: PASAN (verde).

## Tests que debe contener `tutor/tests/test_compose.py`
Solo stdlib + pytest. `ROOT = Path(__file__).resolve().parents[2]`.
Si `shutil.which("docker")` es None, los tests que usan docker hacen `pytest.skip`.

Fixture `compose_dir(tmp_path)`: copia `ROOT/docker-compose.yml` y
`ROOT/docker-compose.tutor.yml` a `tmp_path`, crea un `.env` VACÍO en `tmp_path`
(lo exige `env_file: .env` de rag-api) y un `test.env` con una línea `NOMBRE=x` por
cada una de estas variables:
`DOCLING_GPU_MEMORY_FRACTION INGESTOR_STATE_HOST_DIR OAUTH2_CLIENT_ID OAUTH2_CLIENT_SECRET OAUTH2_COOKIE_SECRET OAUTH2_EMAIL_DOMAINS OAUTH2_REDIRECT_URL OPENAI_API_KEY PYTORCH_CUDA_ALLOC_CONF QDRANT_STORAGE TOPICS_HOST_DIR TZ VLLM_DTYPE VLLM_GPU_MEMORY_UTILIZATION VLLM_KV_CACHE_DTYPE VLLM_LOGGING_LEVEL VLLM_MAX_MODEL_LEN VLLM_MAX_NUM_BATCHED_TOKENS VLLM_MAX_NUM_SEQS VLLM_MODEL VLLM_MODEL_REVISION VLLM_TENSOR_PARALLEL_SIZE VLLM_WORKER_MULTIPROC_METHOD`.

Helper `compose(compose_dir, files, *args)` que ejecuta, con `cwd=compose_dir`:
`["docker", "compose", "-p", "t", "--env-file", "test.env", "-f", f1, ("-f", f2), *args]`
y devuelve stdout (falla el test si returncode != 0, mostrando stderr).

Tests:
- `test_addon_no_cambia_servicios_compartidos`: la salida de
  `config --hash vllm,qdrant,rag-api` es IDÉNTICA con solo `docker-compose.yml` y con
  `docker-compose.yml` + `docker-compose.tutor.yml`.
- `test_servicios_del_tutor_restart_no_y_solo_localhost`: con ambos ficheros,
  `config --format json` → para `tutor-webui` y `tutor-oauth2-proxy`: `restart == "no"`
  y todos sus `ports` tienen `host_ip == "127.0.0.1"`; publicados 8080 y 4180 respectivamente.
- `test_bd_del_tutor_separada`: en el JSON, algún volumen de `tutor-webui` tiene
  `target == "/app/backend/data"` y `source` que termina en `tutor/data`.
- `test_proxy_del_tutor_apunta_al_webui_del_tutor`: el `command` de
  `tutor-oauth2-proxy` contiene `--upstream=http://tutor-webui:8080`.
- `test_make_tutor`: `make -n -C ROOT tutor` (sin docker) → la salida contiene
  `COMPOSE_FILE=docker-compose.yml:docker-compose.tutor.yml`, `stop ingestor oauth2-proxy openwebui`
  y `up -d qdrant vllm rag-api tutor-webui tutor-oauth2-proxy`.
- `test_make_ingest_y_web_paran_el_tutor`: `make -n -C ROOT ingest` y
  `make -n -C ROOT web` → ambas salidas contienen `stop tutor-oauth2-proxy tutor-webui`.
- `test_make_tutor_off_vuelve_a_web`: `make -n -C ROOT tutor-off` contiene
  `stop tutor-oauth2-proxy tutor-webui` y `up -d oauth2-proxy openwebui rag-api vllm qdrant`.
- `test_readme_documenta_el_modo_tutor`: `README.md` contiene `## Modo tutor`,
  `make tutor-off` y `tutor-ari`.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_compose.py -q` → 8 passed.
- `git diff tutor...HEAD -- Makefile` solo añade líneas (ninguna `-` salvo la de `.PHONY`).
- `git diff --stat tutor...HEAD` solo lista los 4 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T03: modo tutor con add-on de compose y make tutor/tutor-off'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
