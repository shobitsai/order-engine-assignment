"""Eval harness for the matcher: python -m orderengine.matching.evaluate

Runs the labeled cases in data/eval_cases.json against data/catalog.json and
reports, for the configured thresholds and for a sweep grid:

- precision        correct answers / all answers given (answering on an
                   out-of-catalog query counts as a wrong answer)
- coverage         share of answerable queries (expected != null) answered
- false-answer     share of unanswerable queries (expected == null) that were
                   wrongly given an answer
- accuracy         correct answers + correct abstentions, over all cases

The sweep is the point: it turns the abstention thresholds from an assertion
into a measurement. With real usage data, the same harness would be fed
(query, chosen-or-rejected) pairs from production logs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .matcher import CatalogMatcher

_REPO_ROOT = Path(__file__).resolve().parents[3]


def run_eval(catalog: list[str], cases: list[dict], **matcher_kwargs) -> dict:
    matcher = CatalogMatcher(catalog, **matcher_kwargs)
    answerable = sum(1 for c in cases if c["expected"] is not None)
    unanswerable = len(cases) - answerable
    answered = correct = false_answers = correct_abstains = 0
    mistakes: list[str] = []

    for case in cases:
        result = matcher.match(case["query"])
        expected = case["expected"]
        if result is None:
            if expected is None:
                correct_abstains += 1
            else:
                mistakes.append(f"  MISSED   {case['query']!r}: wanted {expected!r}, abstained")
        else:
            answered += 1
            if result.entry == expected:
                correct += 1
            else:
                if expected is None:
                    false_answers += 1
                mistakes.append(
                    f"  WRONG    {case['query']!r}: got {result.entry!r} "
                    f"(score {result.score:.2f}, runner-up {result.runner_up:.2f}), "
                    f"wanted {expected!r}"
                )

    answered_on_answerable = answered - false_answers
    return {
        "precision": correct / answered if answered else 1.0,
        "coverage": answered_on_answerable / answerable if answerable else 1.0,
        "false_answer_rate": false_answers / unanswerable if unanswerable else 0.0,
        "accuracy": (correct + correct_abstains) / len(cases),
        "answered": answered,
        "total": len(cases),
        "mistakes": mistakes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=_REPO_ROOT / "data" / "catalog.json")
    parser.add_argument("--cases", type=Path, default=_REPO_ROOT / "data" / "eval_cases.json")
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    cases = json.loads(args.cases.read_text(encoding="utf-8"))

    print(f"catalog: {len(catalog)} entries, eval cases: {len(cases)}\n")

    report = run_eval(catalog, cases)
    print("== default thresholds (score>=0.70, margin>=0.08) ==")
    print(
        f"precision {report['precision']:.3f} | coverage {report['coverage']:.3f} | "
        f"false-answer {report['false_answer_rate']:.3f} | accuracy {report['accuracy']:.3f} "
        f"({report['answered']}/{report['total']} answered)"
    )
    if report["mistakes"]:
        print("\nmisses and wrong answers:")
        print("\n".join(report["mistakes"]))

    print("\n== threshold sweep: precision / coverage ==")
    margins = [0.0, 0.04, 0.08, 0.12]
    thresholds = [0.60, 0.65, 0.70, 0.72, 0.75, 0.80, 0.85]
    header = "threshold " + "".join(f"| margin {m:.2f}   " for m in margins)
    print(header)
    print("-" * len(header))
    for threshold in thresholds:
        row = f"{threshold:.2f}      "
        for margin in margins:
            r = run_eval(catalog, cases, score_threshold=threshold, margin=margin)
            row += f"| {r['precision']:.2f} / {r['coverage']:.2f}  "
        print(row)


if __name__ == "__main__":
    main()
