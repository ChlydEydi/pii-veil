# pii-veil 🕶️

**Use cloud AI on company data without handing it your real data.**

pii-veil sits between your app and the AI. Before anything leaves your
machine it swaps real names, emails, phone numbers and IDs for **realistic
fakes**, then swaps the real values back into the AI's answer.

```
 your data ──► [ mask ] ──► cloud AI (Claude, GPT…) ──► [ unmask ] ──► answer with real data
 "John Smith"   local        sees "Vaughn Holloway"        local        "Dear John…"
```

If the provider logs it, trains on it, or gets hacked, all anyone gets is
fake people. The mapping between real and fake never leaves your side.

> Status: **proof of concept**. It works end to end and has tests, but it is
> not production-ready. See [Limits](#limits-read-this).

## Try it in 30 seconds

Python 3.10+ and nothing else. The encrypted vault feature also needs `cryptography`.

```bash
git clone <this repo> && cd pii-veil
python -m veil demo            # full round trip, no API key needed
python -m unittest -v          # 14 tests (vault test is skipped until you
                               # run: python -m pip install cryptography)
```

The demo prints six panels: the original email, **what the cloud AI receives**,
the AI's answer (fake people), the answer after unmasking (real people), the
local mapping, and a leak check that confirms no real value reached the AI.

## Use it with a real AI

```bash
export ANTHROPIC_API_KEY=...
python -m veil ask examples/customer_email.txt --backend anthropic --show

export OPENAI_API_KEY=...
python -m veil ask examples/customer_email.txt --backend openai --prompt "Summarise this"

python -m veil ask examples/customer_email.txt --backend ollama      # fully local model
```

### As a drop-in proxy (no code changes to your app)

```bash
python -m veil serve --backend anthropic --port 8787 --show
```

Point any OpenAI-compatible client at `http://127.0.0.1:8787/v1`. Every
request is masked going out and unmasked coming back.

### As a library

```python
from veil import Shield, RuleDetector

shield = Shield(detector=RuleDetector(custom_terms=["Project Falcon", "ALLab"]))
safe   = shield.mask(text)            # send this to any AI
answer = shield.unmask(ai_reply)      # real names are back
shield.save("vault.bin", "password")  # optional encrypted mapping
```

## How it works

| Step | What happens | Where |
|---|---|---|
| Detect | Regex rules find emails, phones, Singapore NRIC/FIN, cards (Luhn-checked), IPs, URLs. Names come from a name list plus honorifics (Mr/Ms/Dr). Optionally a **self-hosted model** (Ollama etc.) finds anything else, like client names and addresses. | local |
| Replace | Each value gets a fake of the same kind and shape. Gender is kept so pronouns stay right, phone formats are kept, cards stay Luhn-valid, and emails reuse the fake person's name with a reserved `.example` domain. | local |
| Stay consistent | "John Smith", "Mr Smith" and `john.smith@…` all map to the same fake person, so the AI can still reason about who did what. | local |
| Unlink sessions | Each session uses a fresh random key, so the same person gets different fakes in different sessions. Leaked transcripts can't be joined up. | local |
| Restore | Fakes in the answer are swapped back, case-insensitively and longest match first. | local |

The self-hosted model only **points out** sensitive text. The actual swapping
is done by deterministic code, so even a small 3B model can't corrupt your
data. To try it:

```bash
ollama pull qwen2.5:3b
python -m veil demo --local-llm http://127.0.0.1:11434/v1 qwen2.5:3b
```

## Limits (read this)

These are the open problems this prototype is meant to explore:

1. **Detection misses = leaks.** The rule detector only knows common first
   names, and lower-case or unusual names slip through. Use `--terms` for
   known sensitive words and `--local-llm` for better recall.
2. **Context still leaks.** Changing "John" to "Vaughn" doesn't hide "the CFO
   of our Penang branch who resigned in March". Details like job title, place
   and dates can still identify someone. Generalising these values is the next
   research step.
3. **The AI still sees the content**, just not the identities. Fake names don't
   protect trade secrets in the text itself. Add those words with `--terms`.
4. **Reversal can be imperfect** if the AI rewrites a fake value, for example
   "Vaughn H." or a translated name. Exact and case-varied matches are handled.
5. The proxy doesn't support streaming, and all clients of one server share
   one mapping.

## Project layout

```
veil/detect.py   rule + self-hosted-LLM detectors
veil/shield.py   mask / unmask / encrypted vault
veil/fakes.py    fake name, company and domain pools
veil/llm.py      mock (emulated) cloud AI, Anthropic, OpenAI-compatible
veil/proxy.py    OpenAI-compatible privacy proxy
veil/cli.py      demo / mask / ask / serve
tests/           14 offline tests
```

## Contributing ideas

- Swap the name list for a proper local NER model (spaCy, GLiNER, Presidio)
- Generalise quasi-identifiers (exact age → age band, street → district)
- Streaming support in the proxy
- Benchmark: answer quality with real data vs masked data

MIT licensed. Built so anyone can check exactly what happens to their data.
