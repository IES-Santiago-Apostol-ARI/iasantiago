SHELL := /bin/bash
ENV_FILE := .env
BACKUP_DIR ?= /opt/iasantiago-rag/backups
BACKUP_KEEP_DAYS ?= 14
DATE := $(shell date +%F_%H%M%S)

# Modo tutor (docker-compose.tutor.yml): segundo Open WebUI que sustituye al normal.
TUTOR := COMPOSE_FILE=docker-compose.yml:docker-compose.tutor.yml

.PHONY: gen-env up down stop seed reset bench \
        status logs tail rag-restart \
        backup backup-topics backup-qdrant backup-state \
        backup-openwebui backup-tutor backup-prune restore \
        watcher-on watcher-off \
        publish-docs unpublish-docs \
        eval-sample eval-file eval-nightly \
        ingest web tutor tutor-off tutor-report


gen-env:
	@if [ ! -f $(ENV_FILE) ]; then \
	    echo "Creando .env desde .env.example"; \
	    cp .env.example .env; \
	fi

up: gen-env
	docker compose pull
	docker compose build
	docker compose up -d

down:
	docker compose down
stop:
	docker compose stop

seed: gen-env
	@echo "Creando carpetas de temas y copiando PDFs de ejemplo..."
	@mkdir -p data/storage data/ingestor-state
	@mkdir -p topics/Chemistry topics/Electronics topics/Programming
	@cp -r seeds/* topics/
	@echo "Lanzando ingestor para indexar..."
	docker compose restart ingestor

reset: gen-env
	@echo "Reseteando Qdrant y el estado del ingestor..."
	@docker compose down
	@sudo rm -rf data/ingestor-state/.processing_state.json
	@sudo rm -rf data/storage/*
	@sudo rm -rf data/ingestor-state/*
	@docker compose up -d ingestor

bench:
	@echo "Benchmark de vLLM /chat/completions"
	python3 scripts/bench_vllm.py || true

# ------- Utilidad -------
status:
	docker compose ps

logs:
	docker compose logs --tail=200

tail:
	docker compose logs -f

rag-restart:
	docker compose restart rag-api

# ------- Modo ingestión / web -------
ingest:
	$(TUTOR) docker compose stop tutor-oauth2-proxy tutor-webui || true
	@echo "Deteniendo vllm, rag-api, openwebui y lanzando ingestor..."
	docker compose stop vllm rag-api openwebui oauth2-proxy || true
	docker compose --profile ingest up -d ingestor

web:
	$(TUTOR) docker compose stop tutor-oauth2-proxy tutor-webui || true
	@echo "Deteniendo ingestor y lanzando servicios web..."
	docker compose stop ingestor || true
	docker compose up -d oauth2-proxy openwebui rag-api vllm qdrant

tutor:
	@echo "Parando el sitio normal y lanzando el modo tutor..."
	docker compose stop ingestor oauth2-proxy openwebui || true
	$(TUTOR) docker compose up -d qdrant vllm rag-api tutor-webui tutor-oauth2-proxy

tutor-off:
	@echo "Parando el modo tutor y volviendo al sitio normal..."
	$(MAKE) web

# ------- Backups -------
backup: backup-topics backup-qdrant backup-state backup-openwebui backup-tutor
	@$(MAKE) --no-print-directory backup-prune
	@echo "Backup completo en $(BACKUP_DIR)/full-$(DATE)"

backup-topics:
	@sudo mkdir -p $(BACKUP_DIR)
	sudo tar -C /opt/iasantiago-rag -czf $(BACKUP_DIR)/topics-$(DATE).tgz topics
	@echo "[OK] topics -> $(BACKUP_DIR)/topics-$(DATE).tgz"

backup-qdrant:
	@sudo mkdir -p $(BACKUP_DIR)
	sudo tar -C /opt/iasantiago-rag -czf $(BACKUP_DIR)/qdrant-$(DATE).tgz data/storage
	@echo "[OK] qdrant -> $(BACKUP_DIR)/qdrant-$(DATE).tgz"

# data/ingestor-state guarda .processing_state.json, que es justo lo que no se
# puede perder: sin él se reprocesa el corpus entero. (Era data/whoosh hasta el
# 2026-08-01, cuando se retiraron los índices Whoosh.)
backup-state:
	@sudo mkdir -p $(BACKUP_DIR)
	sudo tar -C /opt/iasantiago-rag -czf $(BACKUP_DIR)/state-$(DATE).tgz data/ingestor-state
	@echo "[OK] estado del ingestor -> $(BACKUP_DIR)/state-$(DATE).tgz"

# Copia una carpeta con BD SQLite viva parando antes su contenedor, y lo vuelve a
# arrancar SOLO si estaba en marcha. $(1)=contenedor, $(2)=carpeta, $(3)=nombre.
# Si la carpeta no existe (p. ej. nunca se usó el modo tutor) no hace nada.
define backup_live_db
	@if [ ! -d /opt/iasantiago-rag/$(2) ]; then \
	    echo "[--] $(2) no existe, nada que copiar"; exit 0; \
	fi; \
	sudo mkdir -p $(BACKUP_DIR); \
	running=$$(docker inspect -f '{{.State.Running}}' $(1) 2>/dev/null || echo false); \
	if [ "$$running" = true ]; then docker stop $(1) >/dev/null || { echo "[ERR] no se pudo parar $(1); no se copia $(2)"; exit 1; }; fi; \
	sudo tar -C /opt/iasantiago-rag --exclude=$(2)/cache -czf $(BACKUP_DIR)/$(3)-$(DATE).tgz $(2); rc=$$?; \
	if [ "$$running" = true ]; then docker start $(1) >/dev/null || { echo "[ERR] $(1) no ha vuelto a arrancar"; rc=1; }; fi; \
	if [ $$rc -eq 0 ]; then echo "[OK] $(2) -> $(BACKUP_DIR)/$(3)-$(DATE).tgz"; fi; \
	exit $$rc
endef

backup-openwebui:
	$(call backup_live_db,openwebui,openwebui/data,openwebui)

backup-tutor:
	$(call backup_live_db,tutor-webui,tutor/data,tutor)

# Borra las copias de chats de más de BACKUP_KEEP_DAYS días. Solo openwebui- y
# tutor-; las de topics, qdrant y state no caducan.
backup-prune:
	@case "$(BACKUP_KEEP_DAYS)" in ''|*[!0-9]*) \
	    echo "[ERR] BACKUP_KEEP_DAYS debe ser un número de días: '$(BACKUP_KEEP_DAYS)'"; exit 1;; \
	esac; \
	if [ ! -d $(BACKUP_DIR) ]; then echo "[--] $(BACKUP_DIR) no existe, nada que borrar"; exit 0; fi; \
	sudo find $(BACKUP_DIR) -maxdepth 1 -type f \( -name 'openwebui-*.tgz' -o -name 'tutor-*.tgz' \) -mtime +$(BACKUP_KEEP_DAYS) -print -delete; \
	echo "[OK] copias de chats de más de $(BACKUP_KEEP_DAYS) días borradas de $(BACKUP_DIR)"

# Uso:
# make restore BACKUP=2025-10-10_023000
restore:
	@if [ -z "$(BACKUP)" ]; then echo "ERROR: usa make restore BACKUP=YYYY-MM-DD_HHMMSS"; exit 1; fi
	@echo "Restaurando backup $(BACKUP) (se requiere ventana de mantenimiento)..."
	docker compose down
	sudo rm -rf data/storage/* data/ingestor-state/*
	sudo tar -C /opt/iasantiago-rag -xzf $(BACKUP_DIR)/qdrant-$(BACKUP).tgz
	@# Backups desde el 2026-08-01 son state-*.tgz; los anteriores, whoosh-*.tgz
	@if [ -f $(BACKUP_DIR)/state-$(BACKUP).tgz ]; then \
	    sudo tar -C /opt/iasantiago-rag -xzf $(BACKUP_DIR)/state-$(BACKUP).tgz; \
	else \
	    sudo tar -C /opt/iasantiago-rag -xzf $(BACKUP_DIR)/whoosh-$(BACKUP).tgz && \
	    sudo mv /opt/iasantiago-rag/data/whoosh /opt/iasantiago-rag/data/ingestor-state; \
	fi
	@echo "Opcionalmente restaura topics si procede:"
	@echo "  sudo tar -C /opt/iasantiago-rag -xzf $(BACKUP_DIR)/topics-$(BACKUP).tgz"
	@echo "Y, si procede, los chats (con openwebui/tutor-webui parados):"
	@echo "  sudo tar -C /opt/iasantiago-rag -xzf $(BACKUP_DIR)/openwebui-$(BACKUP).tgz"
	@echo "  sudo tar -C /opt/iasantiago-rag -xzf $(BACKUP_DIR)/tutor-$(BACKUP).tgz"
	@echo "  (el modo tutor no vuelve solo: make tutor)"
	@echo "  (las copias no llevan cache/: Open WebUI la vuelve a descargar al arrancar)"
	docker compose up -d

# ------- Watcher on/off (override de comando en ingestor) -------
# Usa un archivo de override que cambia el command a watcher.py
watcher-on:
	@echo "Activando watcher (indexación en caliente)..."
	@if [ ! -f docker-compose.watcher.yml ]; then \
		bash -c 'cat > docker-compose.watcher.yml <<YML\n\
version: "3.9"\n\
services:\n\
  ingestor:\n\
    command: ["python", "-u", "watcher.py"]\n\
YML'; \
	fi
	COMPOSE_FILE=docker-compose.yml:docker-compose.watcher.yml docker compose up -d --build ingestor
	@echo "[OK] watcher activo"

watcher-off:
	@echo "Desactivando watcher (vuelve a escaneo inicial)..."
	COMPOSE_FILE=docker-compose.yml:docker-compose.watcher.yml docker compose stop ingestor || true
	docker compose up -d --build ingestor
	@echo "[OK] watcher desactivado (ingestor = main.py)"


# ------- Publicar PDFs como /docs bajo Nginx -------
publish-docs:
	@echo "Publicando /docs/ en Nginx con autenticación oauth2-proxy..."
	@sudo bash -c 'tee /etc/nginx/conf.d/iasantiago-docs.conf >/dev/null <<NGINX\n\
location /docs/ {\n\
    auth_request /oauth2/auth;\n\
    error_page 401 = @oauth2_signin;\n\
    autoindex on;\n\
    alias /opt/iasantiago-rag/topics/;\n\
    add_header X-Content-Type-Options nosniff;\n\
    add_header X-Frame-Options DENY;\n\
}\n\
NGINX'
	sudo nginx -t
	sudo systemctl reload nginx
	@echo "[OK] /docs/ disponible en https://iasantiago.santiagoapostol.net/docs/ (requiere autenticación)"

unpublish-docs:
	@echo "Despublicando /docs/..."
	@sudo rm -f /etc/nginx/conf.d/iasantiago-docs.conf
	sudo nginx -t
	sudo systemctl reload nginx
	@echo "[OK] /docs/ retirado"

# ------- Evaluación offline -------
# Plantilla grande de casos -> eval/cases.sample.json (ver más abajo)
eval-sample:
	@echo "Ejecutando evaluación con plantilla..."
	curl -s http://127.0.0.1:8001/v1/eval/offline \
	    -H 'Content-Type: application/json' \
	    --data-binary @eval/cases.sample.json | jq . > eval/last_eval.json
	@echo "[OK] Resultado en eval/last_eval.json"

# Uso:
# make eval-file FILE=eval/mis_casos.json
eval-file:
	@if [ -z "$(FILE)" ]; then echo "ERROR: usa make eval-file FILE=path.json"; exit 1; fi
	curl -s http://127.0.0.1:8001/v1/eval/offline \
	    -H 'Content-Type: application/json' \
	    --data-binary @$(FILE) | jq . > eval/last_eval.json
	@echo "[OK] Resultado en eval/last_eval.json"

# Lanza el service systemd de evaluación nocturna ahora mismo
eval-nightly:
	sudo systemctl start iasantiago-rag-eval.service && sudo journalctl -u iasantiago-rag-eval.service -n 50 --no-pager

# ------- Informe semanal del tutor (Fase 12) -------
# Uso: make tutor-report [WEEK=2026-W47] [TUTOR_DB=openwebui/data/webui.db]
# Por defecto lee la BD del modo tutor y la semana pasada. Solo lectura.
TUTOR_DB ?= tutor/data/webui.db
tutor-report:
	@sudo python3 -m tutor.report --db $(TUTOR_DB) $(if $(WEEK),--week $(WEEK)) --out tutor-report-$(or $(WEEK),ultima).md
	@echo "[OK] tutor-report-$(or $(WEEK),ultima).md"
