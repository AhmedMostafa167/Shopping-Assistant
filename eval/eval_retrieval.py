"""Evaluate hybrid retrieval for the shopping assistant: strict ID metrics + LLM-judged relevance (Ragas)."""
import argparse, asyncio, math, os, time
from pathlib import Path

import mlflow
import pandas as pd
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import ContextRelevance

from helpers.config import get_settings
from main import app, lifespan
from models.enums.DataBaseEnums import DataBaseEnums

KS = (1, 3, 5, 10)


def product_text(p) -> str:
    return f"{p.title}\n{(p.description or '')[:500]}\nprice: {p.price}"


async def retrieve_all(df, args):
    ids, texts, latencies = [], [], []
    async with lifespan(app):
        for q in df["query"]:
            t0 = time.monotonic()
            products = await app.retrieval_controller.hybrid_search(
                query=q.strip(), top_k=args.top_k, category_name=args.category_name
            )
            latencies.append(time.monotonic() - t0)
            ids.append([str(p.source_id) for p in products])
            texts.append([product_text(p) for p in products])
    return ids, texts, latencies


def main(args):
    df = pd.read_csv(args.csv, dtype={"product_id": str})
    assert {"query", "product_id"} <= set(df.columns), "CSV needs: query, product_id"
    df["product_id"] = df["product_id"].str.strip()
    
    if args.limit:
        df = df.head(args.limit)
        
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1) retrieval
    ids, texts, latencies = asyncio.run(retrieve_all(df, args))
    df["retrieved_ids"], df["latency_s"] = ids, latencies

    # 2) strict metrics (only the labeled product counts as correct)
    df["rank"] = [i.index(pid) + 1 if pid in i else None for i, pid in zip(ids, df["product_id"])]
    df["rr"] = df["rank"].map(lambda r: 1 / r if pd.notna(r) else 0.0)
    found = df["rank"].notna()
    metrics = {
        "queries": len(df),
        "strict_mrr": df["rr"].mean(),
        "miss_rate": 1 - found.mean(),                      # labeled product not in top_k
        "mean_rank_when_found": df.loc[found, "rank"].mean(),
        "empty_results_rate": sum(not i for i in ids) / len(ids),
        "latency_p50_s": df["latency_s"].quantile(0.5),
        "latency_p95_s": df["latency_s"].quantile(0.95),
    }
    for k in KS:
        if k <= args.top_k:
            metrics[f"strict_hit_at_{k}"] = (df["rank"] <= k).mean()
            metrics[f"strict_ndcg_at_{k}"] = df["rank"].map(
                lambda r: 1 / math.log2(r + 1) if pd.notna(r) and r <= k else 0.0
            ).mean()

    from ragas.metrics import ContextRelevance

    # 3) LLM-judged relevance of the top judge_k results (catches relevant products the labels miss)
    samples = [
        SingleTurnSample(
            user_input=q, 
            retrieved_contexts=t[: args.judge_k]
        )
        for q, t in zip(df["query"], texts)
    ]
    
    from langchain_groq import ChatGroq
    judge = LangchainLLMWrapper(
        ChatGroq(model=get_settings().GENERATION_MODEL, temperature=0, max_tokens=1024)
    )
    
    judged = evaluate(
        EvaluationDataset(samples=samples), metrics=[ContextRelevance()],
        llm=judge, raise_exceptions=False,
    ).to_pandas()
    for name, value in judged.select_dtypes("number").mean().items():
        metrics[f"judge_{name}"] = value
    metrics["judged_queries"] = len(judged)

    # 4) save + log
    df.to_csv(out / "retrieval_results.csv", index=False)
    judged.to_csv(out / "judge_scores.csv", index=False)

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
    mlflow.set_experiment(args.experiment)
    
    import subprocess
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        git_commit = "unknown"
        
    with mlflow.start_run(run_name=args.run_name):
        mlflow.set_tag("git_commit", git_commit)
        mlflow.set_tag("framework", "ragas")
        mlflow.log_params({"csv": args.csv, "top_k": args.top_k, "judge_k": args.judge_k,
                           "category": args.category_name, 
                           "generation_model": get_settings().GENERATION_MODEL,
                           "embedding_model": get_settings().EMBEDDING_MODEL})
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
        mlflow.log_artifacts(str(out))

    for k, v in metrics.items():
        print(f"{k}: {v:.4f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--judge-k", type=int, default=5)  # results judged per query
    p.add_argument("--category-name", default=DataBaseEnums.DEFAULT_CATEGORY_NAME.value)
    p.add_argument("--experiment", default="retrieval-eval")
    p.add_argument("--run-name")
    p.add_argument("--limit", type=int, default=50, help="Limit number of evaluation examples")
    p.add_argument("--output-dir", default="eval_outputs")
    main(p.parse_args())