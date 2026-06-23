"""PII detection for the safety gate (Section 16).

Generated content must never contain emails, phone numbers, or employee-id style
identifiers. PII about real participants lives only in `participants.pii_jsonb`
and is never sent to a model.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# International-ish phone numbers: optional +, 7+ digits with separators.
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
# Employee-id style tokens, e.g. EMP12345, EID-9981, employee id 4471.
EMPLOYEE_ID_RE = re.compile(r"\b(?:EMP|EID|EMPID)[-\s]?\d{3,}\b", re.IGNORECASE)


def find_pii(text: str) -> list[str]:
    """Return a list of `kind:match` strings for any PII found."""
    hits: list[str] = []
    hits += [f"email:{m}" for m in EMAIL_RE.findall(text)]
    hits += [f"employee_id:{m}" for m in EMPLOYEE_ID_RE.findall(text)]
    # Filter phone matches that are actually short numeric runs already covered.
    for m in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", m)
        if len(digits) >= 9:  # avoid flagging plain figures like "480" or years
            hits.append(f"phone:{m.strip()}")
    return hits


def contains_pii(text: str) -> bool:
    return bool(find_pii(text))
