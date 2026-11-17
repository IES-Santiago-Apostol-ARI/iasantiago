"""Tests de tutor/docs_log.py (T07, Fase 12)."""

from datetime import date

from tutor.docs_log import DocAccess, distinct_openings, main, parse_line, summarize

LINEA_EJEMPLO = (
    '2026-11-17T10:15:02+01:00 alumno1@santiagoapostol.net '
    '"/docs/Programming/Tema%201.pdf" 206'
)


def test_parse_line_valida():
    acc = parse_line(LINEA_EJEMPLO)
    assert acc == DocAccess(
        email="alumno1@santiagoapostol.net",
        document="Programming/Tema 1.pdf",
        day=date(2026, 11, 17),
    )


def test_quita_query_y_decodifica():
    line = '2026-11-17T10:15:02+01:00 a@x "/docs/Quimica/a%C3%B1o.PDF?x=1" 200'
    acc = parse_line(line)
    assert acc is not None
    assert acc.document == "Quimica/año.PDF"


def test_descarta_lo_que_no_cuenta():
    casos = [
        '2026-11-17T10:15:02+01:00 - "/docs/P/t.pdf" 200',  # email '-'
        '2026-11-17T10:15:02+01:00 a@x "/docs/P/t.pdf" 401',  # estado 401
        '2026-11-17T10:15:02+01:00 a@x "/docs/P/t.pdf" 404',  # estado 404
        '2026-11-17T10:15:02+01:00 a@x "/docs/Programming/" 200',  # carpeta
        '2026-11-17T10:15:02+01:00 a@x "/docs/P/t.png" 200',  # no .pdf
        '2026-11-17T10:15:02+01:00 a@x "/api/x.pdf" 200',  # fuera de /docs/
        "",  # línea vacía
        "esto no es una línea del log",  # basura
    ]
    for linea in casos:
        assert parse_line(linea) is None, linea


def test_peticiones_parciales_cuentan_una_vez():
    lineas = [
        '2026-11-17T10:15:02+01:00 a@x "/docs/P/t.pdf" 206' for _ in range(5)
    ]
    assert len(distinct_openings(lineas)) == 1


def test_summarize_cuenta_dias_distintos():
    lineas = [
        '2026-11-10T10:00:00+01:00 a@x "/docs/P/t1.pdf" 200',
        '2026-11-10T11:00:00+01:00 a@x "/docs/P/t1.pdf" 206',
        '2026-11-12T09:00:00+01:00 a@x "/docs/P/t1.pdf" 200',
        '2026-11-10T10:30:00+01:00 a@x "/docs/P/t2.pdf" 200',
    ]
    assert summarize(lineas) == {"a@x": {"P/t1.pdf": 2, "P/t2.pdf": 1}}


def test_main_csv_y_filtro_de_fechas(tmp_path, capsys):
    f = tmp_path / "docs_access.log"
    f.write_text(
        '2026-11-10T10:00:00+01:00 a@x "/docs/P/t.pdf" 200\n'
        '2026-11-15T10:00:00+01:00 a@x "/docs/P/t.pdf" 206\n'
        '2026-11-20T10:00:00+01:00 a@x "/docs/P/t.pdf" 200\n',
        encoding="utf-8",
    )
    rc = main([str(f), "--since", "2026-11-12", "--until", "2026-11-18"])
    out = capsys.readouterr().out
    assert rc == 0
    lineas = out.strip().splitlines()
    assert lineas[0] == "email,documento,dias"
    assert len(lineas) == 2
    assert lineas[1] == 'a@x,P/t.pdf,1'


def test_main_fichero_inexistente(capsys):
    rc = main(["/no/existe/docs_access.log"])
    assert rc == 1
    assert capsys.readouterr().err


def test_nginx_conf_tiene_el_log_de_docs():
    conf = open("nginx/nginx.conf", encoding="utf-8").read()
    assert "log_format docs" in conf
    assert "access_log /var/log/nginx/docs_access.log docs;" in conf
    assert conf.count("auth_request_set $ow_auth_email") >= 2
    assert conf.index("access_log /var/log/nginx/docs_access.log docs;") > conf.index(
        "location /docs/ {"
    )
