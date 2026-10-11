import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from retrieval_metrics import (  # noqa: E402
    first_relevant_rank,
    rerank_subset,
    results_filename,
    select_queries,
    summarize,
    wilson_interval,
)


def evalset(product_count):
    return [
        {"query": f"{angle} query for p{i:03d}", "angle": angle, "product_id": f"p{i:03d}"}
        for i in range(product_count)
        for angle in ("category", "feature", "short", "need")
    ]


def test_one_query_per_product_with_phrasings_spread_evenly():
    selected = select_queries(evalset(8))

    assert [row["product_id"] for row in selected] == [f"p{i:03d}" for i in range(8)]
    assert [row["angle"] for row in selected].count("category") == 2
    assert {row["angle"] for row in selected} == {"category", "feature", "need", "short"}


def test_selection_does_not_depend_on_file_order():
    rows = evalset(12)

    assert select_queries(rows) == select_queries(list(reversed(rows)))


def test_rerank_subset_is_a_fixed_part_of_the_selection():
    selected = select_queries(evalset(127))

    subset = rerank_subset(selected)

    assert len(subset) == 40
    assert all(row in selected for row in subset)
    assert subset == rerank_subset(select_queries(evalset(127)))


def test_rank_is_the_first_relevant_position_and_a_duplicate_counts():
    assert first_relevant_rank([7, 8, 9], {9}) == 3
    assert first_relevant_rank([7, 8, 9], {9, 8}) == 2  # 8 is an identical duplicate
    assert first_relevant_rank([7, 8, 9], {5}) is None
    assert first_relevant_rank([], {5}) is None


def test_summary_counts_hits_at_each_cutoff():
    metrics = summarize(ranks=[1, 3, 7, None], latencies_s=[0.01, 0.02, 0.03, 0.04])

    assert metrics["queries"] == 4
    assert metrics["hit_at_1"] == 0.25
    assert metrics["hit_at_3"] == 0.5
    assert metrics["hit_at_10"] == 0.75
    assert metrics["mrr"] == pytest.approx((1 + 1 / 3 + 1 / 7) / 4)
    assert metrics["latency_p50_ms"] == pytest.approx(30)


def test_confidence_interval_narrows_with_more_queries_and_stays_in_range():
    low_small, high_small = wilson_interval(28, 40)
    low_large, high_large = wilson_interval(89, 127)

    assert (high_large - low_large) < (high_small - low_small)
    assert 0 <= low_small < 0.7 < high_small <= 1
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(10, 10)[1] == 1.0


def test_every_mode_and_subset_saves_to_its_own_file():
    modes = ("vector", "keyword", "hybrid", "hybrid_rerank")
    names = [results_filename(mode, subset) for mode in modes for subset in ("all", "rerank")]

    assert len(set(names)) == len(names)
