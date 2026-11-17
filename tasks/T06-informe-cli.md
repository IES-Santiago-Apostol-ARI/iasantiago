# T06 — CLI del informe semanal: Markdown, CSV y `make tutor-report` (Fase 12)

## Objetivo
Convertir el resultado de `collect_week` (T05, ya en `tutor/report.py`) en un informe
legible para el profesor (Markdown) o en CSV, con una línea de comandos y un target
de make.

## Ficheros que puedes tocar (SOLO estos)
- `tutor/report.py` (AÑADIR funciones; no cambies `collect_week` ni las dataclasses)
- `Makefile`
- `tutor/tests/test_report_cli.py` (nuevo)

Reutiliza `tutor/tests/fixtures.py` (`make_webui_db`) para crear BDs de prueba; no lo modifiques.

## Interfaz exacta (añadir a `tutor/report.py`)
```python
def iso_week_bounds(week: str, tz: str = DEFAULT_TZ) -> tuple[datetime, datetime]:
    """'2026-W47' -> (lunes 00:00, lunes siguiente 00:00) en tz. Formato inválido -> ValueError."""
def render_markdown(weeks: list[StudentWeek], start: datetime, end: datetime) -> str: ...
def render_csv(weeks: list[StudentWeek]) -> str: ...
def main(argv: list[str] | None = None) -> int: ...
```
Termina el fichero con `if __name__ == "__main__": raise SystemExit(main())`.

### `render_markdown`
- Primera línea: `# Uso del tutor — semana del DD/MM/AAAA al DD/MM/AAAA` (inicio y
  `end - 1 día`, en formato español).
- Línea en blanco y luego una tabla con cabecera exacta:
  `| Alumno | Sesiones | Días activos | Mensajes | Conversaciones más largas |`
  y separador `|---|---|---|---|---|`.
- Una fila por alumno, en el orden recibido. `Alumno` = `name (email)`. La última columna
  son enlaces Markdown `[título](url)` separados por `<br>`; si el título está vacío, usa
  `(sin título)`; si no hay conversaciones, `—`. Escapa `|` en los títulos como `\|`.
- Al final, línea en blanco y: `Sin actividad: N de M alumnos.`
- Termina con un salto de línea.

### `render_csv`
Con `csv.writer`, cabecera `email,nombre,sesiones,dias_activos,mensajes,chat1,chat2,chat3`;
`chatN` = url del N-ésimo de `longest` o vacío.

### `main`
argparse:
- `--db` (obligatorio): ruta a `webui.db`
- `--week` (por defecto: la semana ISO anterior a la actual, calculada con `datetime.now(ZoneInfo(tz))`)
- `--model` (por defecto `DEFAULT_MODEL`); `--all-models` (flag) desactiva el filtro (`model_ids=None`)
- `--format` `md` | `csv` (por defecto `md`)
- `--base-url` (por defecto `DEFAULT_BASE_URL`)
- `--out` (opcional): escribe ahí (UTF-8) en vez de stdout
Errores: BD inexistente o `--week` inválida → mensaje en stderr y devuelve 2. Si todo va bien, 0.

## Makefile
1. Añade `tutor-report` a `.PHONY`.
2. Añade al final del fichero:
   ```make
   # ------- Informe semanal del tutor (Fase 12) -------
   # Uso: make tutor-report [WEEK=2026-W47] [TUTOR_DB=openwebui/data/webui.db]
   # Por defecto lee la BD del modo tutor y la semana pasada. Solo lectura.
   TUTOR_DB ?= tutor/data/webui.db
   tutor-report:
   	@sudo python3 -m tutor.report --db $(TUTOR_DB) $(if $(WEEK),--week $(WEEK)) --out tutor-report-$(or $(WEEK),ultima).md
   	@echo "[OK] tutor-report-$(or $(WEEK),ultima).md"
   ```
   (`sudo` porque `tutor/data` pertenece a root dentro del contenedor. Los
   `tutor-report-*.md` generados ya quedan fuera de git por la regla `*.md`.)

## Pasos (TDD)
1. Escribe `tutor/tests/test_report_cli.py` (abajo). FALLA (rojo).
2. Implementa. PASA (verde).

## Tests que debe contener `tutor/tests/test_report_cli.py`
- `test_iso_week_bounds`: `"2026-W47"` → `(2026-11-16 00:00, 2026-11-23 00:00)` en
  Europe/Madrid; `"2026-47"` y `"2026-W99"` → `ValueError`.
- `test_markdown_cabecera_tabla_y_resumen`: con una BD de 2 alumnos (uno con 2 chats, otro
  sin actividad) → contiene `# Uso del tutor — semana del 16/11/2026 al 22/11/2026`, la
  cabecera de la tabla, `[título](https://ia.santiagoapostol.net/c/<id>)`, `—` en el
  alumno sin actividad y `Sin actividad: 1 de 2 alumnos.`
- `test_markdown_escapa_barras_y_titulo_vacio`: título `a|b` sale como `a\|b`; título
  vacío sale como `(sin título)`.
- `test_csv`: la primera línea es la cabecera exacta; el alumno sin chats tiene las tres
  columnas `chat` vacías.
- `test_main_md_a_fichero`: `main(["--db", db, "--week", "2026-W47", "--out", out])` → 0 y el
  fichero empieza por `# Uso del tutor`.
- `test_main_all_models`: chat con `models=["programacin"]`: sin `--all-models` no cuenta,
  con `--all-models` sí (comprobado en la salida CSV con capsys).
- `test_main_errores`: BD inexistente → 2; `--week 2026-W99` → 2.
- `test_make_tutor_report`: `make -n -C ROOT tutor-report WEEK=2026-W47` → contiene
  `python3 -m tutor.report --db tutor/data/webui.db --week 2026-W47`.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_report_cli.py -q` → 8 passed.
- `python3 -m pytest tutor/tests -q` → todo verde (incluidos T03, T04 y T05).
- `git diff tutor...HEAD -- tutor/report.py` solo añade líneas.
- `git diff --stat tutor...HEAD` solo lista los 3 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T06: CLI del informe semanal en Markdown y CSV, make tutor-report'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
