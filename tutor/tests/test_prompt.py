import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = REPO_ROOT / "rag-api" / "templates" / "system_prompts" / "per_topic" / "TutorInformatica.txt"
INDEX_PATH = REPO_ROOT / "rag-api" / "templates" / "system_prompts" / "per_topic" / "INDEX.txt"


def test_prompt_existe_y_es_utf8():
    assert PROMPT_PATH.exists()
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert len(text) > 3000


def test_prompt_conserva_las_secciones():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    for section in (
        "# Language",
        "# How you help",
        "# What you do not do",
        "# What you do freely",
        "# By topic",
        "# Course material",
        "# Honesty",
        "# Tone",
        "# Hard rules",
        "# Examples",
        "# Before you send",
    ):
        assert section in lines, f"falta la sección {section!r} en su propia línea"


def test_prompt_tiene_el_cierre_de_la_fase_12():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    frase = "what they did not understand at the start, and what they understand now"
    assert frase in text
    assert "# How you help" in text
    assert "# What you do not do" in text
    idx_help = text.index("# How you help")
    idx_not = text.index("# What you do not do")
    idx_frase = text.index(frase)
    assert idx_help < idx_frase < idx_not


def test_prompt_menciona_fuente():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert "FUENTE:" in text


def test_prompt_prohibe_la_idea_clave():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    frase = "Do not state the key idea that solves the exercise"
    assert frase in text
    idx_seccion = text.index("# What you do not do")
    idx_solucion = text.index("Do not write the solution to an exercise")
    idx_frase = text.index(frase)
    idx_reescritura = text.index("Do not rewrite the student's code")
    assert idx_seccion < idx_solucion < idx_frase < idx_reescritura


def test_prompt_un_paso_cinco_frases():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    idx_help = text.index("# How you help")
    idx_not = text.index("# What you do not do")
    idx_frase = text.index("at most five sentences", idx_help)
    assert idx_help < idx_frase < idx_not
    assert "Each message should give one step, not several. End with a question" not in text


def test_prompt_revision_final_es_la_ultima_seccion():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    secciones = [line for line in text.splitlines() if line.startswith("# ")]
    assert secciones[-1] == "# Before you send"
    assert text.index("# Tone") < text.index("# Before you send")
    assert "these checks are for exercises" in text


def test_prompt_termina_en_un_salto():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_prompt_reglas_duras_al_principio():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    idx_goal = text.index("Your goal is that the student learns")
    idx_rules = text.index("# Hard rules")
    idx_language = text.index("# Language")
    assert idx_goal < idx_rules < idx_language
    first_hash = next(line for line in text.splitlines() if line.startswith("# "))
    assert first_hash == "# Hard rules"
    assert "not as a hint, not inside a question, not inside an example" in text
    assert "One step per message" in text


def test_prompt_ejemplos_antes_de_la_revision():
    text = PROMPT_PATH.read_text(encoding="utf-8")
    idx_tone = text.index("# Tone")
    idx_examples = text.index("# Examples")
    idx_send = text.index("# Before you send")
    assert idx_tone < idx_examples < idx_send
    bloque = text[idx_examples:idx_send]
    pos = -1
    for frase in (
        "es_bisiesto",
        "Bad reply:",
        "Good reply:",
        "function Saludar()",
        "Bad reply:",
        "Good reply:",
    ):
        nuevo = bloque.index(frase, pos + 1)
        assert nuevo > pos, f"{frase!r} no aparece en el orden esperado"
        pos = nuevo
    assert text.count("Why it is bad:") == 2


def test_prompt_solo_anade_lineas():
    ruta_rel = PROMPT_PATH.relative_to(REPO_ROOT).as_posix()
    resultado = subprocess.run(
        ["git", "diff", "--numstat", "tutor", "--", ruta_rel],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0 or not resultado.stdout.strip():
        pytest.skip("sin diff de tutor contra el prompt")
    borradas = resultado.stdout.split()[1]
    assert borradas == "0", f"se borraron {borradas} líneas del prompt"


def test_index_registra_el_tutor():
    text = INDEX_PATH.read_text(encoding="utf-8")
    assert any("TutorInformatica.txt" in line and "tutor-ari" in line for line in text.splitlines())
