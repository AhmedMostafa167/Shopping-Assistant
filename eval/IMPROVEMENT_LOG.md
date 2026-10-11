# Improvement log

Each entry records one measured change to the shopping assistant: what was measured, the
numbers before and after, what they showed, and the decision taken because of them.
Entries are in the order the work happened.

## Summary

| # | Date | Change | Measure | Before | After |
|---|---|---|---|---|---|
| 1 | 2026-10-11 | Whole catalogue embedded | Products reachable by semantic search | 1,300 of 12,730 | 12,730 of 12,730 |
| 2 | 2026-10-11 | Vector index added | Median vector search time | 35 ms | 3.1 ms |
| 3 | 2026-10-11 | Search stages compared | Right product in top 10 | keyword 56%, vector 41% | hybrid 72% |
| 4 | 2026-10-11 | Reranking measured | Right product ranked first | hybrid 23% | hybrid + rerank 43% (+20 points, +89% relative) |
| 5 | 2026-10-11 | Agent behaviour baseline | Tasks passed in all 3 runs | not measured | 9 of 12 |

## How the retrieval numbers are produced

- **Data:** `eval/evalset.csv` holds 508 labelled queries for 127 products, four phrasings per
  product (`category`, `feature`, `short`, `need`).
- **Queries used:** one per product, 127 in total, with the phrasing rotated evenly. Four
  phrasings of one product are not independent evidence, so each product counts once. The
  selection is fixed in code (`eval/retrieval_metrics.py`).
- **A hit:** the labelled product is returned, or an exact duplicate of it (same title and
  description). The catalogue contains 71 groups of such duplicates.
- **Uncertainty:** the queries are a sample of everything users might ask, so every hit rate
  is an estimate. Each is shown with a 95% Wilson confidence interval: the range the rate over
  all possible queries is likely to fall in, given the sample size. It shows how far a sample
  result may sit from the full picture. With 127 queries the interval is about ±8 points; with
  40 queries, about ±15. Two modes run on the same queries are also compared query by query,
  which is a sharper test than comparing two intervals.
- **Mean reciprocal rank (MRR):** each query scores 1 divided by the position of the right
  product (first = 1, second = 0.5, third = 0.33, not returned = 0); MRR is the average. It
  rewards placing the right product near the top.
- **Cost control:** reranking is the only step billed per search, so it is run on a fixed
  subset of 40 of the 127 queries. Results are saved per query, so an interrupted run resumes
  without paying twice.
- **Reproduce:** `PYTHONPATH=src:eval uv run python eval/eval_retrieval.py --mode <vector|keyword|hybrid|hybrid_rerank>`.
  Runs are also logged to MLflow under the experiment `retrieval-stages`.

## Entry 0 — Starting point (2026-10-05 to 2026-10-07)

The first evaluation ran the production path (hybrid search with reranking) on the first 50
rows of the evaluation set.

| Measure | Value |
|---|---|
| Right product in top 10 | 50% |
| Mean reciprocal rank | 0.47 |

**What was wrong with it, found later.** The embedding endpoint indexed one page of 1,300
products and stopped, so 90% of the catalogue had no embedding. Only 16 of the 127 labelled
products could be returned by semantic search at all. The score mostly measured that gap.

## Entry 1 — Embed the whole catalogue (2026-10-11)

**Change.** The embedding endpoint now works through every product that has no embedding yet,
in batches of 96, saving each batch before the next. It can be re-run safely and resumes after
a failure.

| Measure | Before | After |
|---|---|---|
| Products with an embedding | 1,300 | 12,730 |
| Labelled evaluation products with an embedding | 16 of 127 | 127 of 127 |

**Cost.** About 2.5 million tokens, roughly $0.25, confirmed against a 96-product trial
(19,555 tokens for $0.002) before the full run.

**Decision.** Embed everything. A random or keyword-filtered sample was considered and
rejected: it saves about 25 cents and makes the claim "semantic search over the catalogue" untrue.

## Entry 2 — Add a vector index (2026-10-11)

**Change.** An HNSW index for cosine distance. The index code existed but was never called,
would have failed if called, and the search query was written in a form that cannot use an index.

Measured on the same 100 searches through the application's own search code:

| Measure | Exact search | With index |
|---|---|---|
| Median time | 35 ms | 3.1 ms |
| 95th percentile | 46 ms | 4.1 ms |
| Exact top-10 results still returned | 100% | 99.7% |

**Finding.** The index is approximate: in 2 of 100 searches it missed one or two of the true
top 10.

**Decision.** Keep it. An eleven-fold speed-up for a 0.3% loss in the first stage of a
pipeline that is then fused and reranked.

## Entry 3 — Compare the search stages (2026-10-11)

127 queries, no reranking. Ranges are 95% confidence intervals.

| Mode | Right product first | In top 3 | In top 10 | Median time |
|---|---|---|---|---|
| Keyword only | 36% (28–45) | 47% | 56% (47–64) | 3 ms |
| Vector only | 15% (10–22) | 24% | 41% (33–50) | 190 ms |
| Hybrid (fused) | 24% (18–33) | 54% | 72% (63–79) | 190 ms |

Right product in the top 10, by how the query is phrased:

| Phrasing | Keyword | Vector | Hybrid |
|---|---|---|---|
| Category ("12-inch rubber gear tie 4 pack") | 94% | 41% | 97% |
| Feature ("40 exposures instax mini film pack") | 66% | 38% | 72% |
| Short ("waterproof speaker") | 58% | 26% | 55% |
| Need ("I need a high-quality wide-angle lens for low-light…") | 6% | 59% | 62% |

**Findings.**

1. **The two searches fail on different queries.** Keyword search needs every query word to
   appear in the product, so it returned nothing for 32 of 127 queries, 28 of them
   natural-language requests. Vector search handles those and is weak on exact product
   wording. 44 queries were found only by keyword, 25 only by vector. Hybrid search is
   justified by this.
2. **Fusion favours vector search when the two disagree.** When keyword and vector each put a
   different product first, both get the same fusion score and the tie goes to the vector
   result. On these queries keyword's first choice is right more than twice as often. In 30
   queries this pushed the right product from first place to second. A well-worded query can
   be answered correctly by keyword search and then demoted by fusion, which is why a
   reranking step is needed.
3. **Almost all of the search time is the embedding API call.** Of the 190 ms, the indexed
   database lookup is about 3 ms. Using a hosted API for embeddings is simple to run, and it
   is where the time goes.
4. **The labels understate quality.** An LLM judge rated the top 5 hybrid results as relevant
   for 0.97 of 30 queries, while the labelled product was in the top 5 for 60%. The catalogue
   has many near-equivalent products. The judge is not calibrated against human labels and is
   close to its maximum, so this is supporting evidence only.

**Decisions.** Keep hybrid search. Measure reranking next, since finding 2 predicts it should
recover first-place accuracy. Leave the fusion tie-break unchanged until that is measured.

## Entry 4 — Measure reranking (2026-10-11)

The same 40 queries through each mode. The reranker returns its best 3 of the 10 fused candidates.

| Mode | Right product first | In top 3 | Returned at all | Median time |
|---|---|---|---|---|
| Keyword only | 30% (18–45) | 43% | 50% (top 10) | 4 ms |
| Hybrid (fused) | 23% (12–38) | 50% | 68% (top 10) | 245 ms |
| Hybrid + rerank | 43% (29–58) | 60% | 60% (top 3) | 457 ms |

What reranking changed, against plain hybrid on the same queries:

| Measure | Hybrid | Hybrid + rerank | Change | Relative |
|---|---|---|---|---|
| Right product first | 22.5% | 42.5% | +20 points | +89% |
| Right product in top 3 | 50.0% | 60.0% | +10 points | +20% |
| Mean reciprocal rank | 0.386 | 0.508 | +0.122 | +32% |
| Median search time | 245 ms | 457 ms | +212 ms | +87% |

Query by query:

| Comparison | Rerank better | Rerank worse | Same |
|---|---|---|---|
| Right product first | 10 | 2 | 28 |
| Right product in top 3 | 5 | 1 | 34 |

**Findings.**

1. **Reranking repairs the ordering.** First-place accuracy rose from 23% to 43%, better on
   10 queries and worse on 2 (sign test p = 0.04). It also beats keyword-only (30%), so it
   more than undoes the fusion problem from entry 3.
2. **The 3-result limit costs coverage.** Fused search had the right product somewhere in its
   10 results for 27 queries. After reranking to 3, it was kept for 24 and dropped for 3.
3. **Reranking doubles search time.** It adds about 210 ms, another hosted API call. Embedding
   and reranking together account for nearly all of the 457 ms. Hosted APIs are the simplest
   way to run these models, and this is their cost in latency.
4. **The sample is small.** 40 queries give intervals of about ±15 points. The first-place
   improvement is clear in the paired comparison; the top-3 improvement (p = 0.22) is not
   established.
5. **First place matters less to the agent than to a results page.** The agent passes all
   returned products to the generation model, so what matters most there is whether the right
   product is among them, not its position. Of the 10 queries where reranking moved the right
   product to first place, 8 already had it in hybrid's top 3; only 2 were brought in from
   further down. Without reranking the agent would receive the top 5 fused results, which
   contain the right product for 57.5% of these queries; with reranking it receives 3, which
   contain it for 60%. So for the agent, reranking gives about the same coverage with fewer
   products to read, at the price of one paid call and about 210 ms. Whether that improves
   the final answer is a question for the agent-level evaluation.
6. **How many products to pass is a trade-off.** More products give the generation model more
   grounded options to answer from; fewer products mean fewer input tokens per turn. At
   current prices the token saving is not a money saving: two fewer products save about
   $0.0001 of generation input per turn, while the rerank call costs about $0.0025. What the
   smaller list buys is headroom under the generation model's tokens-per-minute limit and a
   shorter prompt. The choice depends on which matters more for the product: coverage, or
   tokens and latency.

**Cost.** 40 rerank calls, about $0.10.

**Decisions.** Keep reranking in the production path. Leave the 3-result limit as it is for
now: returning more products means more tokens per agent turn, which matters under the
generation model's rate limit.

## Entry 5 — Agent behaviour baseline (2026-10-11)

**What was measured.** 12 tasks (`eval/agent_tasks.json`), each a short conversation with a
fresh user, run 3 times through the real chat path with system prompt
`shopping-agent/system` version 1 and the model `openai/gpt-oss-20b`. Six code checks read
the agent's tool calls, its reply, and the memory table afterwards. No LLM judge is used.
A task counts as passed only if every applicable check passes in all 3 runs.

| Check | What it verifies | Passed |
|---|---|---|
| `memory_read_first` | Stored facts are read before anything else | 36 of 36 (100%) |
| `prices_grounded` | Every price stated comes from a tool result or the user | 25 of 25 (100%) |
| `budget_respected` | No price above the user's limit | 6 of 6 (100%) |
| `search_uses_memory` | A stored fact is used in the search query | 3 of 3 (100%) |
| `tools_as_expected` | Required tools used, forbidden ones not | 25 of 27 (93%) |
| `memory_write_correct` | The memory table holds what it should | 27 of 30 (90%) |

| Result | Value |
|---|---|
| Tasks passed in all 3 runs | 9 of 12 |
| Runs passing every check | 31 of 36 (86%) |

The three tasks that did not pass reliably:

| Task | Runs passed | What went wrong |
|---|---|---|
| One-off request ("Show me a wireless charger for my car.") | 1 of 3 | Stored the request as a lasting preference |
| Store a constraint ("My budget for accessories is always under $20.") | 1 of 3 | Ran a search nobody asked for |
| No duplicate fact (Samsung preference already stored) | 2 of 3 | Added "User wants a Samsung charger" as a second fact |

**Findings.**

1. **The main failure is storing one-off requests as lasting facts.** It failed two graded
   tasks, and also happened in all 3 runs of the budget task ("User wants a phone case under
   $15"), where it is not graded because whether to store it is debatable.
2. **The agent searches when not asked.** 6 of the 28 catalogue searches came from tasks that
   only asked it to remember something. Each is a paid rerank call and extra latency.
3. **The same task can pass and fail.** Three tasks gave different results across runs, which
   a single run would have hidden. This is why each task runs 3 times.
4. **The baseline is better than the earlier impression.** A single trace read by hand had
   shown memory being read after the search. Over 36 runs that never happened.
5. **Two problems the checks do not cover, seen in the transcripts.** The recommendation score
   is presented to the user as a "rating" in most product replies, and products without a
   price appear as "$nan" (7 of 36 replies). Both come from how the tool formats its output.
6. **The checks graded fairly.** Every failed run was read by hand; each is a real behaviour
   problem, not a grading error.

**Limits.** 12 tasks is a small set, written by hand from observed failures. Four checks sit
at 100% and can only detect a regression, not an improvement. "Do you sell kayaks?" was
answered correctly without checking the catalogue; the task does not require a search.

**Cost.** 28 searches, about $0.07 in reranking. The generation model's free tier allows
8,000 tokens per minute, so conversations were spaced 65 seconds apart (about 40 minutes).

**Reproduce.** `PYTHONPATH=src:eval uv run python eval/eval_agent.py --label <name>`. Each run
is a trace in Langfuse (experiment `agent-behaviour`) with the check results as scores; the
summary is in MLflow under `agent-behaviour`.

**Decision.** Use this as the baseline for prompt changes. The first candidates, in order of
evidence: stop storing one-off requests, stop searching when not asked, and fix the tool
output wording (score label, missing prices).

## Entry 6 — Prompt version 2 and tool wording (2026-10-11, in progress)

**Change.** Three changes measured in one evaluation against the entry 5 baseline:

1. System prompt version 2, rule on memory: store a fact only if it would still be true in a
   future, unrelated conversation; what the user is shopping for right now is a request, not
   a fact about them.
2. System prompt version 2, rule on searching: search or filter only when the user asks for
   products in the current message.
3. Tool output wording: the score is labelled as a recommendation score that is not the
   average rating, and a missing price is shown as "price not listed" instead of "$nan".

Version 2 is published in Langfuse under the label `staging`. Production keeps serving
version 1 until the evaluation is complete and the result is accepted.

A seventh check, `missing_price_not_shown`, was added for change 3. The baseline was
re-scored with it from its saved transcripts.

**Status.** 19 of the 36 runs are complete (all 12 tasks once, 7 of them twice). The
generation model's free tier allows 200,000 tokens per day, and the day's allowance ran out.
The remaining 17 runs resume from the saved results when it is available again.

**Partial result,** comparing the 19 completed runs with the same 19 task-and-run slots of
the baseline:

| Check | Baseline (v1) | Version 2 |
|---|---|---|
| `memory_write_correct` | 14 of 16 | 16 of 16 |
| `tools_as_expected` | 11 of 13 | 13 of 13 |
| `missing_price_not_shown` | 11 of 14 | 11 of 11 |
| `memory_read_first` | 19 of 19 | 19 of 19 |
| `prices_grounded` | 14 of 14 | 11 of 11 |
| `budget_respected` | 3 of 3 | 3 of 3 |
| `search_uses_memory` | 2 of 2 | 2 of 2 |
| Runs passing every check | 13 of 19 | 19 of 19 |

| Other measures, same 19 runs | Baseline (v1) | Version 2 |
|---|---|---|
| Catalogue searches made | 15 | 10 |
| Runs with a search nobody asked for | 5 | 0 |
| Product replies using the word "rating" | 10 of 14 | 6 of 11 |

**What it shows so far.** The two targeted failures did not occur: no one-off request was
stored and no unrequested search was made. The tasks that must still store a fact or still
search kept passing, so the prompt was not over-corrected. Fewer searches means lower cost
per conversation. The score is still called a "rating" in about half of the product
replies, so the wording change helped only partly.

**Not yet a conclusion.** This is 19 runs, and consistency across three runs per task is
exactly what remains to be measured. No decision on promoting version 2 until all 36 are in.

**Finding about the process.** The daily token limit is not reported in the model API's
response headers, only in the error returned once it is exceeded, so it was not planned for.
One full agent evaluation uses roughly half a day's allowance. The runner now stops after
two failed conversations in a row and does not log an incomplete evaluation as a result.

## Open questions

- **Local embedding and reranking models.** Both hosted calls could be replaced by models run
  alongside the application, removing the network round trip. Whether that is faster depends
  on the model size and the available hardware, and smaller local models may rank less well.
  It is a trade-off between latency, quality, per-call cost and operating effort, to be
  measured with this same evaluation before deciding.

- Fix the fusion tie-break (free) and measure whether first-place accuracy improves before reranking.
- Keyword search returns nothing for natural-language queries; matching any word instead of every word may help.
- Whether returning more than 3 reranked products is worth the extra tokens.
