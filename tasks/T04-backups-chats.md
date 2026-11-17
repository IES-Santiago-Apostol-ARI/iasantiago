# T04 — Copias de los chats de Open WebUI y del tutor (Fase 7)

## Objetivo
`make backup` copia también `openwebui/data` (chats y ajustes del sitio normal) y
`tutor/data` (BD del modo tutor), cada una con su contenedor parado durante la copia
porque contienen una BD SQLite viva. `BACKUP_DIR` pasa a poder cambiarse desde fuera
(para apuntar al NAS).

## Ficheros que puedes tocar (SOLO estos)
- `Makefile`
- `tutor/tests/test_backup_targets.py` (nuevo)

## Cambios exactos en el `Makefile`
1. `BACKUP_DIR := /opt/iasantiago-rag/backups` pasa a
   `BACKUP_DIR ?= /opt/iasantiago-rag/backups` (así `BACKUP_DIR=/mnt/nas/... make backup`
   funciona). No cambies `DATE`.
2. En `.PHONY`, añade `backup-openwebui backup-tutor` en la línea de los `backup`.
3. `backup:` pasa a depender de
   `backup-topics backup-qdrant backup-state backup-openwebui backup-tutor`.
4. Después del target `backup-state` añade una macro y dos targets. Copia exactamente
   (las recetas con TABULADOR; `$$` es intencionado):

   ```make
   # Copia una carpeta con BD SQLite viva parando antes su contenedor, y lo vuelve a
   # arrancar SOLO si estaba en marcha. $(1)=contenedor, $(2)=carpeta, $(3)=nombre.
   # Si la carpeta no existe (p. ej. nunca se usó el modo tutor) no hace nada.
   define backup_live_db
   	@if [ ! -d /opt/iasantiago-rag/$(2) ]; then \
   	    echo "[--] $(2) no existe, nada que copiar"; exit 0; \
   	fi; \
   	sudo mkdir -p $(BACKUP_DIR); \
   	running=$$(docker inspect -f '{{.State.Running}}' $(1) 2>/dev/null || echo false); \
   	if [ "$$running" = true ]; then docker stop $(1) >/dev/null; fi; \
   	sudo tar -C /opt/iasantiago-rag -czf $(BACKUP_DIR)/$(3)-$(DATE).tgz $(2); rc=$$?; \
   	if [ "$$running" = true ]; then docker start $(1) >/dev/null; fi; \
   	if [ $$rc -eq 0 ]; then echo "[OK] $(2) -> $(BACKUP_DIR)/$(3)-$(DATE).tgz"; fi; \
   	exit $$rc
   endef

   backup-openwebui:
   	$(call backup_live_db,openwebui,openwebui/data,openwebui)

   backup-tutor:
   	$(call backup_live_db,tutor-webui,tutor/data,tutor)
   ```
5. En el target `restore`, después de las dos líneas `@echo` que explican cómo
   restaurar `topics`, añade estas cuatro (no restaures los chats automáticamente:
   machacarían los chats nuevos):
   ```make
   	@echo "Y, si procede, los chats (con openwebui/tutor-webui parados):"
   	@echo "  sudo tar -C /opt/iasantiago-rag -xzf $(BACKUP_DIR)/openwebui-$(BACKUP).tgz"
   	@echo "  sudo tar -C /opt/iasantiago-rag -xzf $(BACKUP_DIR)/tutor-$(BACKUP).tgz"
   	@echo "  (el modo tutor no vuelve solo: make tutor)"
   ```
No toques ningún otro target.

## Pasos (TDD)
1. Escribe `tutor/tests/test_backup_targets.py` (abajo). FALLA (rojo).
2. Cambia el `Makefile`. PASA (verde).

## Tests que debe contener `tutor/tests/test_backup_targets.py`
Usa `subprocess.run(["make", "-n", "-C", str(ROOT), *args], capture_output=True, text=True)`
con `ROOT = Path(__file__).resolve().parents[2]`. `make -n` no ejecuta nada.
- `test_backup_incluye_chats`: `make -n backup DATE=D` → la salida contiene
  `openwebui/data`, `tutor/data`, `openwebui-D.tgz` y `tutor-D.tgz`, además de los que ya
  había: `topics-D.tgz`, `qdrant-D.tgz`, `state-D.tgz`.
- `test_backup_openwebui_para_y_rearranca`: `make -n backup-openwebui DATE=D BACKUP_DIR=/mnt/nas/x`
  → contiene `docker stop openwebui`, `docker start openwebui` y `/mnt/nas/x/openwebui-D.tgz`;
  y `docker stop` aparece ANTES que `tar` y `tar` ANTES que `docker start`.
- `test_backup_tutor_usa_su_contenedor`: `make -n backup-tutor DATE=D` → contiene
  `docker stop tutor-webui` y `tutor-D.tgz`.
- `test_backup_dir_desde_el_entorno`: con `env={**os.environ, "BACKUP_DIR": "/desde/env"}`,
  `make -n backup-topics DATE=D` → contiene `/desde/env/topics-D.tgz`.
- `test_backup_dir_por_defecto`: con `BACKUP_DIR` quitado del entorno,
  `make -n backup-topics DATE=D` → contiene `/opt/iasantiago-rag/backups/topics-D.tgz`.
- `test_restore_no_restaura_chats_automaticamente`: `make -n restore BACKUP=X` → las
  líneas que contienen `openwebui-X.tgz` empiezan (tras `echo`) por texto de ayuda, es
  decir: ninguna línea de la salida empieza por `sudo tar` y contiene `openwebui-X.tgz`.
- `test_macro_es_shell_valido`: ejecuta `make -n backup-openwebui DATE=D` y comprueba
  que su salida es shell sintácticamente válido:
  `subprocess.run(["bash", "-n"], input=salida, text=True).returncode == 0`.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_backup_targets.py -q` → 7 passed.
- `python3 -m pytest tutor/tests -q` → todo verde (incluidos los tests de T03 sobre el Makefile).
- `git diff --stat tutor...HEAD` solo lista los 2 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T04: make backup copia los chats de Open WebUI y del modo tutor'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
