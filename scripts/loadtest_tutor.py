#!/usr/bin/env python3
"""Load test for the tutor: N simulated students sending one message at once.

Run it ON THE SERVER, where vLLM (port 8000) and rag-api (port 8001) listen.
It needs Python 3 only, no extra packages. See tasks/PLAN.md and the tutor plan, Phase 2.

  # 15 students, tutor prompt, no documents
  python3 scripts/loadtest_tutor.py --prompt-file rag-api/templates/system_prompts/per_topic/TutorInformatica.txt

  # the same, with retrieval before each message, as the Filter does
  RAG_KEY=<OPENAI_API_KEY from .env> python3 scripts/loadtest_tutor.py \
      --prompt-file rag-api/templates/system_prompts/per_topic/TutorInformatica.txt --topic Programming

Each student does: (optional) POST /retrieve, then a streamed chat completion.
The script goes straight to vLLM and rag-api, so it does not create users or
chats in Open WebUI, and it does not measure Open WebUI's own overhead.
"""

import argparse
import json
import os
import statistics
import threading
import time
import urllib.error
import urllib.request

QUESTIONS = [
    "No entiendo por qué mi bucle for se salta el último elemento de la lista.",
    "Me sale IndexError: list index out of range y no sé qué significa.",
    "¿Qué diferencia hay entre = y == en Python?",
    "Mi LED no enciende. El código compila bien. ¿Qué puede ser?",
    "¿Cómo se calcula la máscara de una subred con 30 equipos?",
    "No consigo centrar un div en la página con CSS.",
    "¿Qué es una función y para qué sirve el return?",
    "Mi página no hace nada cuando pulso el botón, tengo un onclick.",
    "¿Qué hace exactamente pinMode en Arduino?",
    "¿Para qué sirve la puerta de enlace en una red?",
    "Mi while no termina nunca, ¿cómo lo depuro?",
    "¿Qué diferencia hay entre una lista y un diccionario?",
    "El Serial.println no muestra nada en el monitor serie.",
    "¿Qué significa el error NameError: name 'x' is not defined?",
    "¿Cuál es la diferencia entre margin y padding?",
]


def post_json(url, payload, headers, timeout):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    return urllib.request.urlopen(req, timeout=timeout)


def student(i, args, system_prompt, start, results):
    r = {"id": i, "ok": False, "error": "", "retrieve_s": None,
         "ttft_s": None, "total_s": None, "tokens": 0}
    results[i] = r
    question = QUESTIONS[i % len(QUESTIONS)]
    start.wait()
    t0 = time.perf_counter()
    try:
        content = question
        if args.topic:
            headers = {"Authorization": f"Bearer {args.rag_key}"}
            with post_json(f"{args.rag_url}/retrieve",
                           {"query": question, "topic": args.topic},
                           headers, args.timeout) as resp:
                context = json.load(resp).get("context") or ""
            r["retrieve_s"] = time.perf_counter() - t0
            if context:
                content = f"{context}\n\n{question}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})
        payload = {"model": args.model, "messages": messages, "stream": True,
                   "max_tokens": args.max_tokens,
                   "stream_options": {"include_usage": True}}
        t1 = time.perf_counter()
        chunks = 0
        with post_json(f"{args.vllm_url}/chat/completions", payload, {},
                       args.timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                event = json.loads(body)
                usage = event.get("usage")
                if usage:
                    r["tokens"] = usage.get("completion_tokens") or r["tokens"]
                for choice in event.get("choices") or []:
                    if (choice.get("delta") or {}).get("content"):
                        chunks += 1
                        if r["ttft_s"] is None:
                            r["ttft_s"] = time.perf_counter() - t1
        if not r["tokens"]:
            r["tokens"] = chunks
        r["total_s"] = time.perf_counter() - t0
        r["ok"] = r["ttft_s"] is not None
        if not r["ok"]:
            r["error"] = "no text received"
    except urllib.error.HTTPError as e:
        r["error"] = f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}"
    except Exception as e:  # report every failure per student, never abort the run
        r["error"] = f"{type(e).__name__}: {e}"


def fmt(values):
    if not values:
        return "    -      -      -"
    return f"{statistics.median(values):5.1f}  {max(values):5.1f}  {min(values):5.1f}"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--students", type=int, default=15)
    p.add_argument("--vllm-url", default="http://127.0.0.1:8000/v1")
    p.add_argument("--model", default="santiago")
    p.add_argument("--prompt-file", help="system prompt, e.g. tutor-prompt.md")
    p.add_argument("--max-tokens", type=int, default=300)
    p.add_argument("--topic", help="call /retrieve with this topic before each chat")
    p.add_argument("--rag-url", default="http://127.0.0.1:8001")
    p.add_argument("--rag-key", default=os.environ.get("RAG_KEY", ""))
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args()

    if args.topic and not args.rag_key:
        p.error("--topic needs the rag-api key: set RAG_KEY or pass --rag-key")
    system_prompt = ""
    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as f:
            system_prompt = f.read()

    results = {}
    start = threading.Event()
    threads = [threading.Thread(target=student,
                                args=(i, args, system_prompt, start, results))
               for i in range(args.students)]
    for t in threads:
        t.start()
    wall0 = time.perf_counter()
    start.set()
    for t in threads:
        t.join()
    wall = time.perf_counter() - wall0

    rows = [results[i] for i in sorted(results)]
    ok = [r for r in rows if r["ok"]]
    print(f"\n{'#':>3} {'retrieve':>9} {'1st token':>10} {'total':>7} {'tokens':>7}  result")
    for r in rows:
        cell = lambda v: f"{v:.1f}s" if v is not None else "-"
        print(f"{r['id']:>3} {cell(r['retrieve_s']):>9} {cell(r['ttft_s']):>10} "
              f"{cell(r['total_s']):>7} {r['tokens']:>7}  "
              f"{'ok' if r['ok'] else 'FAILED ' + r['error']}")

    print(f"\nStudents: {args.students}   succeeded: {len(ok)}   "
          f"failed: {len(rows) - len(ok)}   wall time: {wall:.1f}s")
    print("seconds            median    max    min")
    if args.topic:
        print(f"retrieve           {fmt([r['retrieve_s'] for r in ok])}")
    print(f"first token        {fmt([r['ttft_s'] for r in ok])}")
    print(f"whole answer       {fmt([r['total_s'] for r in ok])}")
    total_tokens = sum(r["tokens"] for r in ok)
    if ok and wall > 0:
        print(f"aggregate output: {total_tokens / wall:.0f} tokens/s "
              f"({total_tokens} tokens)")
    raise SystemExit(0 if len(ok) == len(rows) else 1)


if __name__ == "__main__":
    main()
