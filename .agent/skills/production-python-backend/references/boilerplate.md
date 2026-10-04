# Boilerplate — scaffolding a production-shaped service

Use this when starting a new project, module, or adding a new model/controller/router. It encodes the
layout and the entry-point/config/base-class wiring, **plus** production patterns a bare tutorial
skips (health check, dependency injection, config-driven server, `.gitignore`, Dockerfile, testing
seams). Copy the structure; adapt names to the domain.

Stack: FastAPI · Motor (async MongoDB) · Pydantic v2 · `uv`. Adapt the mechanism, keep the shape, for
other stacks.

## Table of contents

1. Project layout
2. Dependency & environment setup (`uv`)
3. The entry point (`main.py`)
4. Config (`helpers/config.py`)
5. Base classes
6. A model (schema + data-access + factory + idempotent init)
7. A router (with DI, versioning, status codes)
8. `.gitignore` and `.env.example`
9. Dockerfile & compose (running the DB)
10. Health check & readiness
11. Testing seams

---

## 1. Project layout

```
service-name/
├── src/
│   ├── main.py                     # entry point: app + lifespan + router registration
│   ├── helpers/
│   │   ├── __init__.py
│   │   └── config.py               # typed Settings from .env
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── health.py               # liveness/readiness — always have this
│   │   ├── <domain>.py             # one router per concern, versioned prefix
│   │   └── schemas/
│   │       ├── __init__.py
│   │       └── <domain>.py         # request/response Pydantic models (API contract)
│   ├── controllers/
│   │   ├── __init__.py
│   │   ├── BaseController.py        # shared config + paths + helpers
│   │   └── <Domain>Controller.py    # business logic; NO fastapi import
│   ├── models/
│   │   ├── __init__.py
│   │   ├── BaseDataModel.py         # shared db client + settings
│   │   ├── <Domain>Model.py         # the ONLY place with DB queries
│   │   ├── db_schemas/
│   │   │   ├── __init__.py
│   │   │   └── <domain>.py          # DB-shape Pydantic models (+ get_indexes)
│   │   └── enums/
│   │       ├── __init__.py
│   │       ├── ResponseEnum.py
│   │       ├── ProcessingEnum.py
│   │       └── DatabaseEnum.py
│   ├── assets/                      # runtime files (gitignored contents)
│   │   └── .gitignore
│   ├── .env.example                 # committed template
│   ├── .env                         # NEVER committed
│   ├── .gitignore
│   ├── .python-version
│   ├── pyproject.toml
│   └── uv.lock                      # committed (this is an app, not a library)
├── docker/
│   ├── docker-compose.yml
│   ├── .env.example
│   └── .gitignore                   # ignore DB data volumes
├── tests/
├── README.md
└── LICENSE
```

Two folders that are easy to skip but shouldn't be: **`routers/schemas/`** keeps the *API contract*
(what clients send/receive) separate from **`models/db_schemas/`** (how data is stored) — they change
for different reasons and shouldn't be one type. And a **`health.py` router from the start**, because
every deployment target (load balancer, orchestrator, uptime monitor) expects one.

Distinguish **application code** (everything under `src/`) from **infrastructure** (root-level
`docker/`, `README`, `LICENSE`, `pyproject.toml`) — things that support the project but aren't part of
the running app.

---

## 2. Dependency & environment setup (`uv`)

```bash
uv init
uv add fastapi "uvicorn[standard]" motor pydantic pydantic-settings \
       python-multipart aiofiles
uv add --dev pytest pytest-asyncio httpx ruff
```

- **`pyproject.toml`** is the one place for metadata + deps (PEP 621), not a flat `requirements.txt`.
- **Commit `uv.lock`.** For an *application*, the lockfile pins every transitive dependency to an exact
  version so the environment is byte-reproducible ("worked last week" bugs come from unlocked
  transitive deps). For a *library*, don't commit it — libraries stay flexible.
- **Commit `.python-version`.** Language versions change behavior; pin the interpreter too.
- **Fill in `pyproject.toml` metadata** — a real `description`, not the `uv init` placeholder. It's
  portfolio-facing.

---

## 3. The entry point (`main.py`)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from helpers.config import get_settings
from routers.health import health_router
from routers.admin import admin_router   # add one import per router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup: create expensive shared resources ONCE ---
    settings = get_settings()
    app.state.db_client = AsyncIOMotorClient(settings.MONGODB_URL)   # the connection/client
    app.state.db = app.state.db_client[settings.MONGODB_DATABASE]    # the database handle
    yield
    # --- shutdown: guaranteed cleanup even if startup partially failed ---
    app.state.db_client.close()   # only the client has .close()

settings = get_settings()
app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

app.include_router(health_router)
app.include_router(admin_router)
```

Notes that matter: `lifespan` (not the deprecated `@app.on_event`); the deliberate **client vs db**
split with comments (confusing them is a classic Motor bug); `title`/`version` from settings so `/docs`
reflects config; explicit `include_router` per router (gives you control over order and lets you
conditionally include, e.g. admin routes only outside prod).

Run it config-driven, not with hardcoded host/port:

```python
# run.py (or a __main__ block) — dev entry
import uvicorn
from helpers.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("main:app", host=s.APP_HOST, port=s.APP_PORT, reload=s.DEBUG)
```

`--reload` is dev-only. In production run under a process manager with multiple workers.

---

## 4. Config (`helpers/config.py`)

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Service"
    APP_VERSION: str = "0.1.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = False

    MONGODB_URL: str          # no default → must be set
    MONGODB_DATABASE: str

    FILE_ALLOWED_TYPES: list[str] = ["application/pdf", "text/plain"]
    FILE_MAX_SIZE: int = 10_485_760          # 10 MB
    FILE_DEFAULT_CHUNK_SIZE: int = 5_242_880 # 5 MB read slab

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`@lru_cache` makes `get_settings()` a singleton — `.env` is read once, everyone shares one object. It's
also the injectable seam for tests (`get_settings.cache_clear()` + a test `.env`, or override the
dependency).

---

## 5. Base classes

```python
# controllers/BaseController.py
import os, random, string
from helpers.config import get_settings, Settings

class BaseController:
    def __init__(self, config: Settings | None = None):
        # DO NOT write `config: Settings = get_settings()` — a default arg is evaluated ONCE at
        # import time, silently sharing one object across all instances (mutable-default trap).
        self.settings = config or get_settings()
        self.base_dir  = os.path.dirname(os.path.dirname(__file__))       # .../src
        self.files_dir = os.path.join(self.base_dir, "assets", "files")   # os.path.join, not + "/"

    @staticmethod
    def generate_random_string(length: int = 12) -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))

    @staticmethod
    def get_file_extension(filename: str) -> str:
        return os.path.splitext(filename)[-1].lower()
```

```python
# models/BaseDataModel.py
from motor.motor_asyncio import AsyncIOMotorDatabase
from helpers.config import get_settings

class BaseDataModel:
    def __init__(self, db_client: AsyncIOMotorDatabase):
        self.db_client = db_client          # a real type hint, not `object`
        self.settings = get_settings()
```

Utilities that never touch `self` are `@staticmethod` (signal: "no instance state"). Type the db
parameter concretely (`AsyncIOMotorDatabase`) — `object` documents nothing and kills autocomplete.

---

## 6. A model (schema + data-access + factory + idempotent init)

```python
# models/db_schemas/data_chunk.py
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId

class DataChunk(BaseModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    chunk_text: str  = Field(..., min_length=1)
    chunk_order: int = Field(..., ge=0)
    chunk_metadata: dict
    chunk_project_id: str

    model_config = {"arbitrary_types_allowed": True, "json_encoders": {ObjectId: str}}

    @classmethod
    def get_indexes(cls):
        return [{"key": [("chunk_project_id", 1)], "name": "chunk_project_id_index_1", "unique": False}]
```

```python
# models/ChunkModel.py
from pymongo import InsertOne
from models.BaseDataModel import BaseDataModel
from models.db_schemas.data_chunk import DataChunk
from models.enums.DatabaseEnum import DatabaseEnum

class ChunkModel(BaseDataModel):
    def __init__(self, db_client):
        super().__init__(db_client)
        self.collection = self.db_client[DatabaseEnum.COLLECTION_CHUNK_NAME.value]

    @classmethod
    async def create_instance(cls, db_client):        # async factory: __init__ can't be async
        instance = cls(db_client)
        await instance.init_collection()
        return instance

    async def init_collection(self):                  # idempotent: safe every startup
        names = await self.db_client.list_collection_names()
        if DatabaseEnum.COLLECTION_CHUNK_NAME.value not in names:
            await self.db_client.create_collection(DatabaseEnum.COLLECTION_CHUNK_NAME.value)
            for idx in DataChunk.get_indexes():
                await self.collection.create_index(idx["key"], name=idx["name"], unique=idx["unique"])

    async def insert_many_chunks(self, chunks: list[DataChunk], batch_size: int = 100) -> int:
        for i in range(0, len(chunks), batch_size):
            ops = [InsertOne(c.model_dump(by_alias=True, exclude_none=True)) for c in chunks[i:i+batch_size]]
            await self.collection.bulk_write(ops)
        return len(chunks)

    async def delete_chunks_by_project_id(self, project_id: str) -> int:
        res = await self.collection.delete_many({"chunk_project_id": project_id})
        return res.deleted_count
```

Every piece here is load-bearing: the alias + `by_alias` dump, the schema-owned index, the async
factory, the idempotent init, the batched bulk write, the DB queries confined to this layer.

---

## 7. A router (with DI, versioning, status codes)

```python
# routers/admin.py
import logging
from fastapi import APIRouter, Request, UploadFile, status
from fastapi.responses import JSONResponse

from controllers.DataController import DataController
from models.ChunkModel import ChunkModel
from models.enums.ResponseEnum import ResponseSignal
from routers.schemas.data import ProcessRequest

logger = logging.getLogger("uvicorn.error")
admin_router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

@admin_router.post("/ingest/{project_id}")
async def ingest(project_id: str, file: UploadFile, request: Request):
    controller = DataController()
    ok, signal = controller.validate_file(file)        # validate at the boundary, before work
    if not ok:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"signal": signal})

    try:
        file_id = await controller.save_file(file, project_id)   # streams via aiofiles
    except OSError as e:                                          # specific, not bare Exception
        logger.error(f"Failed to save upload for project {project_id}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": ResponseSignal.FILE_UPLOAD_FAILED.value},
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"signal": ResponseSignal.FILE_UPLOAD_SUCCESS.value, "file_id": file_id},
    )

@admin_router.post("/process/{project_id}")
async def process(project_id: str, req: ProcessRequest, request: Request):
    chunk_model = await ChunkModel.create_instance(db_client=request.app.state.db)
    if req.do_reset:
        await chunk_model.delete_chunks_by_project_id(project_id)
    # ... produce chunks ...
    chunks = []  # placeholder
    if not chunks:                                      # check for empty, not just errors
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST,
                            content={"signal": ResponseSignal.PROCESSING_FAILED.value,
                                     "error": "no chunks produced"})
    inserted = await chunk_model.insert_many_chunks(chunks)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content={"signal": ResponseSignal.PROCESSING_SUCCESS.value, "count": inserted})
```

```python
# routers/schemas/data.py
from typing import Optional
from pydantic import BaseModel

class ProcessRequest(BaseModel):
    file_id: str
    chunk_size: Optional[int] = 512      # tunable knobs exposed with defaults
    overlap: Optional[int] = 50
    do_reset: Optional[bool] = False     # destructive option, opt-in
```

**Better DI evolution** — replace `request.app.state.db` access with a dependency so it's explicit and
test-overridable:

```python
from fastapi import Depends

def get_db(request: Request):
    return request.app.state.db

@admin_router.post("/process/{project_id}")
async def process(project_id: str, req: ProcessRequest, db=Depends(get_db)):
    chunk_model = await ChunkModel.create_instance(db_client=db)
    ...
```

---

## 8. `.gitignore` and `.env.example`

`.gitignore` (at least):

```gitignore
.env
__pycache__/
*.pyc
.venv/
assets/files/*
!assets/files/.gitkeep
```

`docker/.gitignore`:

```gitignore
mongodb/          # DB data volume — never commit database files
```

`.env.example` (committed, placeholders only):

```bash
APP_NAME="Service"
APP_VERSION="0.1.0"
DEBUG=False
MONGODB_URL="mongodb://user:pass@localhost:27017/db?authSource=admin"
MONGODB_DATABASE="service_db"
FILE_ALLOWED_TYPES=["application/pdf","text/plain"]
FILE_MAX_SIZE=10485760
FILE_DEFAULT_CHUNK_SIZE=5242880
```

Two mistakes to pre-empt, both from real code: `.gitignore` only affects *untracked* files — if `.env`
or a DB volume was ever committed, adding it to `.gitignore` does nothing; you must
`git rm --cached <path>` too. And note `authSource=admin` in the Mongo URL — without it the driver
authenticates against the target DB where the user doesn't exist, and fails with a *misleading*
"bad credentials" error.

---

## 9. Dockerfile & compose (running the DB)

```dockerfile
# Dockerfile
FROM python:3.13-slim
WORKDIR /app
# copy deps first so the install layer caches across code changes
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY . .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The dependency-copy-before-code ordering is the one Docker optimization worth memorizing: Docker caches
layers, so if code changes but deps don't, the (slow) install layer is reused.

```yaml
# docker/docker-compose.yml
services:
  mongodb:
    image: mongo:7.0            # pin the version
    restart: always
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASS}
    ports: ["27017:27017"]
    volumes: ["mongodb_data:/data/db"]   # volume → data survives restarts (don't commit it)

volumes:
  mongodb_data:
```

The volume is what makes data outlive the container (containers are ephemeral). `MONGO_INITDB_*` is read
**only on first init of a fresh volume** — changing it later does nothing unless you drop the volume.

---

## 10. Health check & readiness

Always ship this from day one — deployment infrastructure depends on it.

```python
# routers/health.py
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

health_router = APIRouter(prefix="/api/v1", tags=["Health"])

@health_router.get("/health")            # liveness: is the process up?
async def health():
    return {"status": "ok"}

@health_router.get("/ready")             # readiness: are dependencies reachable?
async def ready(request: Request):
    try:
        await request.app.state.db_client.admin.command("ping")
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            content={"status": "not_ready"})
```

Liveness and readiness are different questions: liveness = "restart me if this fails"; readiness =
"don't send me traffic yet." Orchestrators use them differently.

---

## 11. Testing seams

The patterns above exist partly to make testing possible without a running server or real DB:

- **Controllers have no `fastapi` import** → test business logic by calling methods directly.
- **`Depends()` dependencies** → override in tests via `app.dependency_overrides[get_db] = fake_db`.
- **`get_settings()` is cached and injectable** → point tests at a test `.env` or override it.

```python
# tests/test_ingest.py
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.mark.asyncio
async def test_ingest_rejects_bad_type():
    app.dependency_overrides[get_db] = lambda: FakeDB()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/admin/ingest/p1",
                              files={"file": ("x.exe", b"...", "application/x-msdownload")})
    assert r.status_code == 400
    app.dependency_overrides.clear()
```

If code is hard to test, that's usually a layering smell — logic entangled with HTTP or the DB.
Testability and clean layering are the same property seen from two angles.
