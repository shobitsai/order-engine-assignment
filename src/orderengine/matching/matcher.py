"""Fuzzy matching of a messy free-text reference against a catalog.

Scoring (stdlib only) blends two complementary signals:

- a *soft token F1*: every query token is matched against its most similar
  entry token (SequenceMatcher ratio), and vice versa; precision and recall
  are combined harmonically. Robust to typos WITHIN words, extra/missing
  words, and word order.
- a *canonical sequence ratio*: SequenceMatcher over the sorted-token strings,
  which rewards overall shape and catches what token-by-token comparison
  misses (e.g. splits/joins like "ice cream" vs "icecream").

Abstention — the deliberately conservative part. A wrong confident match is
worse than no match, so `match()` returns None when ANY of:

- the query has no identifying content (< min_query_chars after normalising);
- the best score is below `score_threshold` (likely out-of-catalog);
- the best score beats the runner-up by less than `margin` (ambiguous —
  two catalog entries are near-indistinguishable for this query), UNLESS the
  best score is >= `exact_override` (a near-verbatim hit should not be blocked
  by the existence of a similar sibling entry, e.g. "chicken tikka" vs
  "chicken tikka masala").

Defaults were chosen from the threshold sweep in evaluate.py, not by feel.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from .normalize import canonical, tokens


@dataclass(frozen=True, slots=True)
class Match:
    entry: str
    score: float
    runner_up: float  # second-best score; exposed so callers can see the margin


def _soft_token_f1(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0

    def best(token: str, others: list[str]) -> float:
        return max(SequenceMatcher(None, token, other).ratio() for other in others)

    precision = sum(best(t, b) for t in a) / len(a)
    recall = sum(best(t, a) for t in b) / len(b)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


class CatalogMatcher:
    def __init__(
        self,
        entries: Iterable[str],
        *,
        score_threshold: float = 0.70,
        margin: float = 0.08,
        exact_override: float = 0.95,
        min_query_chars: int = 3,
    ) -> None:
        self.score_threshold = score_threshold
        self.margin = margin
        self.exact_override = exact_override
        self.min_query_chars = min_query_chars
        # Precompute per-entry token lists and canonical strings once.
        self._entries = [(e, tokens(e), canonical(e)) for e in entries]
        if not self._entries:
            raise ValueError("catalog is empty")

    def _score(self, q_tokens: list[str], q_canon: str, e_tokens: list[str], e_canon: str) -> float:
        soft = _soft_token_f1(q_tokens, e_tokens)
        seq = SequenceMatcher(None, q_canon, e_canon).ratio()
        return 0.5 * soft + 0.5 * seq

    def score_all(self, query: str) -> list[tuple[str, float]]:
        """All entries scored against the query, best first. Debug/eval hook."""
        q_tokens, q_canon = tokens(query), canonical(query)
        scored = [
            (entry, self._score(q_tokens, q_canon, e_tokens, e_canon))
            for entry, e_tokens, e_canon in self._entries
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def match(self, query: str) -> Match | None:
        """Best catalog entry for the query, or None when not confident enough."""
        if len(canonical(query)) < self.min_query_chars:
            return None
        scored = self.score_all(query)
        best_entry, best_score = scored[0]
        runner_up = scored[1][1] if len(scored) > 1 else 0.0
        if best_score < self.score_threshold:
            return None
        if best_score - runner_up < self.margin and best_score < self.exact_override:
            return None
        return Match(entry=best_entry, score=best_score, runner_up=runner_up)
