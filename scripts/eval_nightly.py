#!/usr/bin/env python3
"""Tirada diaria de evaluación offline contra los nueve golden sets por tema.

Sustituye al cuerpo que traía el service systemd desde octubre de 2025, que
**nunca llegó a completar una tirada** (ver FINDINGS.md §6.9). Aquel script
tenía cuatro cosas mal a la vez, y conviene dejarlas escritas para no repetirlas:

  1. Sus dos casos apuntaban a `topics/Electronics/sample1.pdf` y
     `topics/Chemistry/sample1.pdf`, que no existen. `Electronics` ni siquiera
     está en TOPIC_LABELS.
  2. Mandaba `relevant_files`, de antes de que la métrica pasara a página
     (§3.1). Los golden sets de verdad usan `relevant_pages` ("fichero.pdf#87").
  3. No mandaba `Authorization: Bearer`, y el endpoint depende de
     `verify_api_key`. Habría sido 401 aunque el stack estuviese arriba.
  4. Leía `agg["Recall@1"]`, pero `aggregate_eval` devuelve las métricas
     anidadas bajo `pages` y `files`. Todas las columnas habrían salido vacías.

Se excluyen a propósito dos ficheros de `eval/`:

  - `golden_short.json`: su propia cabecera dice que sus R@k son un suelo, no la
    calidad del sistema. Sirve para la comparación pareada BM25↔híbrido (§7.5),
    no como línea base.
  - `golden_chemistry_docling.json`: verificación puntual de la reparación
    Docling (§6.8-bis). Mezclarlo con la línea base sesga la media de Chemistry.

La métrica que manda es `pages`; `files` es secundaria y gruesa (§ docstring de
`aggregate_eval`).
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
EVAL_DIR = RAIZ / "eval"
HISTORICO = EVAL_DIR / "history.csv"
RESUMEN = EVAL_DIR / "eval_summary.csv"
URL = "http://127.0.0.1:8001/v1/eval/offline"

# Explícitos, no un glob: un glob se tragaría en silencio cualquier golden set
# nuevo o de usar y tirar que alguien deje en eval/, y la línea base dejaría de
# ser comparable entre días sin que nadie lo note.
GOLDEN_SETS = [
    "golden_afd.json",
    "golden_chemistry.json",
    "golden_dibujo.json",
    "golden_electricidad.json",
    "golden_fol.json",
    "golden_latin.json",
    "golden_mecanica.json",
    "golden_programming.json",
    "golden_sostenibilidad.json",
]

# Una tirada completa son minutos (130 consultas por retrieval + reranker, que
# corre en CPU). El margen real lo fija la ventana del cron de horario escolar.
TIMEOUT_S = 2400


def lee_api_key() -> str:
    """OPENAI_API_KEY del entorno, y si no del .env (el service no lo carga)."""
    clave = os.getenv("OPENAI_API_KEY")
    if clave:
        return clave
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea.startswith("OPENAI_API_KEY="):
                return linea.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("ERROR: no encuentro OPENAI_API_KEY ni en el entorno ni en .env")


def carga_casos() -> list:
    casos, faltan = [], []
    for nombre in GOLDEN_SETS:
        ruta = EVAL_DIR / nombre
        if not ruta.exists():
            faltan.append(nombre)
            continue
        casos.extend(json.loads(ruta.read_text(encoding="utf-8")))
    # Un golden set que desaparece cambia la línea base en silencio y el R@k del
    # día siguiente parece una regresión. Mejor no medir que medir otra cosa.
    if faltan:
        sys.exit(f"ERROR: faltan golden sets {faltan}; la línea base no es comparable")
    return casos


def main() -> int:
    casos = carga_casos()
    print(f"Enviando {len(casos)} casos de {len(GOLDEN_SETS)} golden sets a {URL}")

    r = requests.post(
        URL,
        json=casos,
        headers={"Authorization": f"Bearer {lee_api_key()}"},
        timeout=TIMEOUT_S,
    )
    r.raise_for_status()
    salida = r.json()

    agg = salida["aggregate"]
    pages, files = agg.get("pages", {}), agg.get("files", {})
    print(json.dumps({"aggregate": agg, "config": salida.get("config")},
                     ensure_ascii=False, indent=2))

    fila = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n": agg.get("n"),
        "n_pages": pages.get("n"),
        "page_tolerance": agg.get("page_tolerance"),
        "duplicate_groups": agg.get("duplicate_groups"),
        "pages_R@1": pages.get("Recall@1"),
        "pages_R@3": pages.get("Recall@3"),
        "pages_R@5": pages.get("Recall@5"),
        "pages_R@10": pages.get("Recall@10"),
        "pages_MRR": pages.get("MRR"),
        "files_R@1": files.get("Recall@1"),
        "files_R@3": files.get("Recall@3"),
        "files_R@5": files.get("Recall@5"),
        "files_MRR": files.get("MRR"),
        "embed_model": (salida.get("config") or {}).get("embed_model"),
        "rerank": (salida.get("config") or {}).get("rerank"),
        "final_topk": (salida.get("config") or {}).get("final_topk"),
    }

    # history.csv se AÑADE: el eval_summary.csv de antes se pisaba en cada
    # tirada, así que sólo existía la foto del día y ninguna regresión era
    # visible como tal. RESUMEN se mantiene, con la última tirada, porque el
    # Makefile y la costumbre lo esperan ahí.
    nuevo = not HISTORICO.exists()
    with HISTORICO.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fila))
        if nuevo:
            w.writeheader()
        w.writerow(fila)
    with RESUMEN.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fila))
        w.writeheader()
        w.writerow(fila)

    print(f"[OK] {HISTORICO} (+1 fila) y {RESUMEN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
