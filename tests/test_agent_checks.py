import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL_DIR))
from agent_checks import (  # noqa: E402
    EXPECTATION_KEYS,
    TOOL_NAMES,
    budget_respected,
    compare,
    memory_read_first,
    memory_write_correct,
    missing_price_not_shown,
    prices_grounded,
    run_checks,
    search_uses_memory,
    summarize,
    tools_as_expected,
)


def record(**overrides):
    base = {
        "user_messages": ["Find me a charger under $20."],
        "replies": ["The Anker charger is $12.99."],
        "tool_calls": [
            {"name": "read_memory", "args": {}, "output": "No stored facts about this user yet."},
            {"name": "search_catalog", "args": {"query": "charger"},
             "output": "- Anker charger ($12.99, recommendation_score 4.2/5): fast"},
        ],
        "seed_memory": [],
        "memory_after": [],
    }
    return {**base, **overrides}


def call(name, **args):
    return {"name": name, "args": args, "output": ""}


def test_memory_must_be_read_before_anything_else():
    assert memory_read_first(record(), {}) is True
    searched_first = record(tool_calls=[call("search_catalog", query="x"), call("read_memory")])
    assert memory_read_first(searched_first, {}) is False
    assert memory_read_first(record(tool_calls=[]), {}) is False


def test_memory_expectation_checks_count_and_wording():
    stored = record(memory_after=[{"fact_type": "preference", "content": "User prefers Samsung"}])
    assert memory_write_correct(stored, {"memory": {"count": 1, "contains": ["samsung"]}}) is True
    assert memory_write_correct(stored, {"memory": {"count": 0}}) is False  # stored a one-off
    assert memory_write_correct(stored, {"memory": {"count": 1, "contains": ["red"]}}) is False
    assert memory_write_correct(stored, {"memory": {"count": 1, "excludes": ["samsung"]}}) is False
    assert memory_write_correct(stored, {}) is None


def test_a_duplicate_fact_fails_the_memory_check():
    twice = record(memory_after=[
        {"fact_type": "preference", "content": "User prefers Samsung products"},
        {"fact_type": "preference", "content": "User is a Samsung person"},
    ])
    assert memory_write_correct(twice, {"memory": {"count": 1}}) is False


def test_required_tools_accept_any_listed_alternative():
    expect = {"tools_required": [["search_catalog", "filter_products"]]}
    assert tools_as_expected(record(), expect) is True
    filtered = record(tool_calls=[call("read_memory"), call("filter_products", max_price=10)])
    assert tools_as_expected(filtered, expect) is True
    assert tools_as_expected(record(tool_calls=[call("read_memory")]), expect) is False


def test_forbidden_tools_fail_the_check():
    expect = {"tools_forbidden": ["search_catalog", "write_memory"]}
    assert tools_as_expected(record(tool_calls=[call("read_memory")]), expect) is True
    assert tools_as_expected(record(), expect) is False
    assert tools_as_expected(record(), {}) is None


def test_filter_limits_must_be_passed_to_the_filter_tool():
    expect = {"tools_required": [["filter_products"]],
              "filter_limits": {"max_price": 10, "min_rating": 4.5}}
    good = record(tool_calls=[call("filter_products", max_price=10, min_rating=4.5)])
    no_rating = record(tool_calls=[call("filter_products", max_price=10)])
    too_loose = record(tool_calls=[call("filter_products", max_price=50, min_rating=4.5)])
    assert tools_as_expected(good, expect) is True
    assert tools_as_expected(no_rating, expect) is False
    assert tools_as_expected(too_loose, expect) is False


def test_budget_check_reads_prices_from_the_final_reply():
    assert budget_respected(record(), {"max_price": 20}) is True
    over = record(replies=["Try this one at $24.50, or this at $9."])
    assert budget_respected(over, {"max_price": 20}) is False
    assert budget_respected(record(replies=["Nothing under $20, sorry."]), {"max_price": 20}) is True
    assert budget_respected(record(), {}) is None


def test_prices_must_come_from_a_tool_result_or_the_user():
    assert prices_grounded(record(), {}) is True
    invented = record(replies=["It costs $14.99."])
    assert prices_grounded(invented, {}) is False
    echoes_budget = record(replies=["Nothing under $20 was found."])
    assert prices_grounded(echoes_budget, {}) is True
    assert prices_grounded(record(replies=["I can help you shop."]), {}) is None


def test_search_must_carry_the_stored_fact():
    expect = {"search_query_contains": ["iphone 13"]}
    used = record(tool_calls=[call("search_catalog", query="iPhone 13 case")])
    ignored = record(tool_calls=[call("search_catalog", query="phone case")])
    assert search_uses_memory(used, expect) is True
    assert search_uses_memory(ignored, expect) is False
    assert search_uses_memory(used, {}) is None


def test_a_missing_price_must_not_reach_the_user_as_nan():
    shown = record(replies=["| Charger | $nan | 2.4/5 |"])
    assert missing_price_not_shown(shown, {}) is False
    assert missing_price_not_shown(record(replies=["Charger, price not listed"]), {}) is True
    assert missing_price_not_shown(record(replies=["A banana case for $9"]), {}) is True
    no_products = record(tool_calls=[call("read_memory")], replies=["nan"])
    assert missing_price_not_shown(no_products, {}) is None


def test_only_applicable_checks_are_reported():
    results = run_checks(record(), {"max_price": 20})
    assert results == {"memory_read_first": True, "budget_respected": True,
                       "prices_grounded": True, "missing_price_not_shown": True}


def test_before_and_after_are_lined_up_per_check():
    before = summarize({"t": [{"a": True, "b": False}]})
    after = summarize({"t": [{"a": True, "b": True, "c": True}]})

    rows = {row["check"]: row for row in compare(before, after)}

    assert rows["b"]["before"]["passed"] == 0 and rows["b"]["after"]["passed"] == 1
    assert rows["c"]["before"]["total"] == 0  # a check added later has no "before"


def test_a_task_is_reliable_only_if_every_trial_passes():
    summary = summarize({
        "steady": [{"a": True, "b": True}] * 3,
        "flaky": [{"a": True}, {"a": False}, {"a": True}],
    })
    assert summary["tasks_reliably_passed"] == 1
    assert summary["per_task"]["flaky"] == {"trials": 3, "passed": 2}
    assert summary["per_check"]["a"] == {"passed": 5, "total": 6, "rate": pytest.approx(5 / 6)}
    assert summary["trial_pass_rate"] == pytest.approx(5 / 6)


def test_the_task_file_is_well_formed():
    spec = json.loads((EVAL_DIR / "agent_tasks.json").read_text())
    ids = [task["id"] for task in spec["tasks"]]
    assert len(ids) == len(set(ids)) == 12
    for task in spec["tasks"]:
        assert task["turns"] and all(isinstance(turn, str) for turn in task["turns"])
        assert set(task["expect"]) <= EXPECTATION_KEYS
        named = [name for group in task["expect"].get("tools_required", []) for name in group]
        assert set(named + task["expect"].get("tools_forbidden", [])) <= TOOL_NAMES
