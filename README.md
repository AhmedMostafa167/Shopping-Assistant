# Shopping Assistant

[![CI](https://github.com/AhmedMostafa167/Shopping-Assistant/actions/workflows/CI.yml/badge.svg)](https://github.com/AhmedMostafa167/Shopping-Assistant/actions/workflows/CI.yml)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent-1C3C3C)](https://langchain-ai.github.io/langgraph/)
[![Cohere](https://img.shields.io/badge/Cohere-LLM%20%7C%20Embeddings%20%7C%20Reranking-39594D)](https://cohere.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-Vector%20Search-3B82F6)](https://github.com/pgvector/pgvector)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-D71F00)](https://www.sqlalchemy.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Pytest](https://img.shields.io/badge/Pytest-Tests-0A9EDC?logo=pytest&logoColor=white)](https://pytest.org/)
[![uv](https://img.shields.io/badge/uv-Dependencies-DE5FE9)](https://docs.astral.sh/uv/)

Shopping Assistant is a FastAPI backend for conversational product discovery over an e-commerce catalog. It combines structured product data, PostgreSQL full-text search, Cohere embeddings, pgvector similarity search, reciprocal-rank fusion, and Cohere reranking behind a LangGraph-powered conversational agent.

The application also maintains user profiles, conversations, and durable shopping facts such as preferences, constraints, and purchase history.

> **Project status:** The core ingestion, retrieval, chat, memory, persistence, migrations, Docker deployment, and test paths are implemented. Authentication, authorization, product comparison, and a production-grade background ingestion worker are not currently implemented.

## Contents

- [Key capabilities](#key-capabilities)
- [How the system works](#how-the-system-works)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Configuration](#configuration)
- [Run locally](#run-locally)
- [Run with Docker Compose](#run-with-docker-compose)
- [Database and migrations](#database-and-migrations)
- [Using the API](#using-the-api)
- [Catalog ingestion workflow](#catalog-ingestion-workflow)
- [Retrieval pipeline](#retrieval-pipeline)
- [Conversation and memory workflow](#conversation-and-memory-workflow)
- [Embedding rate-limit protection](#embedding-rate-limit-protection)
- [Observability](#observability)
- [Testing and CI](#testing-and-ci)
- [Important implementation notes](#important-implementation-notes)
- [Roadmap](#roadmap)
- [License](#license)

## Key capabilities

### Conversational shopping agent

- Accepts a user message through the chat API.
- Uses LangGraph to decide whether to search products, filter products, read memory, write memory, or answer directly.
- Uses Cohere for chat generation, embeddings, and reranking.
- Persists LangGraph checkpoints in PostgreSQL so conversation state can continue across requests.

### Hybrid product retrieval

- **Semantic search:** product title and description embeddings are stored in pgvector.
- **Keyword search:** PostgreSQL full-text search uses a generated `tsvector` column and a GIN index.
- **Rank fusion:** vector and keyword results are combined with Reciprocal Rank Fusion (RRF).
- **Neural reranking:** the fused product candidates are passed to Cohere Rerank before being returned.
- **Category filtering:** vector search is performed against a category-specific embedding table and filters products by category.

### Catalog ingestion

The data API supports a staged workflow:

1. Upload a catalog file.
2. Validate rows against the product input schema.
3. Store valid products in PostgreSQL.
4. Generate embeddings and index them in pgvector.

Supported source formats are determined by the file extension and include CSV, Excel, JSON, Parquet, and Arrow IPC files.

### Long-term shopping memory

- Creates a profile for a username when needed.
- Stores facts as `preference`, `constraint`, or `history`.
- Reads up to 50 facts for a user, ordered by confidence and recency.
- Allows the agent to modify an existing fact instead of creating a duplicate when a preference changes.
- Associates memories and conversations with a profile.

### Operational features

- Alembic migrations for the relational schema.
- Docker Compose deployment with FastAPI, PostgreSQL/pgvector, Nginx, Prometheus, Grafana, PostgreSQL Exporter, and Node Exporter.
- Prometheus request-count and request-latency metrics.
- GitHub Actions workflow for linting and tests.
- Pytest regression coverage for retrieval, RRF, memory updates, request validation, reranking, and embedding rate-limit handling.

## How the system works

### Application startup

The FastAPI lifespan initializes the following components:

1. SQLAlchemy async engine and session factory.
2. PostgreSQL/pgvector provider.
3. Cohere embedding, chat, and reranking clients.
4. Product, profile, memory, and conversation models.
5. Retrieval and memory controllers.
6. LangGraph with a PostgreSQL checkpointer.

### Product search flow

```text
User query
   |
   v
LangGraph agent
   |
   +--> search_catalog tool
           |
           +--> PostgreSQL full-text search
           +--> Cohere query embedding -> pgvector search
                       |
                       v
                Reciprocal Rank Fusion
                       |
                       v
                Product lookup by IDs
                       |
                       v
                Cohere Rerank
                       |
                       v
                Products returned to agent
```

### Data flow

```text
Catalog file
   |
   v
Upload -> Validate -> Store products in PostgreSQL
                              |
                              v
                  Embed title + description with Cohere
                              |
                              v
                  Store vectors in category pgvector table
```

## Architecture

The code is organized into a layered service-oriented structure:

```text
FastAPI routes
    |
    v
Controllers
    |
    +--> SQLAlchemy models ---> PostgreSQL
    |
    +--> LLM provider --------> Cohere
    |
    +--> Vector DB provider --> PostgreSQL + pgvector
    |
    +--> LangGraph agent -----> Tools and persistent checkpoints
```

### Main layers

- **Routes (`src/routes/`)**: HTTP request validation and response handling.
- **Controllers (`src/controllers/`)**: ingestion, preprocessing, embedding, retrieval, and file-management logic.
- **Models (`src/models/`)**: database access methods and SQLAlchemy schema definitions.
- **LLM providers (`src/stores/llm/`)**: Cohere chat, embedding, and reranking integration behind a provider factory.
- **Vector database providers (`src/stores/vectordb/`)**: pgvector table management, indexing, insertion, and similarity search.
- **Agent (`src/agent/`)**: LangGraph state, prompts, tools, and memory orchestration.
- **Utilities (`src/utils/`)**: rank fusion and Prometheus metrics.

### Database entities

| Entity | Purpose |
| --- | --- |
| `categories` | Catalog categories and category metadata. |
| `assets` | Uploaded catalog files and their category association. |
| `products` | Structured catalog products, including title, description, price, rating, store, and image. |
| `profiles` | Application-level user identity represented by a username. |
| `memories` | Durable user facts with type, content, confidence, and ownership. |
| `conversations` | Public conversation UUID, LangGraph thread ID, title, timestamps, and profile ownership. |
| LangGraph checkpoint tables | Persistent graph state created by `AsyncPostgresSaver`. |
| `table_<embedding_size>_<category>` | Category-specific pgvector table containing product embeddings and product IDs. |

## Technology stack

- **Python:** 3.12 or newer for local development.
- **API:** FastAPI and Uvicorn.
- **Database:** PostgreSQL with the pgvector extension.
- **ORM:** SQLAlchemy async sessions.
- **Migrations:** Alembic.
- **Agent orchestration:** LangGraph.
- **LLM provider:** Cohere through `langchain-cohere`.
- **Embeddings:** Cohere Embed through `CohereEmbeddings`.
- **Vector search:** PostgreSQL pgvector with cosine-style distance queries.
- **Keyword search:** PostgreSQL `tsvector` and GIN indexing.
- **Data processing:** pandas and PyArrow.
- **Dependency management:** uv with the committed `uv.lock` file.
- **Observability:** Prometheus client, Prometheus, Grafana, PostgreSQL Exporter, and Node Exporter.

## Repository layout

```text
.
├── .env.example                         Application configuration template
├── .github/workflows/CI.yml             GitHub Actions lint/test workflow
├── docker/
│   ├── docker-compose.yml               Local multi-service deployment
│   ├── nginx/default.conf               Nginx reverse proxy
│   ├── prometheus/prometheus.yml        Prometheus scrape configuration
│   └── shopping_assistant/              Application image and migration entrypoint
├── src/
│   ├── agent/                           LangGraph agent, prompts, tools, and memory
│   ├── controllers/                     Application and retrieval logic
│   ├── models/                          Database models and Alembic migrations
│   ├── routes/                          FastAPI routes and request schemas
│   ├── stores/                           LLM and vector database providers
│   └── utils/                           RRF and metrics utilities
├── tests/                               Regression and integration-style unit tests
├── pyproject.toml                       Dependencies and project metadata
├── uv.lock                              Locked dependency resolution
└── LICENSE
```

## Requirements

### Required for all deployments

- Python 3.12+ for local execution, or Docker for containerized execution.
- A PostgreSQL server with the `vector` extension, or the provided pgvector Docker image.
- A Cohere API key.
- A catalog file with the fields described in [Catalog ingestion workflow](#catalog-ingestion-workflow).

### Recommended local tools

- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose
- `curl` or another HTTP client

## Configuration

Copy the root template and fill in the required values:

```bash
cp .env.example .env
```

The application reads `.env` through `pydantic-settings`.

### Application variables

| Variable | Required | Description | Example |
| --- | --- | --- | --- |
| `APP_NAME` | Yes | Application display name. | `shopping_assistant` |
| `APP_VERSION` | Yes | Application version returned by the welcome endpoint. | `0.1.0` |
| `POSTGRES_USERNAME` | Yes | PostgreSQL username. | `postgres` |
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password. | `change-me` |
| `POSTGRES_DB` | Yes | Application database name. | `shopping_assistant` |
| `POSTGRES_HOST` | Yes | PostgreSQL hostname. Use `localhost` locally or `pgvector` in Compose. | `localhost` |
| `POSTGRES_PORT` | Yes | PostgreSQL port. | `5432` |
| `POSTGRES_MAIN_DATABASE` | Yes | Main PostgreSQL database setting retained by the configuration model. | `postgres` |
| `VECTOR_DB_BACKEND` | Yes | Vector provider backend. | `pgvector` |
| `LLM_BACKEND` | Yes | LLM provider backend. | `CoHere` |
| `COHERE_API_KEY` | Yes | Cohere API key. Never commit this value. | `...` |
| `EMBEDDING_MODEL` | Yes | Cohere embedding model identifier. | `embed-english-v3.0` |
| `EMBEDDING_MODEL_SIZE` | Yes | Stored vector dimension; must match the selected model/output. | `1024` |
| `GENERATION_MODEL` | Yes | Cohere chat model identifier. | `command-r-plus` |
| `RERANKING_MODEL` | Yes | Cohere reranking model identifier. | `rerank-v4.0-pro` |
| `DEFAULT_INPUT_MAX_CHARACTERS` | Yes | Maximum prompt characters sent by the provider wrapper. | `1000` |
| `DEFAULT_GENERATION_MAX_OUTPUT_TOKENS` | Yes | Default maximum generated tokens. | `1000` |
| `DEFAULT_GENERATION_TEMPERATURE` | Yes | Chat generation temperature. | `0.1` |
| `FILE_ALLOWED_TYPES` | Yes | JSON-style list of accepted upload MIME types. | `[...]` |
| `FILE_ALLOWED_SIZE` | Yes | File-size setting used by the upload validator. | `100` |
| `FILE_DEFAULT_CHUNK_SIZE` | No | Upload read/write chunk size in bytes. | `512000` |

The exact supported model names and account availability are controlled by Cohere. Choose an embedding model whose output dimension matches the database vector dimension and the `EMBEDDING_MODEL_SIZE` value.

## Run locally

The following is the simplest development path when PostgreSQL/pgvector is already available.

### 1. Install dependencies

```bash
uv sync --group dev
```

### 2. Configure the environment

```bash
cp .env.example .env
# Edit .env and add database, Cohere, embedding, chat, and reranking settings.
```

### 3. Start PostgreSQL with pgvector

For a quick database-only setup:

```bash
docker run --name shopping-assistant-pgvector \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=shopping_assistant \
  -p 5432:5432 \
  -d pgvector/pgvector:0.8.6-pg18-trixie
```

Set the matching credentials in `.env`.

### 4. Run migrations

The migration environment is under the database scheme directory and uses an Alembic configuration file:

```bash
cp docker/shopping_assistant/alembic.example.ini \
  src/models/db_schemes/shopping_assistant/alembic.ini
```

Update `sqlalchemy.url` in that file, then run:

```bash
cd src/models/db_schemes/shopping_assistant
uv run alembic upgrade head
cd ../../../..
```

### 5. Start the API

```bash
uv run uvicorn --app-dir src main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at:

- Root: <http://localhost:8000/api/v1/>
- OpenAPI UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Prometheus metrics: <http://localhost:8000/metrics>

## Run with Docker Compose

Docker Compose defines these services:

| Service | Purpose | Default port |
| --- | --- | ---: |
| `fastapi` | Shopping Assistant API | `8000` |
| `nginx` | Reverse proxy in front of FastAPI | `80` |
| `pgvector` | PostgreSQL with pgvector | `5432` |
| `postgres-exporter` | PostgreSQL metrics exporter | `9187` |
| `prometheus` | Metrics collection | `9090` |
| `grafana` | Metrics dashboards | `3000` |
| `node-exporter` | Host metrics | `9100` |

The checked-in Compose file expects deployment-specific environment files under `docker/env/`:

- `docker/env/.env.app`
- `docker/env/.env.postgres`
- `docker/env/.env.postgres-exporter`
- `docker/env/.env.grafana`

These files are intentionally not committed because they contain credentials and deployment settings. Create them before starting Compose, using the variables referenced by `docker/docker-compose.yml` and the application settings above.

Then start the stack:

```bash
mkdir -p docker/env
cp .env.example docker/env/.env.app
# Edit docker/env/.env.app. Set POSTGRES_HOST=pgvector and add real Cohere settings.
# Create the PostgreSQL, exporter, and Grafana env files with your deployment credentials.

docker compose -f docker/docker-compose.yml up --build -d
```

The application image runs `alembic upgrade head` automatically before starting Uvicorn.

Useful commands:

```bash
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs -f fastapi
docker compose -f docker/docker-compose.yml logs -f pgvector
docker compose -f docker/docker-compose.yml down
```

To remove containers and persistent volumes as well:

```bash
docker compose -f docker/docker-compose.yml down -v --remove-orphans
```

> **Warning:** `down -v` deletes the PostgreSQL, uploaded-asset, Prometheus, and Grafana volumes. Use it only when data loss is acceptable.

## Database and migrations

Migrations are stored at:

```text
src/models/db_schemes/shopping_assistant/alembic/versions/
```

The current migration chain creates and evolves:

- Categories, uploaded assets, and products.
- Nullable product metadata fields.
- Profile and memory tables.
- Conversation and LangGraph-related application state support.
- A generated PostgreSQL `search_vector` column and GIN index for keyword search.

The Docker entrypoint applies migrations before starting the API. For local execution, run Alembic manually with a configured `alembic.ini`.

## Using the API

All application routes are under `/api/v1`.

### Health-style welcome endpoint

```bash
curl http://localhost:8000/api/v1/
```

Example response:

```json
{
  "app name": "shopping_assistant",
  "app version": "0.1.0"
}
```

### Create a conversation

```bash
curl -X POST http://localhost:8000/api/v1/conversations \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "alice",
    "title": "Phone shopping"
  }'
```

The response contains a public `conversation_id` UUID. The username is currently an application-level identity; authentication is not implemented.

### Send a chat message

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "alice",
    "conversation_id": "00000000-0000-0000-0000-000000000000",
    "message": "Find me a phone with a good camera under $600"
  }'
```

The `conversation_id` must belong to the supplied username. The agent can use the catalog and memory tools before returning a response.

### Upload a catalog file

The upload field name is `file`:

```bash
curl -X POST \
  http://localhost:8000/api/v1/data/upload/electronics_cellphones \
  -F 'file=@./catalog.csv;type=text/csv'
```

The response returns an asset name. Use that asset name in the validation and storage steps.

### Validate an uploaded file

```bash
curl -X POST \
  http://localhost:8000/api/v1/data/validate/<asset_name>
```

Validation checks each row against the product input schema and reports invalid rows. Valid rows are written back to the cleaned source file.

### Store validated products

```bash
curl -X POST \
  http://localhost:8000/api/v1/data/store/<asset_name> \
  -H 'Content-Type: application/json' \
  -d '{"batch_size": 100}'
```

### Generate and index embeddings

```bash
curl -X POST \
  http://localhost:8000/api/v1/data/embed/electronics_cellphones
```

The endpoint loads up to 1,300 products for the category, embeds each product’s title and description, creates the category vector table if needed, and inserts the vectors keyed by `product_id`.

### Direct hybrid retrieval

```bash
curl -X POST \
  'http://localhost:8000/api/v1/data/retrieve/electronics_cellphones?query=wireless%20noise%20cancelling%20headphones'
```

This endpoint runs hybrid search and Cohere reranking, then returns product rows as JSON. Floating-point `NaN` values are converted to JSON `null` because literal `NaN` is not valid standard JSON.

### Prometheus metrics

```bash
curl http://localhost:8000/metrics
```

The middleware records request count and request latency labeled by HTTP method, route path, and status code.

## Catalog ingestion workflow

### Expected product fields

Each input row is validated against the following shape:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `parent_asin` | string | Yes | Source/catalog identifier. |
| `title` | string | Yes | Product title. |
| `description` | string | Yes | Product description. |
| `filename` | string | Yes | Required by the current validation model. |
| `store` | string | No | Seller or store name. |
| `average_rating` | float | No | Defaults to `0.0` in the input model. |
| `rating_number` | integer | No | Defaults to `0` in the input model. |
| `price` | float | No | Defaults to `0.0` in the input model. |
| `image` | string | No | Image URL or source value. |

The storage route maps validated rows into the SQLAlchemy `Product` entity and associates them with the uploaded asset and category.

### File formats

The preprocessing controller selects a loader by extension:

- `.csv` through pandas CSV loading.
- `.xlsx`/`.xls` through pandas Excel loading.
- `.json` through pandas JSON loading.
- `.parquet` through pandas Parquet loading.
- Arrow IPC files through PyArrow.

The upload MIME type must also appear in `FILE_ALLOWED_TYPES`.

## Retrieval pipeline

The `RetrievalController.hybrid_search()` method performs the following steps:

1. Embed the query with Cohere using the `search_query` input type.
2. Search the category’s pgvector table.
3. Run PostgreSQL keyword search using `plainto_tsquery('english', ...)`.
4. Sort both result sets by score.
5. Fuse product IDs with Reciprocal Rank Fusion using `k=60`.
6. Load complete product rows from PostgreSQL.
7. Send the fused products to Cohere Rerank.
8. Return the reranked SQLAlchemy product objects.

The LangGraph `search_catalog` tool uses this same hybrid retrieval path. Explicit numeric constraints such as minimum price, maximum price, and minimum rating are handled by the separate `filter_products` tool.

## Conversation and memory workflow

A conversation is created with a username and optional title. The database stores:

- A public conversation UUID used by API clients.
- A private LangGraph thread ID used for checkpoint lookup.
- The owning profile ID.

On the first message in a thread, the agent is instructed to read existing memories before answering. For each message, the agent may:

- Read the user’s existing facts.
- Add a new preference, constraint, or history fact.
- Modify an existing fact by its exact `fact_id`.

Memory writes are intentionally controlled by the agent prompt and tool validation. The current implementation does not provide a separate authentication layer, tenant isolation layer, or user-facing memory management API.

## Embedding rate-limit protection

Cohere’s current Embed API limits are reflected in `LangChainCohereProvider`:

- Maximum **96 text inputs per request**.
- Maximum **2,000 inputs per minute**.
- `TooManyRequestsError` retries up to three times.
- `Retry-After` is honored when supplied by Cohere.
- Otherwise, the provider waits for the 60-second Cohere rate window.
- The provider preserves `search_document` and `search_query` input types.

This protection applies to the application’s embedding wrapper. It does not replace account-level Cohere quotas or eliminate the need to use an appropriate production API key for production traffic.

## Observability

The Compose stack includes Prometheus and Grafana. FastAPI exposes `/metrics`, and Prometheus is configured to scrape:

- FastAPI.
- Node Exporter.
- Prometheus itself.
- PostgreSQL Exporter.

The Nginx proxy forwards both application traffic and `/metrics` to FastAPI.

## Testing and CI

Run the test suite locally:

```bash
uv run --group dev pytest -q
```

Run the checks used by the GitHub Actions workflow:

```bash
uv run ruff check src tests
uv run black --check src tests
uv run pytest
```

The test suite covers:

- Hybrid retrieval with fake vector and keyword providers.
- Reciprocal Rank Fusion uniqueness and ordering.
- Memory conflict updates without duplicate facts.
- Chat request validation.
- Cohere reranking and product-document conversion.
- Cohere embedding batch size and rate-limit retry behavior.

The workflow in `.github/workflows/CI.yml` runs on pushes and pull requests targeting `main`.

## Important implementation notes

- **Credentials:** Never commit `.env`, Cohere keys, database passwords, or deployment-specific Docker env files.
- **Identity:** `username` is currently the identity boundary. Authentication and authorization are not implemented.
- **Vector dimensions:** The PostgreSQL vector column dimension is derived from `EMBEDDING_MODEL_SIZE`; changing embedding dimensions requires compatible tables and re-indexing.
- **Category tables:** Embeddings are stored in category-specific tables named `table_<dimension>_<category>`.
- **Re-indexing:** If product title or description changes, re-run the embedding/indexing workflow for the affected category.
- **Reranking fallback:** If no reranking client is available, the retrieval controller preserves the fused order.
- **JSON responses:** Direct retrieval converts SQLAlchemy column values to JSON-safe values and maps floating-point `NaN` to `null`.
- **Upload storage:** Uploaded files are stored under `src/assets/files/<category>/` in local execution and under the mounted `fastapi_data` volume in Docker.
- **Deployment files:** `docker/docker-compose.yml` expects environment files under `docker/env/`; those files are deployment secrets and are not committed.
- **Current Docker documentation:** The Compose file is the source of truth for service names, images, ports, and mounted volumes. Verify environment-file paths before starting a new deployment.

## Roadmap

The following items are natural next steps for production hardening:

- Add authentication and authorization instead of username-only identity.
- Add conversation listing, retrieval, and deletion endpoints.
- Add an explicit product comparison tool.
- Add paginated catalog ingestion and a background job for large datasets.
- Add durable ingestion status and retry reporting.
- Add retrieval evaluation datasets and ranking-quality metrics.
- Add Cohere reranking rate limiting and batching if candidate sets grow beyond the current small retrieval window.
- Add typed response models for all data endpoints.
- Add database health/readiness endpoints and safer startup failure reporting.
- Add complete Docker env templates and automated container smoke tests.
- Resolve remaining formatting and dependency alignment issues in CI configuration.

## License

This project is distributed under the terms of the [MIT License](LICENSE).
