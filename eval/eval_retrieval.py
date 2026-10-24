"""Evaluate each stage of product retrieval on the labelled query set.

    PYTHONPATH=src:eval uv run python eval/eval_retrieval.py --mode hybrid

Modes: vector, keyword, hybrid (both fused), hybrid_rerank (the production path; paid).
Results are saved per query as the run goes, so an interrupted run continues where it
stopped and never pays for the same query twice.
"""
import argparse
import asyncio
import csv
import json
import os
import subprocess
import time
from pathlib import Path

# Evaluation runs must not flood Langfuse with one trace per query.
os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

from sqlalchemy import text as sql_text  # noqa: E402

from helpers.config import get_settings  # noqa: E402
from main import app, lifespan  # noqa: E402
from models.enums.DataBaseEnums import DataBaseEnums  # noqa: E402
from retrieval_metrics import (  # noqa: E402
    KS,
    first_relevant_rank,
    rerank_subset,
    results_filename,
    select_queries,
    summarize,
)

MODES = ("vector", "keyword", "hybrid", "hybrid_rerank")
EVALSET = Path(__file__).parent / "evalset.csv"

# A labelled product and its exact duplicates (same title and description) are the
# same item to a shopper, so any of them is a correct result.
RELEVANT_IDS_SQL = sql_text("""
    SELECT labelled.source_id, labelled.product_id AS labelled_id, twin.product_id AS relevant_id
    FROM products labelled
    JOIN products twin
      ON twin.title = labelled.title AND twin.description = labelled.description
    WHERE labelled.source_id = ANY(:source_ids)
""")


def load_queries(mode: str, subset: str) -> list[dict]:
    with open(EVALSET, newline="") as handle:
        rows = [{**row, "product_id": row["product_id"].strip()} for row in csv.DictReader(handle)]
    selected = select_queries(rows)
    if mode == "hybrid_rerank" or subset == "rerank":
        selected = rerank_subset(selected)
    return selected


async def load_relevant_ids(source_ids: list[str]) -> tuple[dict, dict]:
    """Map each labelled source id to its own product ids and to those plus duplicates."""
    strict, with_twins = {}, {}
    async with app.db_client() as session:
        result = await session.execute(RELEVANT_IDS_SQL, {"source_ids": source_ids})
        for source_id, labelled_id, relevant_id in result.all():
            strict.setdefault(source_id, set()).add(labelled_id)
            with_twins.setdefault(source_id, set()).add(relevant_id)
    return strict, with_twins


async def retrieve(mode: str, query: str, top_k: int, category_name: str) -> list[int]:
    controller = app.retrieval_controller
    if mode == "vector":
        results = await controller.vector_search(query, top_k, category_name)
    elif mode == "keyword":
        results = await controller.keyword_search(query, top_k, category_name)
    else:
        results = await controller.hybrid_search(
            query, top_k, category_name, rerank=(mode == "hybrid_rerank")
        )
    return [result.product_id for result in results]


def product_text(product) -> str:
    return f"{product.title}\n{(product.description or '')[:500]}\nprice: {product.price}"


async def judge_contexts(rows: list[dict], judge_limit: int, judge_k: int) -> list[dict]:
    """The query and top results, as text, for the first judge_limit queries."""
    samples = []
    for row in rows[:judge_limit]:
        top_ids = row["retrieved_ids"][:judge_k]
        products = {p.product_id: p for p in await app.retrieval_controller.get_products_by_ids(top_ids)}
        samples.append({
            "query": row["query"],
            "contexts": [product_text(products[i]) for i in top_ids if i in products],
        })
    return samples


def judge_relevance(samples: list[dict]) -> dict:
    """LLM-judged relevance of the retrieved products (catches good results the labels miss).

    Runs one request at a time: the judge model's rate limit is far below what
    Ragas sends when it runs in parallel.
    """
    from langchain_groq import ChatGroq
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import ContextRelevance
    from ragas.run_config import RunConfig

    settings = get_settings()
    judge = LangchainLLMWrapper(ChatGroq(
        model=settings.GENERATION_MODEL, api_key=settings.GROQ_API_KEY,
        temperature=0, max_tokens=1024,
    ))
    dataset = EvaluationDataset(samples=[
        SingleTurnSample(user_input=sample["query"], retrieved_contexts=sample["contexts"])
        for sample in samples if sample["contexts"]
    ])
    judged = evaluate(
        dataset, metrics=[ContextRelevance()], llm=judge, raise_exceptions=False,
        run_config=RunConfig(max_workers=1, max_retries=10, max_wait=90, timeout=180),
    ).to_pandas()
    scores = judged.select_dtypes("number")
    return {
        "judged_queries": int(scores.iloc[:, 0].notna().sum()),
        **{f"judge_{name}": float(value) for name, value in scores.mean().items()},
    }


async def run(args) -> tuple[dict, list[dict]]:
    queries = load_queries(args.mode, args.subset)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / results_filename(args.mode, args.subset)

    done = {}
    if results_path.exists():
        done = {row["query"]: row for row in map(json.loads, results_path.open())}

    async with lifespan(app):
        strict_ids, twin_ids = await load_relevant_ids([q["product_id"] for q in queries])
        with results_path.open("a") as handle:
            for item in queries:
                if item["query"] in done:
                    continue
                started = time.perf_counter()
                retrieved = await retrieve(
                    args.mode, item["query"].strip(), args.top_k, args.category_name
                )
                row = {
                    "mode": args.mode,
                    "query": item["query"],
                    "angle": item["angle"],
                    "labelled_source_id": item["product_id"],
                    "retrieved_ids": retrieved,
                    "latency_s": time.perf_counter() - started,
                }
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                done[item["query"]] = row

        rows = [done[item["query"]] for item in queries]
        samples = await judge_contexts(rows, args.judge_limit, args.judge_k)

    latencies = [row["latency_s"] for row in rows]
    ranks = [
        first_relevant_rank(row["retrieved_ids"], twin_ids.get(row["labelled_source_id"], set()))
        for row in rows
    ]
    strict_ranks = [
        first_relevant_rank(row["retrieved_ids"], strict_ids.get(row["labelled_source_id"], set()))
        for row in rows
    ]
    metrics = summarize(ranks, latencies)
    strict = summarize(strict_ranks, latencies)
    metrics.update({f"strict_{name}": strict[name] for name in ("hit_at_10", "mrr")})
    metrics["avg_results_returned"] = sum(len(row["retrieved_ids"]) for row in rows) / len(rows)
    metrics["labels_missing_from_catalogue"] = sum(
        1 for item in queries if item["product_id"] not in strict_ids
    )
    return metrics, samples


def log_to_mlflow(args, metrics: dict) -> None:
    import mlflow

    settings = get_settings()
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
    mlflow.set_experiment(args.experiment)
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        git_commit = "unknown"
    with mlflow.start_run(run_name=args.run_name or f"{args.mode}-{args.subset}"):
        mlflow.set_tag("git_commit", git_commit)
        mlflow.log_params({
            "mode": args.mode,
            "subset": args.subset,
            "top_k": args.top_k,
            "category": args.category_name,
            "embedding_model": settings.EMBEDDING_MODEL,
            "reranking_model": settings.RERANKING_MODEL if args.mode == "hybrid_rerank" else "none",
            "query_selection": "one per labelled product, phrasing rotated",
        })
        mlflow.log_metrics({name: float(value) for name, value in metrics.items()})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--subset", default="all", choices=("all", "rerank"),
                        help="'rerank' runs any mode on the 40 queries used for hybrid_rerank")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--category-name", default=DataBaseEnums.DEFAULT_CATEGORY_NAME.value)
    parser.add_argument("--experiment", default="retrieval-stages")
    parser.add_argument("--run-name")
    parser.add_argument("--output-dir", default="eval_outputs")
    parser.add_argument("--no-mlflow", action="store_true")
    parser.add_argument("--judge-limit", type=int, default=0,
                        help="Also have an LLM judge the top results of this many queries")
    parser.add_argument("--judge-k", type=int, default=5, help="Results judged per query")
    args = parser.parse_args()

    metrics, samples = asyncio.run(run(args))
    if samples:
        metrics.update(judge_relevance(samples))
    if not args.no_mlflow:
        log_to_mlflow(args, metrics)

    print(f"mode={args.mode} subset={args.subset} queries={metrics['queries']}")
    for k in KS:
        print(
            f"  hit@{k}: {metrics[f'hit_at_{k}']:.3f} "
            f"(95% CI {metrics[f'hit_at_{k}_ci_low']:.3f}-{metrics[f'hit_at_{k}_ci_high']:.3f})"
        )
    for name, value in metrics.items():
        if not name.startswith("hit_at_") and name != "queries":
            print(f"  {name}: {value:.3f}")


if __name__ == "__main__":
    main()
