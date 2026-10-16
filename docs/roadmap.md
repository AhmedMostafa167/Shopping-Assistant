# Roadmap and future work

[Back to the README](../README.md)

Guardrails and safety:

- Authentication and authorisation between the store and the API, and per-store separation of data.
- Rate limiting per customer and per client.
- A trained prompt-injection classifier in place of the pattern-based memory filter, which catches plain instructions but not paraphrased ones.
- A run-time check that every price in a reply exists in the tool results (the evaluation's `prices_grounded` check, applied live).
- Treating retrieved product descriptions as untrusted: truncation and clear marking as data.
- Masking personal data before it is sent to Langfuse.
- Memory consolidation when a customer reaches the fact limit, instead of refusing new facts.

Agent and retrieval:

- Harder evaluation tasks: longer conversations and requests the catalogue cannot satisfy.
- Stop the recommendation score being called a "rating" in replies.
- Keyword search returns nothing for some natural-language queries; test a looser full-text query.
- Local embedding and reranking models, measured against the hosted ones for latency, quality and cost.

Platform:

- An evaluation gate in CI that blocks a merge on a behaviour regression.
- Online LLM-judge evaluators on live traffic.
- Endpoints to list and delete conversations and memories, and product links and add-to-cart on the cards.
- A product comparison tool.
- Background ingestion jobs with durable status for very large catalogues.
