# T01 — Prompt del tutor versionado en el repo

## Objetivo
Guardar el prompt de sistema del tutor como fuente de verdad en el repo, con una
línea nueva para que cada sesión acabe con el alumno explicando lo aprendido, y
registrarlo en `INDEX.txt`.

## Ficheros que puedes tocar (SOLO estos)
- `rag-api/templates/system_prompts/per_topic/TutorInformatica.txt` (nuevo)
- `rag-api/templates/system_prompts/per_topic/INDEX.txt` (añadir una línea)
- `tutor/tests/test_prompt.py` (nuevo)

## Pasos (TDD)
1. Escribe primero `tutor/tests/test_prompt.py` con los tests de abajo y ejecútalo:
   debe FALLAR (rojo).
2. Copia el prompt original tal cual:
   `cp /datos/Clases/tutor/tutor-prompt.md rag-api/templates/system_prompts/per_topic/TutorInformatica.txt`
   NO lo traduzcas: se queda en inglés.
3. En `TutorInformatica.txt`, dentro de la sección `# How you help`, justo DESPUÉS del
   párrafo que empieza por `When the student fixes something, ask them to explain`,
   añade una línea en blanco y este párrafo EXACTO:

   ```
   When the student says the problem is solved, or that they are leaving, ask them before saying goodbye to write two or three sentences in their own words: what they did not understand at the start, and what they understand now. Do not write that summary for them.
   ```
4. En `INDEX.txt`, en la tabla `Fichero -> id del workspace model`, añade al final
   (después de la línea de `Sostenibilidad.txt`) esta línea, alineada como las demás:

   ```
   TutorInformatica.txt -> tutor-ari               (Tutor Informática)  [sin Filter hasta la Fase 5; prompt en inglés a propósito]
   ```
5. Ejecuta los tests: deben PASAR (verde).

## Tests que debe contener `tutor/tests/test_prompt.py`
Usa `pathlib`; la raíz del repo es `Path(__file__).resolve().parents[2]`.
- `test_prompt_existe_y_es_utf8`: el fichero existe, se lee con `encoding="utf-8"` y
  tiene más de 3000 caracteres.
- `test_prompt_conserva_las_secciones`: contiene, cada una en su propia línea,
  `# Language`, `# How you help`, `# What you do not do`, `# What you do freely`,
  `# By topic`, `# Course material`, `# Honesty`, `# Tone`.
- `test_prompt_tiene_el_cierre_de_la_fase_12`: contiene la frase
  `what they did not understand at the start, and what they understand now` y esa
  frase aparece DESPUÉS de `# How you help` y ANTES de `# What you do not do`.
- `test_prompt_menciona_fuente`: contiene `FUENTE:`.
- `test_index_registra_el_tutor`: `INDEX.txt` tiene una línea que contiene a la vez
  `TutorInformatica.txt` y `tutor-ari`.

## Criterios de aceptación
- `python3 -m pytest tutor/tests/test_prompt.py -q` → 5 passed.
- `diff <(head -c 100 /datos/Clases/tutor/tutor-prompt.md) <(head -c 100 rag-api/templates/system_prompts/per_topic/TutorInformatica.txt)` no muestra diferencias.
- El resto del prompt es idéntico al original salvo el párrafo añadido
  (`diff /datos/Clases/tutor/tutor-prompt.md rag-api/templates/system_prompts/per_topic/TutorInformatica.txt`
  muestra solo líneas añadidas `>`).
- `git diff --stat tutor...HEAD` solo lista los 3 ficheros permitidos.

## Comando de verificación
```
python3 -m pytest tutor/tests -q
```

## Al terminar
`git add -A && git commit -m 'T01: prompt del tutor versionado con cierre de la Fase 12'`
(sin coautores). Informa con `hc send`: ficheros cambiados, salida de los tests, dudas.
