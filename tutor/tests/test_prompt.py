from pathlib import Path

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
    idx_frase = text.index("at most five sentences")
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


def test_index_registra_el_tutor():
    text = INDEX_PATH.read_text(encoding="utf-8")
    assert any("TutorInformatica.txt" in line and "tutor-ari" in line for line in text.splitlines())
