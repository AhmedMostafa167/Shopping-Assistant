FROM python:3.14-slim-bookworm AS builder
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.14-slim-bookworm AS final
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/

ENV PATH="/app/.venv/bin:$PATH"

RUN mkdir -p /models/db_schemes/shopping_assistant
COPY docker/shopping_assistant/alembic.ini models/db_schemes/shopping_assistant/alembic.ini

COPY docker/shopping_assistant/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
