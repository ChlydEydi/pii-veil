"""Cloud AI backends. They only ever receive masked text.

* MockCloudAI       - emulates a cloud AI with no API key. It also writes down
                      everything it receives, i.e. exactly what an AI provider
                      (or a hacker who breaches it) would get to see.
* AnthropicAI       - Claude via the Anthropic Messages API (ANTHROPIC_API_KEY)
* OpenAICompatibleAI- OpenAI, Azure-style gateways, Ollama, vLLM, LM Studio ...
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

Messages = list[dict]  # [{"role": "user"|"assistant"|"system", "content": str}]


class MockCloudAI:
    """A stand-in for a cloud model, good enough to prove the round trip."""

    def __init__(self, log_path: str | Path | None = "cloud_ai_received.log"):
        self.log_path = Path(log_path) if log_path else None
        self.received: list[str] = []

    def chat(self, messages: Messages, system: str | None = None) -> str:
        seen = "\n".join(m["content"] for m in messages if isinstance(m.get("content"), str))
        self.received.append(seen)
        if self.log_path:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write("=" * 60 + "\n" + seen + "\n")

        emails = list(dict.fromkeys(re.findall(r"[\w.+-]+@[\w.-]+\.\w+", seen)))
        people = list(dict.fromkeys(re.findall(
            r"\b(?:Mr|Ms|Mrs|Dr)\.?\s+[A-Z][a-z]+|\b[A-Z][a-z]+\s+[A-Z][a-z]{3,}\b", seen)))
        phones = list(dict.fromkeys(re.findall(r"\+\d[\d\s-]{6,}\d", seen)))
        first = people[0].split()[-2] if people and len(people[0].split()) > 1 else "there"
        lines = ["Here is my analysis (emulated cloud AI).", ""]
        if people:
            lines.append("People involved: " + ", ".join(people) + ".")
        if emails:
            lines.append("Contact emails: " + ", ".join(emails) + ".")
        if phones:
            lines.append("Phone numbers: " + ", ".join(p.strip() for p in phones) + ".")
        lines += ["", "Suggested reply:", f"Dear {first},",
                  "Thank you for reaching out. We have reviewed your case and "
                  "will follow up within two working days.",
                  f"If anything is urgent, reply to {emails[0]}." if emails else ""]
        return "\n".join(lines).strip()


class AnthropicAI:
    def __init__(self, model: str | None = None, api_key: str | None = None, max_tokens: int = 1024):
        self.model = model or os.environ.get("VEIL_MODEL", "claude-sonnet-5-5")
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
        self.max_tokens = max_tokens

    def chat(self, messages: Messages, system: str | None = None) -> str:
        body = {"model": self.model, "max_tokens": self.max_tokens,
                "messages": [m for m in messages if m["role"] != "system"]}
        sys_parts = [m["content"] for m in messages if m["role"] == "system"] + ([system] if system else [])
        if sys_parts:
            body["system"] = "\n\n".join(sys_parts)
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", json.dumps(body).encode(),
            {"content-type": "application/json", "x-api-key": self.api_key,
             "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
        return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")


class OpenAICompatibleAI:
    def __init__(self, base_url: str | None = None, model: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("VEIL_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("VEIL_MODEL", "gpt-4o-mini")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def chat(self, messages: Messages, system: str | None = None) -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions",
                                     json.dumps({"model": self.model, "messages": msgs}).encode(), headers)
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)["choices"][0]["message"]["content"]


def backend_from_name(name: str):
    name = name.lower()
    if name == "mock":
        return MockCloudAI()
    if name in ("anthropic", "claude"):
        return AnthropicAI()
    if name in ("openai", "ollama", "compatible"):
        if name == "ollama":
            return OpenAICompatibleAI(os.environ.get("VEIL_BASE_URL", "http://127.0.0.1:11434/v1"),
                                      os.environ.get("VEIL_MODEL", "llama3.2"))
        return OpenAICompatibleAI()
    raise ValueError(f"unknown backend {name!r} (use mock, anthropic, openai, ollama)")
