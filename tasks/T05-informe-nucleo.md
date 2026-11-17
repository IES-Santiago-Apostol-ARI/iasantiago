# T05 — Núcleo del informe semanal por alumno (Fase 12)

## Objetivo
Función que lee la BD de Open WebUI (`webui.db`, SQLite) y devuelve, por alumno,
la actividad con el tutor en una semana: sesiones, días activos, mensajes y los
3 chats más largos con su enlace. Solo lectura, solo stdlib.

## Ficheros que puedes tocar (SOLO estos)
- `tutor/report.py` (nuevo)
- `tutor/tests/fixtures.py` (nuevo)
- `tutor/tests/test_report.py` (nuevo)

## Esquema de `webui.db` que se asume (Open WebUI 0.6.x)
Comprobado en el servidor después, no aquí. Solo se usan estas columnas:

```sql
CREATE TABLE user (id TEXT PRIMARY KEY, name TEXT, email TEXT, role TEXT);
CREATE TABLE chat (id TEXT PRIMARY KEY, user_id TEXT, title TEXT, chat TEXT,
                   created_at INTEGER, updated_at INTEGER, archived INTEGER DEFAULT 0);
```
La columna `chat.chat` es texto JSON con esta forma (solo importan estos campos):
```json
{"models": ["tutor-ari"],
 "history": {"messages": {
    "m1": {"id": "m1", "role": "user", "content": "hola", "timestamp": 1763380000},
    "m2": {"id": "m2", "role": "assistant", "content": "...", "timestamp": 1763380005}}},
 "messages": [ ...la misma lista de mensajes, versión plana... ]}
```
`timestamp` de cada mensaje = segundos Unix. Si existe `history.messages` (dict),
se usan sus valores; si no, la lista `messages`; si ninguna, el chat no tiene mensajes.

## Interfaz exacta (`tutor/report.py`)
```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

DEFAULT_MODEL = "tutor-ari"
DEFAULT_BASE_URL = "https://ia.santiagoapostol.net"
DEFAULT_TZ = "Europe/Madrid"

@dataclass(frozen=True)
class ChatSummary:
    chat_id: str
    title: str
    user_messages: int   # mensajes role=="user" del chat DENTRO del intervalo
    url: str             # f"{base_url}/c/{chat_id}"

@dataclass(frozen=True)
class StudentWeek:
    email: str
    name: str
    sessions: int        # nº de chats con >=1 mensaje de usuario en el intervalo
    days_active: int     # nº de fechas locales (tz) distintas con mensajes de usuario
    user_messages: int   # total de mensajes de usuario en el intervalo
    longest: tuple[ChatSummary, ...]  # máx. 3, orden: user_messages desc, luego chat_id asc

def collect_week(db_path: str | Path, start: datetime, end: datetime,
                 model_ids: Iterable[str] | None = (DEFAULT_MODEL,),
                 base_url: str = DEFAULT_BASE_URL,
                 tz: str = DEFAULT_TZ) -> list[StudentWeek]:
    ...
```

## Reglas
- `start` y `end` son datetimes CON zona horaria; intervalo semiabierto `[start, end)`.
  Si alguno no tiene `tzinfo`, `ValueError`.
- Abre la BD en solo lectura: `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.
  Si el fichero no existe, `FileNotFoundError` (compruébalo antes de conectar).
- Alumnos = filas de `user` con `role == "user"`. Los `admin` y `pending` no salen.
  Salen TODOS los alumnos, también los que no tienen actividad (con ceros y `longest=()`).
- Filtro de modelo: si `model_ids` es `None` o vacío, cuentan todos los chats. Si no,
  solo los chats cuyo JSON `models` contiene alguno de `model_ids`.
- Los chats archivados cuentan igual.
- Un chat con JSON inválido o sin mensajes se ignora (no lanza excepción).
- Un mensaje sin `timestamp` numérico se ignora.
- `days_active` usa la fecha local en `tz` (`zoneinfo.ZoneInfo(tz)`).
- Resultado ordenado por `email` ascendente.

## Pasos (TDD)
1. `tutor/tests/fixtures.py`: función
   `make_webui_db(path, users: list[dict], chats: list[dict]) -> Path`
   que crea las dos tablas del esquema de arriba e inserta las filas. Cada `chat` del
   argumento es un dict con `id, user_id, title, models, messages` donde `messages` es
   una lista de `(role, timestamp)`; la fixture construye el JSON con `history.messages`
   (ids `m0`, `m1`, …, `content` = `"x"`). Acepta además una clave opcional `raw_json`
   que, si está, se inserta tal cual en la columna `chat` (para probar JSON roto).
   Será reutilizada por T06: no la acoples a un test concreto.
2. Escribe `tutor/tests/test_report.py` (abajo). Ejecútalo: FALLA (rojo).
3. Implementa `tutor/report.py`. Ejecuta: PASA (verde).

## Tests que debe contener `tutor/tests/test_report.py`
Semana de referencia: `start = datetime(2026, 11, 16, tzinfo=ZoneInfo("Europe/Madrid"))`,
`end = start + timedelta(days=7)`. Usa `tmp_path`.
- `test_cuenta_sesiones_dias_y_mensajes`: alumno A con 2 chats del tutor: uno con 3
  mensajes de usuario el lunes, otro con 1 el miércoles (más respuestas `assistant`)
  → `sessions=2, days_active=2, user_messages=4`.
- `test_mensajes_fuera_de_la_semana_no_cuentan`: un mensaje 1 segundo antes de
  `start` y otro exactamente en `end` no cuentan; el chat sin mensajes dentro no es sesión.
- `test_dias_en_hora_local`: dos mensajes a las 23:30 y 00:30 hora de Madrid
  (distinto día local, aunque en UTC sea el mismo día) → `days_active=2`.
- `test_filtra_por_modelo`: chat con `models=["programacin"]` no cuenta con el filtro
  por defecto, pero sí con `model_ids=None`.
- `test_lista_alumnos_sin_actividad_y_excluye_admin`: un `admin` con chats no aparece;
  un alumno sin chats aparece con ceros y `longest == ()`.
- `test_tres_chats_mas_largos_con_enlace`: alumno con 4 chats de 5, 2, 7 y 2 mensajes
  → `longest` tiene 3 elementos con 7, 5, 2; el empate en 2 se resuelve por `chat_id`
  ascendente; `url == "https://ia.santiagoapostol.net/c/<id>"`; `base_url` se respeta
  si se pasa otro.
- `test_json_roto_se_ignora`: chat con `raw_json="{no es json"` → no lanza, no cuenta.
- `test_usa_lista_messages_si_no_hay_history`: chat con `raw_json` que solo tiene la
  lista plana `messages` → cuenta sus mensajes de usuario.
- `test_errores_de_entrada`: datetime sin zona → `ValueError`; BD inexistente →
  `FileNotFoundError`.
- `test_no_modifica_la_bd`: el `mtime` y el contenido (bytes) de la BD son iguales
  antes y después de `collect_week`.
- `test_orden_por_email`: el resultado viene ordenado por email.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_report.py -q` → 11 passed.
- `tutor/report.py` solo importa de la biblioteca estándar.
- `git diff --stat tutor...HEAD` solo lista los 3 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T05: núcleo del informe semanal por alumno sobre webui.db'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
