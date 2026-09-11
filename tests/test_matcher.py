import json
from pathlib import Path

import pytest

from orderengine.matching import CatalogMatcher
from orderengine.matching.evaluate import run_eval

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def catalog():
    return json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matcher(catalog):
    return CatalogMatcher(catalog)


def test_exact_and_case_insensitive_match(matcher):
    assert matcher.match("Paneer Butter Masala").entry == "Paneer Butter Masala"
    assert matcher.match("paneer butter masala").entry == "Paneer Butter Masala"


def test_typo_within_a_word(matcher):
    assert matcher.match("chiken biryani").entry == "Chicken Biryani"


def test_word_order_is_irrelevant(matcher):
    assert matcher.match("biryani mutton").entry == "Mutton Biryani"


def test_quantity_noise_is_ignored(matcher):
    assert matcher.match("2 x veg fried rice").entry == "Veg Fried Rice"


def test_gibberish_and_empty_queries_abstain(matcher):
    assert matcher.match("xqzkjv wpl") is None
    assert matcher.match("") is None
    assert matcher.match("2") is None  # quantity with no content


def test_ambiguous_query_abstains_but_exact_sibling_does_not(matcher):
    # 'paneer' matches seven entries about equally: must abstain.
    assert matcher.match("paneer") is None
    # 'chicken tikka' is a verbatim entry; its sibling 'Chicken Tikka Masala'
    # must not force an abstention (the exact_override rule).
    assert matcher.match("chicken tikka").entry == "Chicken Tikka"


def test_eval_harness_regression_floor(catalog):
    cases = json.loads((DATA / "eval_cases.json").read_text(encoding="utf-8"))
    report = run_eval(catalog, cases)
    # Tripwire: a scoring change that degrades quality fails loudly.
    assert report["precision"] >= 0.9, report["mistakes"]
    assert report["coverage"] >= 0.9, report["mistakes"]
    assert report["false_answer_rate"] <= 0.15, report["mistakes"]
