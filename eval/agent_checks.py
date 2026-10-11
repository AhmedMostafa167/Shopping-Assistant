"""Pass/fail checks on one agent run. Pure functions: no database, no API calls.

A run record is what the runner collected:
    user_messages  list[str]   what the user said, in order
    replies        list[str]   the agent's reply to each message
    tool_calls     list[dict]  {"name", "args", "output"} in the order they happened
    seed_memory    list[dict]  facts stored before the conversation
    memory_after   list[dict]  {"fact_type", "content"} in the memory table afterwards

Each check returns True (pass), False (fail) or None (does not apply to this task).
"""
import re

TOOL_NAMES = {"search_catalog", "filter_products", "read_memory", "write_memory"}
EXPECTATION_KEYS = {
    "tools_required", "tools_forbidden", "memory", "max_price",
    "search_query_contains", "filter_limits",
}

DOLLAR_AMOUNT = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
MISSING_PRICE_SHOWN = re.compile(r"\bnan\b", re.IGNORECASE)
ANY_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _to_float(text: str) -> float:
    return float(text.replace(",", ""))


def dollar_amounts(text: str) -> list[float]:
    return [_to_float(match) for match in DOLLAR_AMOUNT.findall(text)]


def numbers(text: str) -> list[float]:
    return [_to_float(match) for match in ANY_NUMBER.findall(text)]


def memory_read_first(record: dict, expect: dict) -> bool | None:
    """A new conversation must start by reading the user's stored facts."""
    calls = record["tool_calls"]
    return bool(calls) and calls[0]["name"] == "read_memory"


def memory_write_correct(record: dict, expect: dict) -> bool | None:
    """The memory table afterwards holds what the task says it should."""
    wanted = expect.get("memory")
    if wanted is None:
        return None
    facts = record["memory_after"]
    stored_text = " ".join(fact["content"] for fact in facts).lower()
    return (
        len(facts) == wanted["count"]
        and all(word.lower() in stored_text for word in wanted.get("contains", []))
        and not any(word.lower() in stored_text for word in wanted.get("excludes", []))
    )


def tools_as_expected(record: dict, expect: dict) -> bool | None:
    """Required tools were used, forbidden ones were not, and filters carry the limits."""
    required = expect.get("tools_required", [])
    forbidden = expect.get("tools_forbidden", [])
    limits = expect.get("filter_limits")
    if not required and not forbidden and not limits:
        return None
    called = [call["name"] for call in record["tool_calls"]]
    if any(not set(alternatives) & set(called) for alternatives in required):
        return False
    if set(forbidden) & set(called):
        return False
    if limits:
        return any(_filter_within(call["args"], limits) for call in record["tool_calls"]
                   if call["name"] == "filter_products")
    return True


def _filter_within(args: dict, limits: dict) -> bool:
    max_price, min_rating = args.get("max_price"), args.get("min_rating")
    if "max_price" in limits and (max_price is None or max_price > limits["max_price"]):
        return False
    if "min_rating" in limits and (min_rating is None or min_rating < limits["min_rating"]):
        return False
    return True


def budget_respected(record: dict, expect: dict) -> bool | None:
    """No price in the final reply is above the limit the user gave."""
    limit = expect.get("max_price")
    if limit is None:
        return None
    return all(amount <= limit for amount in dollar_amounts(record["replies"][-1]))


def prices_grounded(record: dict, expect: dict) -> bool | None:
    """Every price the agent states came from a tool result or from the user."""
    stated = [amount for reply in record["replies"] for amount in dollar_amounts(reply)]
    if not stated:
        return None
    sources = (
        [call["output"] for call in record["tool_calls"]]
        + record["user_messages"]
        + [fact["content"] for fact in record["seed_memory"]]
    )
    known = {number for source in sources for number in numbers(str(source))}
    return all(any(abs(amount - number) < 0.005 for number in known) for amount in stated)


def search_uses_memory(record: dict, expect: dict) -> bool | None:
    """A catalogue search carries the stored fact it should have used."""
    terms = expect.get("search_query_contains")
    if not terms:
        return None
    queries = [str(call["args"].get("query", "")).lower()
               for call in record["tool_calls"] if call["name"] == "search_catalog"]
    return any(all(term.lower() in query for term in terms) for query in queries)


def missing_price_not_shown(record: dict, expect: dict) -> bool | None:
    """A product without a price must not be shown to the user as "$nan"."""
    listed = any(call["name"] in ("search_catalog", "filter_products") for call in record["tool_calls"])
    if not listed:
        return None
    return not any(MISSING_PRICE_SHOWN.search(reply) for reply in record["replies"])


CHECKS = {
    "memory_read_first": memory_read_first,
    "memory_write_correct": memory_write_correct,
    "tools_as_expected": tools_as_expected,
    "budget_respected": budget_respected,
    "prices_grounded": prices_grounded,
    "search_uses_memory": search_uses_memory,
    "missing_price_not_shown": missing_price_not_shown,
}


def run_checks(record: dict, expect: dict) -> dict[str, bool]:
    """Results of every check that applies to this task."""
    results = {name: check(record, expect) for name, check in CHECKS.items()}
    return {name: passed for name, passed in results.items() if passed is not None}


def compare(before: dict, after: dict) -> list[dict]:
    """Per-check pass counts of two summaries, side by side, for a before/after table."""
    names = list(dict.fromkeys([*before["per_check"], *after["per_check"]]))
    empty = {"passed": 0, "total": 0, "rate": 0.0}
    return [
        {"check": name, "before": before["per_check"].get(name, empty),
         "after": after["per_check"].get(name, empty)}
        for name in names
    ]


def summarize(trial_results: dict[str, list[dict[str, bool]]]) -> dict:
    """Aggregate over all tasks and trials.

    trial_results maps a task id to one dict of check results per completed trial.
    A task is reliably passed only if every applicable check passed in every trial.
    """
    per_check: dict[str, list[bool]] = {}
    per_task = {}
    for task_id, trials in trial_results.items():
        passed_trials = sum(all(checks.values()) for checks in trials)
        per_task[task_id] = {"trials": len(trials), "passed": passed_trials}
        for checks in trials:
            for name, passed in checks.items():
                per_check.setdefault(name, []).append(passed)
    tasks = len(per_task)
    return {
        "per_check": {
            name: {"passed": sum(values), "total": len(values), "rate": sum(values) / len(values)}
            for name, values in per_check.items()
        },
        "per_task": per_task,
        "tasks": tasks,
        "tasks_reliably_passed": sum(
            1 for result in per_task.values() if result["trials"] and result["passed"] == result["trials"]
        ),
        "trial_pass_rate": (
            sum(r["passed"] for r in per_task.values()) / sum(r["trials"] for r in per_task.values())
            if tasks and sum(r["trials"] for r in per_task.values()) else 0.0
        ),
    }
