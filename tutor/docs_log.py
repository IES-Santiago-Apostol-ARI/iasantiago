"""Parser del log de /docs/ de nginx (T07, Fase 12).

Cada línea del log (formato `docs` en nginx/nginx.conf) tiene la forma:

    2026-11-17T10:15:02+01:00 alumno1@santiagoapostol.net "/docs/Programming/Tema%201.pdf" 206

El visor de PDF hace peticiones parciales (206) repetidas del mismo documento;
las aperturas distintas se cuentan como (alumno, documento, día).
"""

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable
from urllib.parse import unquote

# $time_iso8601 $ow_auth_email "$request_uri" $status
_LINE_RE = re.compile(r'^(\S+) (\S+) "([^"]*)" (\d+)$')


@dataclass(frozen=True)
class DocAccess:
    email: str
    document: str   # ruta decodificada SIN el prefijo /docs/ y sin query
    day: date       # fecha tal como viene en el timestamp (hora local del servidor)


def parse_line(line: str) -> DocAccess | None:
    """Devuelve la apertura codificada en la línea, o None si no cuenta."""
    if not line:
        return None
    m = _LINE_RE.match(line.strip())
    if not m:
        return None
    timestamp, email, uri, status = m.groups()
    if not email or email == "-":
        return None
    if status not in ("200", "206", "304"):
        return None
    if not uri.startswith("/docs/"):
        return None
    # Sin query ni fragmento, decodificada, sin el prefijo /docs/
    path = unquote(uri.split("?", 1)[0].split("#", 1)[0])
    document = path[len("/docs/"):]
    if not document or document.endswith("/"):
        return None
    if not document.rsplit(".", 1)[-1].lower() == "pdf":
        return None
    try:
        day = datetime.fromisoformat(timestamp).date()
    except ValueError:
        return None
    return DocAccess(email=email, document=document, day=day)


def distinct_openings(lines: Iterable[str]) -> set[DocAccess]:
    """Aperturas distintas (alumno, documento, día), ignorando 206 repetidos."""
    return {acc for acc in (parse_line(line) for line in lines) if acc is not None}


def summarize(lines: Iterable[str]) -> dict[str, dict[str, int]]:
    """email -> {documento -> nº de días distintos en que lo abrió}."""
    result: dict[str, dict[str, int]] = {}
    for acc in distinct_openings(lines):
        result.setdefault(acc.email, {}).setdefault(acc.document, set()).add(acc.day)
    return {
        email: {doc: len(dias) for doc, dias in docs.items()}
        for email, docs in result.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m tutor.docs_log",
        description="Resumen de aperturas de PDF de /docs/ por alumno.",
    )
    parser.add_argument("fichero", help="fichero docs_access.log de nginx")
    parser.add_argument("--since", type=date.fromisoformat, default=None)
    parser.add_argument("--until", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)

    try:
        with open(args.fichero, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"error: no se puede leer {args.fichero}: {e}", file=sys.stderr)
        return 1

    openings = distinct_openings(lines)
    if args.since is not None:
        openings = {a for a in openings if a.day >= args.since}
    if args.until is not None:
        openings = {a for a in openings if a.day <= args.until}

    by_email_doc: dict[tuple[str, str], set[date]] = {}
    for acc in openings:
        by_email_doc.setdefault((acc.email, acc.document), set()).add(acc.day)

    writer = csv.writer(sys.stdout)
    writer.writerow(["email", "documento", "dias"])
    for (email, document) in sorted(by_email_doc):
        writer.writerow([email, document, len(by_email_doc[(email, document)])])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
