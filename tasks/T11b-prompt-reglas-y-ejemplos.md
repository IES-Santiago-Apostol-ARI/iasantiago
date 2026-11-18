# T11b — Prompt del tutor: reglas duras al principio y ejemplos de respuesta buena/mala

## Objetivo
Tras T11, la batería en el servidor da 11/14: el tutor sigue revelando la idea clave
(casos 1 y 11) y da el arreglo de CSS (caso 10). Segunda y última ronda de prompt,
aprobada por el profesor: un bloque de reglas al principio y una sección de ejemplos
antes de la revisión final. El prompt sigue en inglés; los diálogos de ejemplo, en español.

## Ficheros que puedes tocar (SOLO estos)
- `rag-api/templates/system_prompts/per_topic/TutorInformatica.txt`
- `tutor/tests/test_prompt.py`

## Cambios exactos en `TutorInformatica.txt`
Solo se AÑADEN líneas; no cambies ni borres ninguna existente. Copia los bloques
EXACTAMENTE, línea por línea, con las líneas en blanco que se ven.

### A. Sección `# Hard rules`
Insértala justo DESPUÉS del párrafo que empieza por `Your goal is that the student learns`
(y su línea en blanco), y ANTES de `# Language`. Bloque a insertar (termina con una línea
en blanco antes de `# Language`):
```
# Hard rules

These rules come before everything else in this prompt.

1. Never write the solution, the code that fixes the problem, or the key idea that solves the exercise (the formula, condition, property or operation the student has to find): not as a hint, not inside a question, not inside an example.
2. One step per message: one question or one small hint, at most five sentences.
3. Exceptions: concept explanations the student asks for, safety warnings and tool questions are answered fully.

```

### B. Sección `# Examples`
Insértala justo ANTES de `# Before you send` (después de la sección `# Tone` y su línea
en blanco). Bloque a insertar (termina con una línea en blanco antes de `# Before you send`):
```
# Examples

These show the difference between a reply that helps the student learn and one that does their work for them. They use exercises from outside the course on purpose: apply the same pattern to any exercise.

Student: "Tengo que hacer una función es_bisiesto(año) y no sé por dónde empezar."
Bad reply: "Un año es bisiesto si es divisible entre 4 y no entre 100, salvo que lo sea entre 400. Prueba con año % 4 == 0 y ve añadiendo las otras condiciones."
Why it is bad: it gives the key idea and the operation, so nothing is left for the student to discover.
Good reply: "Vamos por partes. ¿Sabes qué regla decide si un año es bisiesto? Si no, búscala y cuéntamela con tus palabras: ese es el primer paso."

Student: "Mi botón no hace nada: `<button onclick="saludar()">Hola</button>` y en el script `function Saludar() { alert('hola'); }`"
Bad reply: "El problema es la mayúscula: cambia la función a `function saludar()` y funcionará."
Why it is bad: it finds the bug and writes the fix.
Good reply: "Abre la consola del navegador con F12 y pulsa el botón. ¿Aparece algún mensaje en rojo? Léelo y dime qué crees que significa."

```
`# Before you send` sigue siendo la última sección y el fichero termina con un único `\n`.

## Tests (en `tutor/tests/test_prompt.py`; no borres ni cambies los existentes salvo lo indicado)
- En `test_prompt_conserva_las_secciones` añade `"# Hard rules"` y `"# Examples"` a la tupla.
- `test_prompt_reglas_duras_al_principio`: `# Hard rules` aparece después de
  `Your goal is that the student learns` y antes de `# Language`; es la primera línea del
  fichero que empieza por `# `; el texto contiene
  `not as a hint, not inside a question, not inside an example` y `One step per message`.
- `test_prompt_ejemplos_antes_de_la_revision`: `# Examples` aparece después de `# Tone`
  y antes de `# Before you send`, y entre `# Examples` y `# Before you send` están, en
  este orden: `es_bisiesto`, `Bad reply:`, `Good reply:`, `function Saludar()`,
  `Bad reply:`, `Good reply:`. Además `Why it is bad:` aparece exactamente 2 veces en el fichero.
- `test_prompt_solo_anade_lineas`: usa
  `subprocess.run(["git", "diff", "--numstat", "tutor", "--", <ruta relativa del prompt>], cwd=ROOT, capture_output=True, text=True)`;
  si `returncode != 0` o la salida está vacía, `pytest.skip(...)`; si no, la segunda
  columna (líneas borradas) es `0`.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_prompt.py -q` → todo verde (9 anteriores + 3 nuevos).
- `python3 -m pytest tutor/tests -q` → todo verde.
- `git diff tutor...HEAD -- rag-api/` solo tiene líneas añadidas (ninguna `-` salvo la cabecera).
- `git diff --stat tutor...HEAD` solo lista los 2 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T11b: reglas duras al principio y ejemplos en el prompt del tutor'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
