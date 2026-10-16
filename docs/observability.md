# Observability

[Back to the README](../README.md)

## LLM tracing with Langfuse

Each chat request is one trace in [Langfuse](https://langfuse.com), named `chat-turn`, containing every model call and tool call with token usage and cost. Traces are grouped into one session per conversation and attributed to the user.

Inside each `search_catalog` call the retrieval pipeline is traced step by step: `hybrid-search` contains `vector-search` (with `embed-query`), `keyword-search`, `fuse-results` and `rerank-results`, each with its duration and the product IDs and scores it returned. A slow or wrong answer can be traced to the exact step that caused it.

Guardrail decisions appear in the same trace, as described in [Guardrails](evaluation.md#guardrails).

## Prompt management

The agent's prompts are served from Langfuse, not from code:

| Langfuse prompt | Purpose |
| --- | --- |
| `shopping-agent/system` | The agent's system prompt. |
| `shopping-agent/first-turn-memory` | Extra instruction on the first turn of a conversation. |

The application serves the version labelled `production`. A new version is published under `staging`, evaluated, and promoted by moving the label; the running application picks it up within about a minute. Each model call in a trace is linked to the prompt version that produced it.

`src/agent/Templates.py` holds the fallback text, used when Langfuse is not configured or cannot be reached. To create the prompts in a new Langfuse project:

```bash
uv run python scripts/seed_langfuse_prompts.py
```

## User feedback

`POST /api/v1/chat/feedback` records a customer's rating of a reply as a `response_rating` score on that reply's trace, so poorly rated answers can be found and inspected.

## Service monitoring with Prometheus and Grafana

Langfuse shows what the agent did; Prometheus and Grafana show how the service is doing. FastAPI exposes request count and latency at `/metrics`, labelled by method, route template and status code. The API runs several Uvicorn workers, so metrics use the Prometheus client's multiprocess mode and every scrape reports all workers together. The Docker Compose stack runs Prometheus, Grafana, Node Exporter and PostgreSQL Exporter alongside the API.

Grafana starts with the Prometheus data source and a **Shopping Assistant: API and infrastructure** dashboard already provisioned (`docker/grafana/`):

| Panel | What it answers |
| --- | --- |
| API up, Database up | Is the service reachable and is PostgreSQL up? |
| Requests per second, by route and by status code | How much traffic, where, and how much of it fails? |
| Chat latency p50 and p95 | How long a customer waits for a reply, model and search included. |
| Server error rate | Share of requests answered with a 5xx error. |
| Latency by route (p95) | Which endpoint is slow. |
| Database connections, host CPU and memory | Is the infrastructure under strain? |

Tracing is off by default. Set `LANGFUSE_TRACING_ENABLED=true` with the Langfuse keys (see `.env.example`); the application refuses to start if tracing is enabled without keys. With tracing on, user messages, replies, tool results and stored facts are sent to Langfuse.
