# T11 — Prompt del tutor: no revelar la idea clave, un paso por mensaje, revisión final

## Objetivo
En el servidor, el tutor revela la idea clave del ejercicio (p. ej. `(columna + fila) % 2`)
y da varios pasos en un mensaje. Se añaden tres cambios de texto al prompt, aprobados
por el profesor. El prompt está en inglés y sigue en inglés.

## Ficheros que puedes tocar (SOLO estos)
- `rag-api/templates/system_prompts/per_topic/TutorInformatica.txt`
- `tutor/tests/test_prompt.py`

## Cambios exactos en `TutorInformatica.txt`
Copia los textos EXACTAMENTE (cada párrafo es una sola línea, como el resto del fichero;
párrafos separados por una línea en blanco). No toques nada más.

1. Sección `# What you do not do`: justo DESPUÉS del párrafo que empieza por
   `Do not write the solution to an exercise` (y su línea en blanco), inserta este
   párrafo nuevo (seguido de una línea en blanco):
   ```
   Do not state the key idea that solves the exercise either: the formula, the relation, the condition or the operation the student has to discover (for example, telling them that a leap year is one divisible by 4 but not by 100, unless by 400). Finding that idea is the work of the exercise. This also holds inside examples: an example may illustrate a concept, but never with the operation that solves the exercise in hand.
   ```
   Queda entre ese párrafo y el que empieza por `Do not rewrite the student's code`.

2. Sección `# How you help`: sustituye la línea entera
   ```
   Each message should give one step, not several. End with a question or a small task the student can do right now.
   ```
   por
   ```
   Each message should give one step, not several: one question or one hint, at most five sentences. End with a single question or a small task the student can do right now. If the student says they do not know where to start, make the step smaller; do not give a bigger one.
   ```

3. Al FINAL del fichero, después de la sección `# Tone`, añade una línea en blanco y:
   ```
   # Before you send

   Check your reply before sending it. Does it contain the solution, the key idea, or a corrected version of their code? Remove it. Does it give more than one step? Keep only the first one. Does it end with exactly one question or small task? When the student asked for a concept explanation, a safety warning or a tool question, answer fully: these checks are for exercises.
   ```
   El fichero termina con un único salto de línea.

## Tests (en `tutor/tests/test_prompt.py`; no borres los existentes)
- En `test_prompt_conserva_las_secciones` añade `"# Before you send"` a la tupla.
- `test_prompt_prohibe_la_idea_clave`: el texto contiene
  `Do not state the key idea that solves the exercise`, y esa frase está después de
  `# What you do not do`, después de `Do not write the solution to an exercise` y antes
  de `Do not rewrite the student's code`.
- `test_prompt_un_paso_cinco_frases`: contiene `at most five sentences` entre
  `# How you help` y `# What you do not do`; y ya NO contiene
  `Each message should give one step, not several. End with a question`.
- `test_prompt_revision_final_es_la_ultima_seccion`: la última línea del fichero que
  empieza por `# ` es `# Before you send`, aparece después de `# Tone`, y el texto
  contiene `these checks are for exercises`.
- `test_prompt_termina_en_un_salto`: el texto termina en `"\n"` y no en `"\n\n"`.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_prompt.py -q` → todo verde (5 tests anteriores + 4 nuevos).
- `python3 -m pytest tutor/tests -q` → todo verde.
- `git diff tutor...HEAD -- rag-api/` solo muestra: 1 línea cambiada (paso 2) y líneas
  añadidas (pasos 1 y 3). Ninguna otra línea quitada.
- `git diff --stat tutor...HEAD` solo lista los 2 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T11: el prompt prohíbe la idea clave y limita cada mensaje a un paso'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
