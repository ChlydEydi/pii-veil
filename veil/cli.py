"""Command line:

  python -m veil demo [file]                 full round trip with the emulated cloud AI
  python -m veil mask  file                  show what the AI would receive
  python -m veil ask   file --backend X      real round trip (mock|anthropic|openai|ollama)
  python -m veil serve --backend X           OpenAI-compatible privacy proxy

Options shared by ask/serve/demo:
  --terms a,b,c          extra confidential words (client names, project names)
  --local-llm URL MODEL  use a self-hosted model (e.g. Ollama) to find PII too
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .detect import LocalLLMDetector, RuleDetector
from .llm import MockCloudAI, backend_from_name
from .shield import Shield

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "customer_email.txt"
TASK = "Summarise this customer email and draft a short reply.\n\n"


def _shield(args) -> Shield:
    terms = [t.strip() for t in (args.terms or "").split(",") if t.strip()]
    rules = RuleDetector(custom_terms=terms)
    if args.local_llm:
        url, model = args.local_llm
        return Shield(detector=LocalLLMDetector(url, model, fallback=rules))
    return Shield(detector=rules)


def _read(path: str | None) -> str:
    if path in (None, "-"):
        return SAMPLE.read_text(encoding="utf-8") if path is None else sys.stdin.read()
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"File not found: {path}\n"
                         f"Try the sample:  python -m veil mask examples/customer_email.txt\n"
                         f"Or pipe text in: echo Call John Smith on 9123 4567 | python -m veil mask -")
    return p.read_text(encoding="utf-8")


def _box(title: str, body: str) -> None:
    print(f"\n\033[1m── {title} " + "─" * max(0, 60 - len(title)) + "\033[0m")
    print(body.rstrip())


def cmd_demo(args) -> int:
    text = _read(args.file)
    shield = _shield(args)
    ai = MockCloudAI(log_path=None)

    masked = shield.mask(text)
    answer_fake = ai.chat([{"role": "user", "content": TASK + masked}])
    answer = shield.unmask(answer_fake)

    _box("1. ORIGINAL (stays on our machine)", text)
    _box("2. WHAT THE CLOUD AI RECEIVES", masked)
    _box("3. CLOUD AI ANSWER (fake identities)", answer_fake)
    _box("4. ANSWER AFTER UNMASKING (real identities)", answer)
    _box("5. MAPPING (kept locally, never sent)", "\n".join(f"  {r:<45} -> {f}" for r, f in shield.mapping()))

    leaked = [r for r, _ in shield.mapping()
              if re.search(rf"(?<!\w){re.escape(r)}(?!\w)", ai.received[0], re.I)]
    _box("6. LEAK CHECK", "No real value reached the AI. ✅" if not leaked
         else "LEAKED: " + ", ".join(leaked) + " ❌")
    return 1 if leaked else 0


def cmd_mask(args) -> int:
    print(_shield(args).mask(_read(args.file)))
    return 0


def cmd_ask(args) -> int:
    shield = _shield(args)
    backend = backend_from_name(args.backend)
    prompt = (args.prompt + "\n\n" if args.prompt else TASK) + _read(args.file)
    masked = shield.mask(prompt)
    if args.show:
        _box("SENT TO AI", masked)
    print(shield.unmask(backend.chat([{"role": "user", "content": masked}])))
    if args.vault:
        shield.save(args.vault, args.vault_password)
    return 0


def cmd_serve(args) -> int:
    from .proxy import make_server

    backend = backend_from_name(args.backend)
    audit = (lambda msgs: print("→ AI sees:", msgs[-1]["content"][:200].replace("\n", " "))) if args.show else None
    server = make_server(backend, _shield(args), args.host, args.port, audit=audit)
    print(f"pii-veil proxy on http://{args.host}:{args.port}/v1/chat/completions  (backend: {args.backend})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="veil", description="Keep real personal data away from cloud AI.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--terms", help="comma-separated extra confidential words")
        sp.add_argument("--local-llm", nargs=2, metavar=("URL", "MODEL"),
                        help="self-hosted detector, e.g. http://127.0.0.1:11434/v1 qwen2.5:3b")

    sp = sub.add_parser("demo", help="round trip with the emulated cloud AI")
    sp.add_argument("file", nargs="?")
    common(sp)
    sp.set_defaults(fn=cmd_demo)

    sp = sub.add_parser("mask", help="print the masked text")
    sp.add_argument("file", nargs="?")
    common(sp)
    sp.set_defaults(fn=cmd_mask)

    sp = sub.add_parser("ask", help="real round trip through a cloud AI")
    sp.add_argument("file", nargs="?")
    sp.add_argument("--backend", default="mock")
    sp.add_argument("--prompt")
    sp.add_argument("--show", action="store_true", help="print what is sent to the AI")
    sp.add_argument("--vault", help="save the encrypted mapping here")
    sp.add_argument("--vault-password", default="change-me")
    common(sp)
    sp.set_defaults(fn=cmd_ask)

    sp = sub.add_parser("serve", help="OpenAI-compatible privacy proxy")
    sp.add_argument("--backend", default="mock")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8787)
    sp.add_argument("--show", action="store_true", help="log what the AI sees")
    common(sp)
    sp.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    return args.fn(args)
