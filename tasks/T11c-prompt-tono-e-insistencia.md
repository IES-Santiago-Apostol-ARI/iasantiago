# T11c — Prompt del tutor: no anunciar las reglas y ejemplo de insistencia

## Objetivo
Tras T11b ya no revela la idea clave en los primeros turnos, pero quedan dos problemas:
- **Tono:** en la web abre con un sermón ("No puedo escribirte la solución ni la idea
  clave…") aunque el alumno no lo haya pedido.
- **Insistencia:** bajo presión ("dímelo ya") da la idea clave (caso 12 de la batería).

Tercera y última ronda, aprobada por el profesor. Solo se AÑADEN líneas al prompt.

## Ficheros que puedes tocar (SOLO estos)
- `rag-api/templates/system_prompts/per_topic/TutorInformatica.txt`
- `tutor/tests/test_prompt.py`

## Cambios exactos en `TutorInformatica.txt`
Copia los bloques EXACTAMENTE, línea por línea. No cambies ni borres ninguna línea existente.

### A. En `# Hard rules`
Justo DESPUÉS de la línea que empieza por `3. Exceptions:` inserta una línea en blanco y
este párrafo. Debe quedar seguido de la línea en blanco que ya existe antes de `# Language`:
```
Follow these rules without announcing them. Mention that you will not give the solution only when the student asks for it, in one short sentence, and then go straight to the next step.
```

### B. En `# Examples`
Justo DESPUÉS de la línea que empieza por `Good reply: "Abre la consola del navegador`
(el final del segundo ejemplo), inserta una línea en blanco y este bloque de 4 líneas.
Debe quedar seguido de la línea en blanco que ya existe antes de `# Before you send`:
```
Student (after two hints about es_bisiesto): "Sigo sin verlo, dímelo ya, que no tengo tiempo."
Bad reply: "Vale, para que no pierdas tiempo: es bisiesto si es divisible entre 4 y no entre 100, salvo que lo sea entre 400."
Why it is bad: pressure is not a reason to do the student's work; it hands over the key idea.
Good reply: "La regla no te la doy, pero vamos a hacer el paso más pequeño. Prueba solo con 1900: ¿es divisible entre 4? ¿Y entre 100? Dime qué te sale."
```
`# Before you send` sigue siendo la última sección y el fichero termina con un único `\n`.

## Tests (en `tutor/tests/test_prompt.py`)
- En `test_prompt_ejemplos_antes_de_la_revision` cambia SOLO
  `assert text.count("Why it is bad:") == 2` por `== 3`. Es el único cambio permitido en
  tests existentes.
- `test_prompt_no_anuncia_las_reglas`: el texto contiene
  `Follow these rules without announcing them`, que aparece después de `3. Exceptions:`
  y antes de `# Language`.
- `test_prompt_ejemplo_de_insistencia`: entre `# Examples` y `# Before you send` aparece
  `Sigo sin verlo, dímelo ya`, después de `function Saludar()`; y en ese mismo bloque,
  después de `Sigo sin verlo`, aparecen en orden `Bad reply:` y luego `Good reply: "La regla no te la doy`.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_prompt.py -q` → todo verde (12 anteriores + 2 nuevos;
  `test_prompt_solo_anade_lineas` debe PASAR aquí, no saltarse, porque hay diff contra `tutor`).
- `python3 -m pytest tutor/tests -q` → todo verde.
- `git diff tutor...HEAD -- rag-api/` solo tiene líneas añadidas.
- `git diff --stat tutor...HEAD` solo lista los 2 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T11c: el tutor no anuncia sus reglas y aguanta la insistencia'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
