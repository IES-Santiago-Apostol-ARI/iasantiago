# T07 — Registro de quién abre cada PDF de /docs/ (Fase 12)

## Objetivo
Que nginx escriba un log propio de `/docs/` con el email del alumno, y un parser
que cuente aperturas distintas (alumno, documento, día), ignorando las peticiones
parciales repetidas que hace el visor de PDF. Es información para el profesor, no nota.

## Ficheros que puedes tocar (SOLO estos)
- `nginx/nginx.conf`
- `tutor/docs_log.py` (nuevo)
- `tutor/tests/test_docs_log.py` (nuevo)

## Parte 1 — nginx (3 líneas)
En `nginx/nginx.conf`:
1. Dentro del bloque `http`, justo DESPUÉS del bloque `map $ow_auth_email $ow_auth_name { ... }`
   (termina en `}` hacia la línea 52), añade:
   ```nginx
   # Quién abre cada PDF de /docs/ (Fase 12 del tutor). Lo lee tutor/docs_log.py.
   log_format docs '$time_iso8601 $ow_auth_email "$request_uri" $status';
   ```
2. Dentro de `location /docs/ {`, justo DESPUÉS de la línea `error_page 401 = @oauth2_signin;`, añade:
   ```nginx
         auth_request_set $ow_auth_email $upstream_http_x_auth_request_email;
         access_log /var/log/nginx/docs_access.log docs;
   ```
   (misma indentación que las líneas vecinas). Es el mismo `auth_request_set` que ya
   usa la location de signin; oauth2-proxy envía la cabecera porque tiene
   `set_xauthrequest = true`.
No toques nada más de nginx.conf. No puedes ejecutar `nginx -t` aquí: el orquestador
lo dejará anotado para el servidor.

## Parte 2 — parser (`tutor/docs_log.py`)
Formato de cada línea (lo produce el `log_format` de arriba):
```
2026-11-17T10:15:02+01:00 alumno1@santiagoapostol.net "/docs/Programming/Tema%201.pdf" 206
```

Interfaz exacta:
```python
from dataclasses import dataclass
from datetime import date
from typing import Iterable

@dataclass(frozen=True)
class DocAccess:
    email: str
    document: str   # ruta decodificada SIN el prefijo /docs/ y sin query: "Programming/Tema 1.pdf"
    day: date       # fecha tal como viene en el timestamp (hora local del servidor)

def parse_line(line: str) -> DocAccess | None: ...
def distinct_openings(lines: Iterable[str]) -> set[DocAccess]: ...
def summarize(lines: Iterable[str]) -> dict[str, dict[str, int]]:
    """email -> {documento -> nº de días distintos en que lo abrió}"""
def main(argv: list[str] | None = None) -> int: ...
```

Reglas de `parse_line` (devuelve `None` si la línea no cuenta):
- Línea vacía o que no encaja con el formato → `None` (no lanza).
- Email `-` o vacío → `None`.
- Estado distinto de 200, 206 y 304 → `None`.
- La ruta debe empezar por `/docs/`; se quita la query (`?…`) y el fragmento (`#…`),
  se decodifica con `urllib.parse.unquote`, y se quita el prefijo `/docs/`.
- Rutas que terminan en `/` (listado de carpeta) → `None`.
- Solo cuentan ficheros cuya extensión, sin distinguir mayúsculas, sea `.pdf` → otros `None`.
- `day` = `datetime.fromisoformat(timestamp).date()`.

`main`: `python3 -m tutor.docs_log FICHERO [--since AAAA-MM-DD] [--until AAAA-MM-DD]`
(ambos inclusivos, opcionales). Lee el fichero (UTF-8, `errors="replace"`) y escribe
en stdout un CSV con cabecera `email,documento,dias` ordenado por email y documento,
usando `csv.writer`. Devuelve 0. Si el fichero no existe, escribe un mensaje en stderr
y devuelve 1. Añade al final `if __name__ == "__main__": raise SystemExit(main())`.

## Pasos (TDD)
1. Escribe `tutor/tests/test_docs_log.py` (abajo). Ejecútalo: FALLA (rojo).
2. Implementa `tutor/docs_log.py`. PASA (verde).
3. Haz el cambio de nginx de la Parte 1.

## Tests que debe contener `tutor/tests/test_docs_log.py`
- `test_parse_line_valida`: la línea de ejemplo → `DocAccess("alumno1@santiagoapostol.net", "Programming/Tema 1.pdf", date(2026, 11, 17))`.
- `test_quita_query_y_decodifica`: `"/docs/Quimica/a%C3%B1o.PDF?x=1"` → documento `"Quimica/año.PDF"`.
- `test_descarta_lo_que_no_cuenta`: email `-`, estado 401, estado 404, ruta `/docs/Programming/`,
  fichero `.png`, ruta fuera de `/docs/`, línea vacía y línea basura → todas `None`.
- `test_peticiones_parciales_cuentan_una_vez`: 5 líneas 206 del mismo alumno, documento
  y día → `distinct_openings` tiene 1 elemento.
- `test_summarize_cuenta_dias_distintos`: mismo documento abierto dos días distintos
  (varias líneas cada día) y otro documento un día → `{"a@x": {"P/t1.pdf": 2, "P/t2.pdf": 1}}`.
- `test_main_csv_y_filtro_de_fechas`: fichero temporal con aperturas del 10, 15 y 20 de
  noviembre; `main([f, "--since", "2026-11-12", "--until", "2026-11-18"])` → devuelve 0 y
  el CSV (capturado con `capsys`) solo cuenta la del 15; primera línea `email,documento,dias`.
- `test_main_fichero_inexistente`: devuelve 1.
- `test_nginx_conf_tiene_el_log_de_docs`: `nginx/nginx.conf` contiene `log_format docs`,
  `access_log /var/log/nginx/docs_access.log docs;`, y el `auth_request_set $ow_auth_email`
  aparece AL MENOS dos veces (signin y /docs/); además la línea `access_log … docs;`
  aparece DESPUÉS de `location /docs/ {` en el fichero.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_docs_log.py -q` → 8 passed.
- `git diff tutor...HEAD -- nginx/nginx.conf` solo añade 4 líneas (comentario incluido), no quita ninguna.
- `git diff --stat tutor...HEAD` solo lista los 3 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T07: log de /docs/ con email y parser de aperturas'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
