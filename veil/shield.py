"""The core idea: swap real values for realistic fakes, and swap them back.

    real text --mask()--> fake text --(cloud AI)--> fake answer --unmask()--> real answer

* Replacements are *consistent*: "John Smith" becomes the same fake person
  every time, and "Mr Smith" / "john.smith@acme.com" follow along, so the AI
  can still reason about who is who.
* Replacements are *realistic* (names stay names, emails stay emails, phone
  numbers keep their format) so the AI's answer quality doesn't drop.
* The mapping lives only on our side (in memory, or in an encrypted vault
  file). Whatever the AI provider stores, trains on, or leaks is fake.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import re
import string
from pathlib import Path

from . import fakes
from .detect import KNOWN_FIRST, Entity, RuleDetector

# Shared mailbox names carry no personal data; leave them readable for the AI.
ROLE_MAILBOXES = {"support", "info", "admin", "sales", "hello", "contact", "help",
                  "noreply", "no-reply", "billing", "hr", "careers", "team", "office"}

MALE = set(fakes.KNOWN_FIRST_NAMES_MALE)
FEMALE = set(fakes.KNOWN_FIRST_NAMES_FEMALE)


class Shield:
    def __init__(self, detector=None, secret: bytes | None = None):
        self.detector = detector or RuleDetector()
        self.secret = secret or os.urandom(32)
        # real (lower-cased) -> fake, per table
        self.tables: dict[str, dict[str, str]] = {
            "first": {}, "last": {}, "domain": {}, "value": {},
        }
        self._used: set[str] = set()
        self._originals: dict[str, str] = {}  # "table:lowered" -> original spelling
        self._forbid = ""  # text being masked; fakes must not already occur in it

    # ------------------------------------------------------------ public API
    def mask(self, text: str) -> str:
        """Replace every detected sensitive value with its fake twin."""
        entities = self.detector.detect(text)
        self._forbid = text.lower()
        out, pos = [], 0
        for e in entities:
            out.append(text[pos:e.start])
            out.append(self._fake_for(e))
            pos = e.end
        out.append(text[pos:])
        return "".join(out)

    def unmask(self, text: str) -> str:
        """Put the real values back into the AI's answer."""
        pairs = self._reverse_pairs()
        if not pairs:
            return text
        lookup = {fake.lower(): real for fake, real in pairs}
        pattern = re.compile(
            r"(?<![\w@.])(" + "|".join(re.escape(f) for f, _ in pairs) + r")(?![\w@])",
            re.IGNORECASE,
        )

        def swap(m: re.Match) -> str:
            got, real = m.group(0), lookup[m.group(0).lower()]
            if got.isupper() and len(got) > 1:
                return real.upper()
            if got.islower() and not real.islower() and "@" not in real:
                return real.lower()
            return real

        return pattern.sub(swap, text)

    def mapping(self) -> list[tuple[str, str]]:
        """(real, fake) pairs, for display / auditing on OUR side only."""
        rows = []
        for table in ("first", "last", "value", "domain"):
            for real, fake in self.tables[table].items():
                rows.append((self._display_real(table, real), fake))
        return rows

    # ------------------------------------------------------------ vault I/O
    def save(self, path: str | Path, password: str) -> None:
        """Persist the mapping, encrypted (Fernet / AES-128-CBC + HMAC)."""
        Fernet = _fernet()

        payload = json.dumps({
            "secret": base64.b64encode(self.secret).decode(),
            "tables": self.tables,
            "originals": self._originals,
        }).encode()
        Path(path).write_bytes(Fernet(_key_from_password(password)).encrypt(payload))

    @classmethod
    def load(cls, path: str | Path, password: str, detector=None) -> "Shield":
        Fernet = _fernet()

        data = json.loads(Fernet(_key_from_password(password)).decrypt(Path(path).read_bytes()))
        s = cls(detector=detector, secret=base64.b64decode(data["secret"]))
        s.tables = data["tables"]
        s._originals = data.get("originals", {})
        s._used = {v.lower() for t in s.tables.values() for v in t.values()}
        return s

    # ------------------------------------------------------------ internals
    def _rng(self, *parts: str) -> random.Random:
        digest = hmac.new(self.secret, "|".join(parts).encode(), hashlib.sha256).digest()
        return random.Random(digest)

    def _unique(self, table: str, key: str, make) -> str:
        """Get (or create) a fake for key that collides with nothing."""
        if key in self.tables[table]:
            return self.tables[table][key]
        for attempt in range(200):
            fake = make(self._rng(table, key, str(attempt)))
            low = fake.lower()
            if low not in self._used and low != key and low not in self._forbid:
                break
        self._used.add(fake.lower())
        self.tables[table][key] = fake
        return fake

    def _remember(self, table: str, real: str) -> str:
        key = real.lower()
        self._originals.setdefault(f"{table}:{key}", real)
        return key

    def _display_real(self, table: str, key: str) -> str:
        return self._originals.get(f"{table}:{key}", key)

    # --- per-kind fake generators
    def _fake_for(self, e: Entity) -> str:
        if e.kind == "PERSON":
            return self._fake_person(e.text)
        if e.kind == "EMAIL":
            return self._fake_email(e.text)
        if e.kind == "PHONE":
            return self._value(e.text, lambda r: _reshape_digits(e.text, r, keep_prefix=True))
        if e.kind == "NRIC":
            return self._value(e.text, lambda r: e.text[0] + "".join(r.choices(string.digits, k=7))
                               + r.choice(string.ascii_uppercase))
        if e.kind == "CARD":
            return self._value(e.text, lambda r: _fake_card(e.text, r))
        if e.kind == "IP":
            return self._value(e.text, lambda r: f"203.0.113.{r.randint(1, 254)}")  # TEST-NET-3
        if e.kind == "URL":
            return self._value(e.text, lambda r: f"https://{self._fake_domain(_host(e.text))}/p/"
                               + "".join(r.choices(string.ascii_lowercase + string.digits, k=8)))
        # CUSTOM / ORG / anything else: an invented organisation name
        return self._value(e.text, lambda r: r.choice(fakes.FAKE_COMPANIES)
                           + (f" {r.randint(2, 99)}" if r.random() < 0.3 else ""))

    def _value(self, real: str, make) -> str:
        return self._unique("value", self._remember("value", real), make)

    def _fake_person(self, name: str) -> str:
        words = name.split()
        out = []
        for i, w in enumerate(words):
            is_first = i == 0 and (len(words) > 1 or w.lower() in KNOWN_FIRST)
            out.append(self._fake_first(w) if is_first else self._fake_last(w))
        # keep the original whitespace between words
        seps = re.findall(r"\s+", name)
        return "".join(o + (seps[i] if i < len(seps) else "") for i, o in enumerate(out))

    def _fake_first(self, real: str) -> str:
        low = real.lower()
        if low in FEMALE and low not in MALE:
            pool = fakes.FAKE_FIRST_FEMALE
        elif low in MALE and low not in FEMALE:
            pool = fakes.FAKE_FIRST_MALE
        else:
            pool = fakes.FAKE_FIRST_MALE + fakes.FAKE_FIRST_FEMALE
        return self._unique("first", self._remember("first", real), lambda r: r.choice(pool))

    def _fake_last(self, real: str) -> str:
        return self._unique("last", self._remember("last", real), lambda r: r.choice(fakes.FAKE_LAST))

    def _fake_domain(self, real: str) -> str:
        return self._unique("domain", self._remember("domain", real),
                            lambda r: r.choice(fakes.FAKE_EMAIL_DOMAINS))

    def _fake_email(self, email: str) -> str:
        local, domain = email.rsplit("@", 1)

        def fake_local(r: random.Random) -> str:
            if local.lower() in ROLE_MAILBOXES:
                return local
            parts = re.split(r"([._+-])", local)
            res = []
            for p in parts:
                if not p or p in "._+-":
                    res.append(p)
                elif p.isalpha():
                    low = p.lower()
                    if low in self.tables["first"] or low in KNOWN_FIRST:
                        res.append(self._fake_first(p).lower())
                    elif low in self.tables["last"] or len(p) > 2:
                        res.append(self._fake_last(p).lower())
                    else:
                        res.append("".join(r.choices(string.ascii_lowercase, k=len(p))))
                else:
                    res.append(_reshape_digits(p, r))
            return "".join(res)

        key = self._remember("value", email)
        if key in self.tables["value"]:
            return self.tables["value"][key]
        fake_dom = self._fake_domain(domain)
        return self._unique("value", key, lambda r: f"{fake_local(r)}@{fake_dom}")

    def _reverse_pairs(self) -> list[tuple[str, str]]:
        pairs = []
        for table, mapping in self.tables.items():
            for real_key, fake in mapping.items():
                pairs.append((fake, self._display_real(table, real_key)))
        # longest first so "arlen.blackwood@x.example" wins over "Arlen"
        return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


# ---------------------------------------------------------------- helpers
def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError("The encrypted vault needs the 'cryptography' package: "
                           "python -m pip install cryptography") from None
    return Fernet


def _key_from_password(password: str) -> bytes:
    raw = hashlib.pbkdf2_hmac("sha256", password.encode(), b"pii-veil-vault-v1", 200_000)
    return base64.urlsafe_b64encode(raw)


def _reshape_digits(text: str, r: random.Random, keep_prefix: bool = False) -> str:
    """Replace digits but keep spacing/punctuation (and a +country code)."""
    out, i = [], 0
    if keep_prefix:
        m = re.match(r"\+\d{1,3}", text)
        if m:
            out.append(m.group())
            i = m.end()
    first_local = True
    for ch in text[i:]:
        if ch.isdigit():
            if first_local and keep_prefix:
                out.append(ch)  # keep first digit: mobile vs landline stays recognisable
                first_local = False
            else:
                out.append(r.choice(string.digits))
        else:
            out.append(ch)
    return "".join(out)


def _fake_card(text: str, r: random.Random) -> str:
    digits = re.sub(r"\D", "", text)
    body = "4000" + "".join(r.choices(string.digits, k=len(digits) - 5))
    total = 0
    for i, ch in enumerate(reversed(body)):  # compute Luhn check digit
        d = int(ch)
        if i % 2 == 0:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    new = iter(body + str((10 - total % 10) % 10))
    return "".join(next(new) if c.isdigit() else c for c in text)


def _host(url: str) -> str:
    m = re.match(r"https?://([^/:?#]+)", url, re.I)
    return m.group(1) if m else url
