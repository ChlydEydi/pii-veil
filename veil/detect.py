"""Find sensitive values (PII) in text.

Two detectors ship with the prototype:

* RuleDetector     - regexes + a name list. Zero dependencies, runs anywhere.
* LocalLLMDetector - asks a small *self-hosted* model (e.g. Ollama running
                     llama3.2:3b or qwen2.5:3b) to list the sensitive values.
                     This is the "open-source, self-hosted AI" step of the
                     idea. It never talks to a cloud service.

Both return a list of Entity(start, end, kind, text).
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

from . import fakes


@dataclass(frozen=True)
class Entity:
    start: int
    end: int
    kind: str  # PERSON, EMAIL, PHONE, NRIC, CARD, IP, URL, CUSTOM
    text: str


# ---------------------------------------------------------------- patterns
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r"\bhttps?://[^\s<>\"')]+", re.I)
IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
# Singapore NRIC / FIN, e.g. S1234567D
NRIC_RE = re.compile(r"\b[STFGM]\d{7}[A-Z]\b")
# 13-19 digits, optionally grouped by spaces/dashes; validated with Luhn below
CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
# International or local phone numbers: +65 9123 4567, (555) 123-4567, 9123-4567
PHONE_RE = re.compile(
    r"(?<![\w+])(?:\+\d{1,3}[\s-]?)?(?:\(\d{1,4}\)[\s-]?)?\d{3,4}[\s-]?\d{3,4}(?:[\s-]?\d{2,4})?(?!\w)"
)

HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Mdm|Dr|Prof|Sir|Madam)\.?"
CAP_WORD = r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
HONORIFIC_RE = re.compile(rf"\b{HONORIFIC}\s+({CAP_WORD}(?:\s+{CAP_WORD})?)")
CAP_WORD_RE = re.compile(rf"\b{CAP_WORD}\b")

# Capitalised words that commonly follow a first name but are not surnames.
NOT_SURNAMES = {
    "The", "And", "But", "For", "From", "To", "In", "On", "At", "Is", "Was",
    "Will", "Can", "Has", "Had", "Said", "Says", "Thanks", "Thank", "Hi",
    "Hello", "Dear", "Regards", "Best", "Team", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Please", "We",
    "I", "He", "She", "They", "Our", "Your", "His", "Her",
}

KNOWN_FIRST = set(fakes.KNOWN_FIRST_NAMES_MALE) | set(fakes.KNOWN_FIRST_NAMES_FEMALE)


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


class RuleDetector:
    """Regex + dictionary detector. Fast, deterministic, no dependencies."""

    def __init__(self, custom_terms: list[str] | None = None):
        # custom_terms: anything else you never want to leave the building
        # (client names, project code names, internal hostnames ...)
        self.custom_terms = sorted({t for t in (custom_terms or []) if t.strip()}, key=len, reverse=True)

    def detect(self, text: str) -> list[Entity]:
        found: list[Entity] = []

        def add(m: re.Match, kind: str, group: int = 0):
            found.append(Entity(m.start(group), m.end(group), kind, m.group(group)))

        for term in self.custom_terms:
            for m in re.finditer(rf"\b{re.escape(term)}\b", text, re.I):
                add(m, "CUSTOM")
        for m in EMAIL_RE.finditer(text):
            add(m, "EMAIL")
        for m in URL_RE.finditer(text):
            url = m.group().rstrip(".,;:!?")
            found.append(Entity(m.start(), m.start() + len(url), "URL", url))
        for m in NRIC_RE.finditer(text):
            add(m, "NRIC")
        for m in IPV4_RE.finditer(text):
            add(m, "IP")
        for m in CARD_RE.finditer(text):
            digits = re.sub(r"\D", "", m.group())
            if 13 <= len(digits) <= 19 and _luhn_ok(digits):
                add(m, "CARD")
        for m in PHONE_RE.finditer(text):
            digits = re.sub(r"\D", "", m.group())
            if 7 <= len(digits) <= 15:
                add(m, "PHONE")

        # --- people
        for m in HONORIFIC_RE.finditer(text):
            add(m, "PERSON", 1)
        caps = list(CAP_WORD_RE.finditer(text))
        for i, m in enumerate(caps):
            if m.group().lower() not in KNOWN_FIRST:
                continue
            end = m.end()
            nxt = caps[i + 1] if i + 1 < len(caps) else None
            # a surname is the next capitalised word, separated only by spaces
            if nxt and text[m.end():nxt.start()].strip(" ") == "" and nxt.group() not in NOT_SURNAMES:
                end = nxt.end()
            found.append(Entity(m.start(), end, "PERSON", text[m.start():end]))

        return resolve_overlaps(found)


class LocalLLMDetector:
    """Ask a self-hosted model (OpenAI-compatible API, e.g. Ollama) for PII.

    Example: ollama pull qwen2.5:3b && ollama serve
             LocalLLMDetector("http://127.0.0.1:11434/v1", "qwen2.5:3b")

    The model only *lists* the sensitive strings; replacement is still done by
    our deterministic code, so a weak local model can't corrupt the text.
    Results are merged with the rule detector so regex hits are never lost.
    """

    PROMPT = (
        "List every piece of personal or confidential data in the text below: "
        "people's names, emails, phone numbers, ID numbers, addresses, company "
        "or client names, account numbers. Reply ONLY with JSON like "
        '{"entities":[{"text":"...","kind":"PERSON"}]}. Kinds: PERSON, EMAIL, '
        "PHONE, NRIC, ADDRESS, ORG, CUSTOM.\n\nTEXT:\n"
    )

    def __init__(self, base_url: str, model: str, fallback: RuleDetector | None = None, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback = fallback or RuleDetector()
        self.timeout = timeout

    def detect(self, text: str) -> list[Entity]:
        body = json.dumps({
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": self.PROMPT + text}],
        }).encode()
        req = urllib.request.Request(f"{self.base_url}/chat/completions", body,
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            reply = json.load(r)["choices"][0]["message"]["content"]
        reply = reply[reply.find("{"): reply.rfind("}") + 1]
        items = json.loads(reply).get("entities", [])

        found = list(self.fallback.detect(text))
        for it in items:
            needle = str(it.get("text", "")).strip()
            kind = str(it.get("kind", "CUSTOM")).upper()
            if len(needle) < 2:
                continue
            kind = kind if kind in {"PERSON", "EMAIL", "PHONE", "NRIC"} else "CUSTOM"
            for m in re.finditer(re.escape(needle), text):
                found.append(Entity(m.start(), m.end(), kind, m.group()))
        return resolve_overlaps(found)


PRIORITY = {"EMAIL": 0, "URL": 1, "NRIC": 2, "CARD": 3, "IP": 4, "PHONE": 5, "CUSTOM": 6, "PERSON": 7}


def resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """Keep the longest match; on ties keep the more specific kind."""
    ordered = sorted(entities, key=lambda e: (-(e.end - e.start), PRIORITY.get(e.kind, 9), e.start))
    taken: list[Entity] = []
    for e in ordered:
        if all(e.end <= t.start or e.start >= t.end for t in taken):
            taken.append(e)
    return sorted(taken, key=lambda e: e.start)
