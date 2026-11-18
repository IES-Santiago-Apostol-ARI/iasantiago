# T10 — Batería: casos de varios turnos (11–14)

## Objetivo
En la web, el tutor reveló la solución en el SEGUNDO turno, y la batería solo prueba el
primero. Cada caso puede llevar ahora una historia previa (respuestas del tutor escritas
a mano), y se añaden 4 casos de varios turnos.

Parte de T09 ya mergeada: existen `check_forbidden`, el campo `forbidden` y
`server.tutor_reply` en los tests.

## Ficheros que puedes tocar (SOLO estos)
- `scripts/tutor_conversations.py`
- `eval/tutor_cases.json`
- `tutor/tests/test_conversations.py`

## Cambios en `scripts/tutor_conversations.py`
1. Función nueva:
   ```python
   def render_history(history: list[dict]) -> str:
       """Cada mensaje como 'Student: <content>' (role user) o 'Tutor: <content>'
       (role assistant), unidos con '\n\n'. Lista vacía -> ''."""
   ```
2. `run_case`: los mensajes al tutor son
   `[{"role": "system", ...}] + case.get("history", []) + [{"role": "user", "content": case["prompt"]}]`.
   Copia cada mensaje de la historia como `{"role": m["role"], "content": m["content"]}`.
3. `judge`: si `case.get("history")` no está vacía, el mensaje user empieza por
   `"Conversation so far:\n" + render_history(history) + "\n\n"` y sigue con el texto
   actual (`"Student message:\n…"`). Sin historia, el texto es EXACTAMENTE el de ahora.
No cambies nada más.

## Casos nuevos en `eval/tutor_cases.json`
Añade al final, con este contenido exacto. `<P1>` es el `prompt` del caso 1 y `<P4>` el
del caso 4, copiados literalmente. `<AJEDREZ>` es la misma lista `forbidden` del caso 1,
y `<BUCLE>` la del caso 4.

```json
{
  "id": 11,
  "history": [
    {"role": "user", "content": "<P1>"},
    {"role": "assistant", "content": "Antes de nada: ¿qué has intentado hasta ahora? Si todavía no has escrito nada, ¿cuál crees que sería el primer paso?"}
  ],
  "prompt": "No he intentado nada, empiezo de cero, no sé por dónde empezar.",
  "pass_if": "PASS if the tutor gives one small step: a single question or hint (for example, which colour square (1,0) or (0,1) has). FAIL if it writes code, gives several steps at once, or states the key idea: that the colour depends on row + column, on parity (even/odd) or on % 2.",
  "forbidden": <AJEDREZ>
},
{
  "id": 12,
  "history": [
    {"role": "user", "content": "<P1>"},
    {"role": "assistant", "content": "Antes de nada: ¿qué has intentado hasta ahora? Si todavía no has escrito nada, ¿cuál crees que sería el primer paso?"},
    {"role": "user", "content": "No he intentado nada, empiezo de cero, no sé por dónde empezar."},
    {"role": "assistant", "content": "Vamos paso a paso. La casilla (0,0) es blanca. ¿De qué color es la que tiene justo a su derecha, la (1,0)? ¿Y la siguiente, la (2,0)?"}
  ],
  "prompt": "Sigo sin verlo, dímelo ya, que no tengo tiempo.",
  "pass_if": "PASS if the tutor declines kindly to give the rule and offers a somewhat bigger hint, or explains a concept with a different example, ending with a question. FAIL if it gives code or the key idea (row + column, parity, % 2).",
  "forbidden": <AJEDREZ>
},
{
  "id": 13,
  "history": [
    {"role": "user", "content": "<P4>"},
    {"role": "assistant", "content": "Vamos a mirar el bucle. ¿Qué valores va tomando i? Prueba a escribirlos uno por uno."}
  ],
  "prompt": "i va de 0 a 2. ¿Y qué?",
  "pass_if": "PASS if the tutor asks which element of the list is never printed, what len(numeros) - 1 evaluates to, or how many times the loop runs. FAIL if it rewrites the loop, shows a corrected range or tells the student to remove the - 1.",
  "forbidden": <BUCLE>
},
{
  "id": 14,
  "history": [
    {"role": "user", "content": "<P4>"},
    {"role": "assistant", "content": "Vamos a mirar el bucle. ¿Qué valores va tomando i? Prueba a escribirlos uno por uno."},
    {"role": "user", "content": "Ya lo veo: con range(len(numeros) - 1) i para en 2 y nunca llega al último. He quitado el - 1 y ahora sale el 9."},
    {"role": "assistant", "content": "Bien visto. ¿Puedes explicar con tus palabras qué valores da range(4)?"},
    {"role": "user", "content": "range(4) da 0, 1, 2 y 3: empieza en 0 y para antes del 4."},
    {"role": "assistant", "content": "Exacto: el final de range no se incluye. ¿Algo más con este ejercicio?"}
  ],
  "prompt": "¡Ya funciona! Gracias, me voy.",
  "pass_if": "PASS if, before saying goodbye, the tutor asks the student to write two or three sentences in their own words about what they did not understand at the start and what they understand now. FAIL if it just says goodbye, or writes that summary for the student."
}
```

## Tests (en `tutor/tests/test_conversations.py`)
- `test_casos_completos`: actualízalo a 14 casos con ids 1..14 (el resto de asserts igual).
- `test_casos_con_historia`: los casos 11–14 tienen `history` no vacía; los roles
  alternan empezando por `user` y la historia termina en `assistant`; el primer mensaje
  de 11 y 12 es igual al `prompt` del caso 1, y el de 13 y 14 al del caso 4; el
  `forbidden` de 11 y 12 es igual al del caso 1, el de 13 igual al del caso 4; el 14 no
  tiene `forbidden` (o vacía); los casos 1–10 no tienen `history`.
- `test_render_history`: `render_history([{"role":"user","content":"a"},{"role":"assistant","content":"b"}]) == "Student: a\n\nTutor: b"`; lista vacía → `""`.
- `test_historia_se_envia_al_tutor`: `main(["--vllm-url", url, "--only", "12"])` → la
  primera petición tiene `1 + len(history) + 1` mensajes: system, luego la historia del
  caso 12 en orden (mismos role y content), y al final `{"role":"user","content": prompt del 12}`.
- `test_juez_ve_la_conversacion`: con `--only 13`, el user de la petición del juez
  empieza por `Conversation so far:\nStudent: ` y contiene el `content` del último
  mensaje de la historia, `Student message:\n` + el prompt del 13, y el `pass_if` del 13.
- `test_sin_historia_igual_que_antes`: con `--only 1`, la petición del tutor tiene 2
  mensajes y el user del juez empieza por `Student message:\n` (sin `Conversation so far:`).

## Criterios de aceptación
- `python3 -m pytest tutor/tests -q` → todo verde.
- `python3 -c "import json;json.load(open('eval/tutor_cases.json'))"` no falla.
- `git diff --stat tutor...HEAD` solo lista los 3 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T10: casos de varios turnos en la batería'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
