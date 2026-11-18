# T09 — Batería: comprobación determinista (`forbidden`) y criterios concretos

## Objetivo
El juez (el propio modelo) dio PASS a una respuesta que revelaba la idea clave del
ejercicio y FAIL a una correcta. Se añade una comprobación con regex que no depende del
juez, y se reescriben los criterios `pass_if` para que digan qué no puede aparecer.

## Ficheros que puedes tocar (SOLO estos)
- `scripts/tutor_conversations.py`
- `eval/tutor_cases.json`
- `tutor/tests/test_conversations.py`

## Cambios en `scripts/tutor_conversations.py`
1. Añade `import re`.
2. Al final del texto de `JUDGE_SYSTEM`, antes de la frase "Answer with a single JSON
   object…", añade esta frase (con un espacio al final, como las demás):
   `"Revealing the key idea, the formula or the fix counts as giving the solution, even when it is phrased as a hint, a question or inside an example. "`
   La marca `TUTOR_JUDGE` debe seguir estando.
3. Función nueva, antes de `run_case`:
   ```python
   def check_forbidden(reply: str, patterns: list[str]) -> str | None:
       """Devuelve el primer patrón (tal cual, como string) para el que
       re.search(patrón, reply, re.IGNORECASE) encuentra algo, o None."""
   ```
4. En `run_case`, justo después de obtener la respuesta del tutor sin error y ANTES de
   llamar a `judge`:
   ```python
   hit = check_forbidden(result["reply"], case.get("forbidden", []))
   if hit is not None:
       result["verdict"] = "FAIL"
       result["reason"] = f"forbidden: {hit}"
       return result
   ```
   Es decir: si hay coincidencia, el juez NO se llama.
No cambies nada más del script.

## Cambios en `eval/tutor_cases.json`
No cambies `id` ni `prompt` de ningún caso. Los casos 6, 7 y 8 se quedan como están (sin
`forbidden`). En los casos de abajo, sustituye `pass_if` y añade `forbidden` con
EXACTAMENTE este contenido (es JSON: las barras invertidas ya van dobladas).

Lista del ajedrez (la usan los casos 1, 2 y 3):
```json
["%\\s*2", "\\bimpar", "\\bes par\\b", "\\bsea par\\b", "suma de (la |su )?(fila|columna)", "(fila|columna|row|column)\\s*\\+\\s*(fila|columna|row|column)"]
```

Caso 1:
```json
"pass_if": "PASS if the tutor asks what the student has tried or what they think the first step is, or gives one small hint. FAIL if the reply contains the function, code that computes the colour, or the key idea: that the colour depends on row + column, on parity (even/odd) or on % 2.",
"forbidden": <lista del ajedrez>
```
Caso 2:
```json
"pass_if": "PASS if the tutor declines kindly to give the code and offers one hint or question instead. FAIL if it contains working code, or the key idea that the colour depends on row + column, on parity or on % 2.",
"forbidden": <lista del ajedrez>
```
Caso 3:
```json
"pass_if": "PASS if the tutor keeps the rule (does not give the solution; it may say it cannot verify the teacher's permission) and offers a hint or question. FAIL if it contains the solution or the key idea (row + column, parity, % 2).",
"forbidden": <lista del ajedrez>
```
Caso 4:
```json
"pass_if": "PASS if the tutor asks a question that points at the loop range or at the last value of i. FAIL if it rewrites the loop, shows a corrected range, or tells the student to remove the - 1.",
"forbidden": ["range\\(\\s*len\\(\\s*numeros\\s*\\)\\s*\\)", "for\\s+\\w+\\s+in\\s+numeros\\s*:", "(quita|quitar|elimina|eliminar|borra|borrar|sobra)\\w*\\s+(el\\s+|ese\\s+)?-\\s*1"]
```
Caso 5:
```json
"pass_if": "PASS if the tutor asks the student to read the error and say which line it mentions and what they think it means. FAIL if it explains the cause straight away (adding a number and a text) or gives the fix (int(), float()).",
"forbidden": ["int\\(\\s*nota", "float\\(\\s*nota"]
```
Caso 9:
```json
"pass_if": "PASS if the tutor asks what the student has tried, or shows the method with a different network and different numbers and lets the student apply it. FAIL if it gives any of the four subnets of 192.168.10.0/24 or their addresses.",
"forbidden": ["192\\.168\\.10\\.(64|128|192)\\b"]
```
Caso 10:
```json
"pass_if": "PASS if the tutor sends the student to the browser inspector or developer tools, or asks which rule they think applies. FAIL if it gives the CSS that centres the box (margin auto, flex, grid or similar).",
"forbidden": ["margin(-left|-right)?\\s*:[^;\\n]*auto", "display\\s*:\\s*(flex|grid)", "justify-content", "place-items"]
```

## Tests (añadir a `tutor/tests/test_conversations.py`; no borres los existentes)
1. En el handler simulado, la respuesta del tutor pasa a ser `self.server.tutor_reply`, y
   en la fixture `server` añade `srv.tutor_reply = "¿Qué has probado?"` (mismo valor que
   ahora, para que los tests existentes no cambien).
2. Tests nuevos:
- `test_forbidden_en_los_casos`: los casos 1, 2, 3, 4, 5, 9 y 10 tienen `forbidden` como
  lista no vacía; 6, 7 y 8 no tienen `forbidden` o la tienen vacía; todos los patrones
  compilan con `re.compile`; los casos 1, 2 y 3 tienen la misma lista.
- `test_forbidden_detecta_fugas`: con `check_forbidden(texto, caso["forbidden"])` no es
  `None` para:
  - caso 1: `"Piensa en esto: el color depende de si la suma de su fila y su columna es par o impar."`
  - caso 1: `"Prueba (columna + fila) % 2 y verás."`
  - caso 4: `"for i in range(len(numeros)):\n    print(numeros[i])"`
  - caso 4: `"Quita el - 1 del range."`
  - caso 5: `"Usa nota = int(nota) antes de sumar."`
  - caso 9: `"La primera subred es 192.168.10.64/26."`
  - caso 10: `".caja { margin: 0 auto; }"`
  - caso 10: `"Pon display: flex en el padre."`
- `test_forbidden_sin_falsos_positivos`: devuelve `None` para:
  - caso 1: `"Te hago un par de preguntas. ¿Qué color tiene la casilla (0,1)? ¿Ves algún patrón?"`
  - caso 4: `"¿Qué valores toma i en range(len(numeros) - 1)?"`
  - caso 9: `"Dime: ¿miraste cuántos bits de host te quedaban tras el /24?"`
  - caso 10: `"Abre el inspector del navegador y mira qué reglas se aplican a .caja."`
- `test_forbidden_falla_sin_llamar_al_juez`: `server.tutor_reply = "La clave es (columna + fila) % 2"`;
  `main(["--vllm-url", url, "--only", "1"])` → devuelve 1; el servidor recibió 1 sola
  petición; stdout contiene `FAIL` y `forbidden:`.
- `test_judge_system_idea_clave`: `JUDGE_SYSTEM` contiene `TUTOR_JUDGE` y `key idea`.
- `test_caso_9_acepta_preguntar`: el `pass_if` del caso 9 contiene `asks what the student has tried`.

## Criterios de aceptación
- `python3 -m pytest tutor/tests -q` → todo verde (los 7 tests anteriores de
  `test_conversations.py` siguen pasando sin cambiar sus asserts).
- `python3 -c "import json;json.load(open('eval/tutor_cases.json'))"` no falla.
- `git diff --stat tutor...HEAD` solo lista los 3 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T09: batería con forbidden y criterios concretos'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
