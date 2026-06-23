"""Prompt-injection detection and input sanitization (Section 19).

Authored free-text (`business_context`, `subject_matter`) is sanitized before it
is ever placed in a prompt. Input text can never override system instructions; a
clearly malicious payload is rejected outright.
"""

from __future__ import annotations

import re

# High-signal phrases: presence => reject the input.
HARD_INJECTION = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard the system prompt",
    "disregard all previous",
    "reveal your system prompt",
    "reveal your instructions",
    "exfiltrate",
    "print your system prompt",
]

# Soft markers: presence => sanitize and flag, but proceed.
SOFT_INJECTION = [
    "system prompt",
    "you are now",
    "developer message",
    "as an ai",
    "jailbreak",
    "override",
]


class InjectionError(ValueError):
    """Raised when authored input is clearly an attempt to hijack the model."""


def detect_injection(text: str) -> list[str]:
    """Return all injection markers (hard + soft) found in `text`."""
    low = text.lower()
    found = [p for p in HARD_INJECTION if p in low]
    found += [p for p in SOFT_INJECTION if p in low]
    return found


def sanitize_input(text: str) -> tuple[str, list[str]]:
    """Return (clean_text, flags). Rejects hard-injection payloads; neutralizes soft ones.

    Neutralization replaces a flagged phrase with `[removed]` so the surrounding
    authored content is preserved but the instruction-like fragment cannot act.
    """
    low = text.lower()
    hard = [p for p in HARD_INJECTION if p in low]
    if hard:
        raise InjectionError(f"input rejected: injection attempt detected ({hard})")

    flags: list[str] = []
    clean = text
    for phrase in SOFT_INJECTION:
        if phrase in clean.lower():
            flags.append(phrase)
            clean = re.sub(re.escape(phrase), "[removed]", clean, flags=re.IGNORECASE)
    return clean, flags
