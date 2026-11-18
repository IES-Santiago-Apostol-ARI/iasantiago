# T12 — Copias de chats sin `cache/` y con caducidad

## Objetivo
La copia nocturna de `openwebui/data` ocupa 1,8 GB, casi todo `cache/` (modelos que Open
WebUI vuelve a descargar), y nada borra las copias viejas. Se excluye `cache/` y se
borran las copias de chats (`openwebui-*.tgz`, `tutor-*.tgz`) de más de N días.
Las demás copias (`topics-`, `qdrant-`, `state-`) NO se tocan.

## Ficheros que puedes tocar (SOLO estos)
- `Makefile`
- `tutor/tests/test_backup_targets.py`

## Cambios exactos en el `Makefile`
1. Debajo de `BACKUP_DIR ?= /opt/iasantiago-rag/backups` añade:
   ```make
   BACKUP_KEEP_DAYS ?= 14
   ```
2. En `.PHONY`, en la línea `backup-openwebui backup-tutor restore \`, añade
   `backup-prune` después de `backup-tutor`.
3. En la macro `backup_live_db`, la línea del `tar` pasa a excluir la caché. Solo cambia
   esto: se añade `--exclude=$(2)/cache` después de `-C /opt/iasantiago-rag`:
   ```make
   	sudo tar -C /opt/iasantiago-rag --exclude=$(2)/cache -czf $(BACKUP_DIR)/$(3)-$(DATE).tgz $(2); rc=$$?; \
   ```
4. En el target `backup`, añade como PRIMERA línea de la receta (antes del `@echo`
   existente):
   ```make
   	@$(MAKE) --no-print-directory backup-prune
   ```
5. Después de los targets `backup-openwebui` y `backup-tutor` (antes del comentario
   `# Uso:` de `restore`), añade (recetas con TABULADOR; `$$` es intencionado):
   ```make
   # Borra las copias de chats de más de BACKUP_KEEP_DAYS días. Solo openwebui- y
   # tutor-; las de topics, qdrant y state no caducan.
   backup-prune:
   	@case "$(BACKUP_KEEP_DAYS)" in ''|*[!0-9]*) \
   	    echo "[ERR] BACKUP_KEEP_DAYS debe ser un número de días: '$(BACKUP_KEEP_DAYS)'"; exit 1;; \
   	esac; \
   	if [ ! -d $(BACKUP_DIR) ]; then echo "[--] $(BACKUP_DIR) no existe, nada que borrar"; exit 0; fi; \
   	sudo find $(BACKUP_DIR) -maxdepth 1 -type f \( -name 'openwebui-*.tgz' -o -name 'tutor-*.tgz' \) -mtime +$(BACKUP_KEEP_DAYS) -print -delete; \
   	echo "[OK] copias de chats de más de $(BACKUP_KEEP_DAYS) días borradas de $(BACKUP_DIR)"
   ```
6. En el target `restore`, después de la línea `@echo "  (el modo tutor no vuelve solo: make tutor)"`,
   añade:
   ```make
   	@echo "  (las copias no llevan cache/: Open WebUI la vuelve a descargar al arrancar)"
   ```
No toques ningún otro target.

## Tests (añadir a `tutor/tests/test_backup_targets.py`; no borres los existentes)
Reutiliza `make_n`. Para ejecutar de verdad la receta de `backup-prune` en un test, toma
la salida de `make -n backup-prune …`, quita `sudo ` con `.replace("sudo ", "")` y
pásala a `subprocess.run(["bash", "-c", salida], capture_output=True, text=True)`.

- `test_backup_excluye_cache`: `make -n backup-openwebui DATE=D` contiene
  `--exclude=openwebui/data/cache`; `make -n backup-tutor DATE=D` contiene
  `--exclude=tutor/data/cache`.
- `test_prune_solo_copias_de_chats`: `make -n backup-prune BACKUP_DIR=/x BACKUP_KEEP_DAYS=7`
  contiene `find /x`, `-mtime +7`, `openwebui-*.tgz`, `tutor-*.tgz` y `-delete`; NO
  contiene `topics-`, `qdrant-` ni `state-`.
- `test_prune_14_dias_por_defecto`: sin `BACKUP_KEEP_DAYS` (quítalo del entorno) →
  contiene `-mtime +14`.
- `test_backup_ejecuta_prune_al_final`: `make -n backup DATE=D` contiene `-mtime +14`,
  y su posición está después de la ÚLTIMA aparición de `tutor-D.tgz`.
- `test_prune_borra_solo_lo_viejo`: en `tmp_path` crea `openwebui-a.tgz`, `tutor-a.tgz`,
  `topics-a.tgz`, `qdrant-a.tgz` con fecha de hace 30 días (`os.utime`), y
  `openwebui-b.tgz` con fecha de ahora. Ejecuta la receta (como se explica arriba) con
  `BACKUP_DIR=<tmp_path> BACKUP_KEEP_DAYS=14` → returncode 0; ya no existen
  `openwebui-a.tgz` ni `tutor-a.tgz`; siguen existiendo los otros tres.
- `test_prune_rechaza_dias_invalidos`: igual que el anterior pero con
  `BACKUP_KEEP_DAYS=abc` → returncode distinto de 0 y los 5 ficheros siguen existiendo.
- `test_prune_sin_carpeta`: con `BACKUP_DIR=<tmp_path>/no-existe` → returncode 0.

## Criterios de aceptación
- `python3 -m pytest tutor/tests -q` → todo verde (incluidos los 8 tests anteriores de
  `test_backup_targets.py` y los de compose y report que usan el Makefile).
- `git diff --stat tutor...HEAD` solo lista los 2 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T12: copias de chats sin cache y con caducidad'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
