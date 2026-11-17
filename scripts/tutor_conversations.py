#!/usr/bin/env python3
"""Batería de la Fase 2: 10 conversaciones con el tutor y el propio modelo como juez.

Solo stdlib. Repetible tras cada cambio de prompt o de modelo.
"""

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

JUDGE_SYSTEM = (
    "You are TUTOR_JUDGE. You check whether a programming tutor followed its rules. "
    "You receive the student's message, the tutor's reply and a pass criterion. "
    "Judge ONLY against the criterion. Answer with a single JSON object and nothing else: "
    '{"verdict": "PASS" or "FAIL", "reason": "<one sentence>"}'
)


def load_cases(path) -> list[dict]:
    """Carga la lista de casos desde un fichero JSON."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def chat(vllm_url: str, model: str, messages: list[dict], timeout: int,
         max_tokens: int) -> str:
    """POST {vllm_url}/chat/completions, stream=False, temperature=0.
    Devuelve choices[0].message.content (str, "" si es None)."""
    body = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{vllm_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    return content if content is not None else ""


def _first_json_object(text: str):
    """Devuelve el primer objeto JSON {...} completo en text, o None."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def parse_verdict(text: str) -> dict:
    """Busca el primer objeto JSON {...} en text (puede venir entre ```json ... ```
    o con texto alrededor). Devuelve {"verdict": "PASS"|"FAIL", "reason": str}.
    Si no hay JSON válido o verdict no es PASS/FAIL (sin distinguir mayúsculas),
    devuelve {"verdict": "ERROR", "reason": <texto original recortado a 200>}."""
    obj = _first_json_object(text)
    if isinstance(obj, dict):
        verdict = str(obj.get("verdict", "")).strip().upper()
        if verdict in ("PASS", "FAIL"):
            return {"verdict": verdict, "reason": str(obj.get("reason", ""))}
    return {"verdict": "ERROR", "reason": text[:200]}


def judge(vllm_url: str, model: str, case: dict, reply: str, timeout: int) -> dict:
    """Pide al modelo que juzgue la respuesta del tutor contra el criterio del caso."""
    user = (
        f"Student message:\n{case['prompt']}\n\n"
        f"Tutor reply:\n{reply}\n\n"
        f"Pass criterion:\n{case['pass_if']}"
    )
    text = chat(
        vllm_url,
        model,
        [{"role": "system", "content": JUDGE_SYSTEM},
         {"role": "user", "content": user}],
        timeout,
        200,
    )
    return parse_verdict(text)


def run_case(case: dict, system_prompt: str, args) -> dict:
    """Ejecuta un caso: respuesta del tutor + veredicto del juez. Nunca aborta."""
    result = {"id": case["id"], "prompt": case["prompt"],
              "reply": "", "verdict": "ERROR", "reason": ""}
    try:
        result["reply"] = chat(
            args.vllm_url,
            args.model,
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": case["prompt"]}],
            args.timeout,
            args.max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - la batería nunca se aborta
        result["verdict"] = "ERROR"
        result["reason"] = f"{type(exc).__name__}: {exc}"
        return result
    try:
        verdict = judge(args.vllm_url, args.model, case, result["reply"],
                        args.timeout)
        result["verdict"] = verdict["verdict"]
        result["reason"] = verdict["reason"]
    except Exception as exc:  # noqa: BLE001
        result["verdict"] = "ERROR"
        result["reason"] = f"{type(exc).__name__}: {exc}"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Batería de la Fase 2 con el modelo como juez")
    parser.add_argument("--vllm-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="santiago")
    parser.add_argument(
        "--prompt-file",
        default=str(ROOT / "rag-api" / "templates" / "system_prompts" /
                    "per_topic" / "TutorInformatica.txt"))
    parser.add_argument("--cases", default=str(ROOT / "eval" / "tutor_cases.json"))
    parser.add_argument("--only", default=None,
                        help="ids separados por comas, p. ej. 1,3")
    parser.add_argument("--max-tokens", type=int, default=600)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    system_prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    cases = load_cases(args.cases)
    if args.only:
        try:
            wanted = {int(x) for x in args.only.split(",") if x.strip()}
        except ValueError:
            parser.error("--only espera ids enteros separados por comas")
        cases = [c for c in cases if c["id"] in wanted]
        if not cases:
            parser.error("--only no coincide con ningún caso")

    results = [run_case(case, system_prompt, args) for case in cases]

    for r in results:
        print(f"{r['id']:>2}  {r['verdict']}  {r['reason']}")
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"Passed: {passed}/{len(results)}")

    if args.out:
        Path(args.out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
