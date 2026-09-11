"""Text normalisation for matching.

Human-typed references contain casing noise, punctuation, accents, and
quantities ("2 x veg biryani"). Normalisation strips all of that down to the
tokens that actually identify a catalog entry.
"""

from __future__ import annotations

import unicodedata


def _basic(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))  # strip accents
    s = s.casefold()
    return "".join(c if c.isalnum() else " " for c in s)


def tokens(s: str) -> list[str]:
    """Identifying tokens: drops pure digits (quantities) and single characters
    ("2 x paneer tikka" -> ["paneer", "tikka"]). Single-char tokens carry no
    signal in this domain and mostly come from quantity markers like 'x'."""
    return [t for t in _basic(s).split() if not t.isdigit() and len(t) > 1]


def canonical(s: str) -> str:
    """Order-insensitive canonical string: sorted identifying tokens joined by
    spaces. Feeding this to SequenceMatcher makes word order irrelevant."""
    return " ".join(sorted(tokens(s)))
