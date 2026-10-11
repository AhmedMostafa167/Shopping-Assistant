"""Scoring for the retrieval evaluation: pure functions, no database or API calls."""
import math

KS = (1, 3, 5, 10)
ANGLES = ("category", "feature", "need", "short")


def select_queries(rows: list[dict]) -> list[dict]:
    """One query per labelled product, with the four phrasings rotated evenly.

    Four phrasings of the same product are not independent evidence, so each product
    contributes one query. The choice depends only on the sorted product ids, so every
    run evaluates the same queries.
    """
    by_product: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_product.setdefault(row["product_id"], {})[row["angle"]] = row
    selected = []
    for index, product_id in enumerate(sorted(by_product)):
        phrasings = by_product[product_id]
        angle = ANGLES[index % len(ANGLES)]
        selected.append(phrasings.get(angle) or phrasings[sorted(phrasings)[0]])
    return selected


def rerank_subset(selected: list[dict], size: int = 40) -> list[dict]:
    """A fixed, evenly spread subset for the paid rerank mode."""
    return selected[::3][:size]


def results_filename(mode: str, subset: str) -> str:
    """Where one run saves its per-query results. Unique per (mode, subset): a shared
    file would let one run silently reuse another run's results."""
    return f"retrieval__{mode}__{subset}.jsonl"


def first_relevant_rank(retrieved_ids: list[int], relevant_ids: set[int]) -> int | None:
    """1-based position of the first relevant result, or None if none was retrieved."""
    for position, product_id in enumerate(retrieved_ids, start=1):
        if product_id in relevant_ids:
            return position
    return None


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion; behaves well for small samples."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    half_width = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denominator
    return (max(0.0, centre - half_width), min(1.0, centre + half_width))


def summarize(ranks: list[int | None], latencies_s: list[float]) -> dict:
    """Hit rate at each k with its interval, MRR, nDCG@10 and latency for one mode."""
    total = len(ranks)
    metrics: dict = {"queries": total}
    for k in KS:
        hits = sum(1 for rank in ranks if rank is not None and rank <= k)
        low, high = wilson_interval(hits, total)
        metrics[f"hit_at_{k}"] = hits / total if total else 0.0
        metrics[f"hit_at_{k}_ci_low"] = low
        metrics[f"hit_at_{k}_ci_high"] = high
    metrics["mrr"] = sum(1 / rank for rank in ranks if rank) / total if total else 0.0
    metrics["ndcg_at_10"] = (
        sum(1 / math.log2(rank + 1) for rank in ranks if rank and rank <= 10) / total
        if total else 0.0
    )
    ordered = sorted(latencies_s)
    if ordered:
        metrics["latency_p50_ms"] = 1000 * ordered[len(ordered) // 2]
        metrics["latency_p95_ms"] = 1000 * ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return metrics
