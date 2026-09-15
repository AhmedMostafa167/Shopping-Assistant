# Shopping Assistant

A production-oriented shopping assistant for e-commerce catalogs. It searches products semantically, remembers a user's preferences across sessions, and decides for itself which action to take on each turn — search the catalog, recall stored memory, compare items, or reply directly — rather than following one fixed retrieval pipeline.

Built with a scalable, service-oriented architecture: a thin API layer, isolated business logic per controller, a swappable provider layer for LLM and vector-store backends, and a clean separation between structured product data and vector search — designed so any layer (embedding model, LLM provider, vector store) can be swapped without touching the others.

## What it does (target scope)

- **Semantic product search** over an e-commerce catalog, powered by vector embeddings for retrieval quality beyond keyword matching.
- **Agentic tool-routing** — an LLM decides per turn whether to search the catalog, read/write memory, compare products, or reply directly.
- **Cross-session memory with conflict resolution** — user preferences persist across separate conversations, and contradicting statements update stored facts instead of duplicating them.
- **Product comparison** over 2+ catalog items.

## Current status

Data ingestion and storage are in place; the agent/memory layer has not been built yet.

- [x] Category, Asset, and Product tables (PostgreSQL + SQLAlchemy + Alembic)
- [x] File upload → validate → store pipeline (`/api/v1/data/upload`, `/validate`, `/store`)
- [x] pgvector table creation, indexing (HNSW/IVFFlat + category B-tree), and vector search
- [x] Catalog dataset filtered to target categories, embedding-ready
- [ ] Embedding endpoint (in progress)
- [ ] Agentic tool-routing
- [ ] Cross-session memory + conflict resolution
- [ ] Product comparison
- [ ] Evaluation suite

## Architecture

```
Client
  │
  ▼
FastAPI routes  →  Controllers  →  Models (SQLAlchemy)  →  PostgreSQL
                         │                                   + pgvector
                         ▼
                 LLM / Vector-DB providers (factory pattern)
```

**Design principles:**
- **Layered, single-responsibility structure.** Routes stay thin (request/response only); controllers hold business logic; models are the only layer that talks to the database.
- **Provider-agnostic integrations.** LLM and vector-store access go through factory interfaces, so swapping providers (e.g. a different embedding model, a different vector database) is a configuration change, not a rewrite.
- **Two-store split for scalability.** Product attributes (frequently read, occasionally updated) live in relational tables; embeddings (rarely change, read via similarity search) live in a separate pgvector table — joined by `product_id`. This keeps writes to mutable product data from ever touching the vector index.
- **Idempotent, batch-oriented ingestion.** Bulk data loads are upserted by a stable source ID, so re-running ingestion is always safe.

Data flow for a new product batch:
1. **Upload** — file is validated and saved to disk; an `Asset` record is created.
2. **Validate** — the file is loaded into a DataFrame, each row validated against a schema; invalid rows are dropped and reported.
3. **Store** — valid rows become `Product` rows in Postgres, linked to their `Asset` and `Category`.
4. **Embed** *(in progress)* — `title + description` is embedded and written to a pgvector table, keyed by `product_id`.

## Tech stack

- **API:** FastAPI (async)
- **Database:** PostgreSQL + pgvector, via SQLAlchemy (async) and Alembic migrations
- **Data processing:** pandas, Hugging Face `datasets` for bulk catalog ingestion
- **Embeddings:** sentence-transformers (prototyping) → ONNX Runtime (production target, for minimal image footprint)
- **LLM:** Cohere (current provider), behind a swappable factory interface

## Setup

**Requirements:** Python 3.12+, Docker

```bash
# 1. Start Postgres + pgvector
cd docker
docker compose up -d

# 2. Install dependencies
cd ../src
pip install uv
uv sync

# 3. Configure environment
cp .env.example .env
# fill in POSTGRES_*, EMBEDDING_MODEL, LLM API keys, etc.

# 4. Run migrations
alembic upgrade head

# 5. Start the API
uvicorn main:app --reload
```

## Project structure

```
src/
├── controllers/     # business logic — one responsibility per controller
├── models/          # DB access layer (one class per table) + SQLAlchemy schemas
├── routes/          # thin FastAPI route handlers
├── stores/
│   ├── llm/         # LLM provider factory (Cohere, swappable)
│   └── vectordb/    # pgvector provider — table creation, indexing, search
└── main.py
```

## Design notes

- **Ingestion is a script, not an endpoint** for bulk catalog loads — no external caller needs to trigger it. The upload/validate/store *endpoints* exist for adding new products incrementally after the initial load.
- **Embedding model choice is decoupled from query time via `.env`** — the same model name must be used to embed both the catalog and the query, or vector search silently compares two different embedding spaces.
- **Category and vector indexes are created idempotently** — safe to re-run after every ingestion batch without duplicate-index errors.