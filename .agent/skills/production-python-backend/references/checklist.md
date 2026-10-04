# The Checklist — habit-by-habit rules

Every rule here maps to one of the five principles in SKILL.md. Format: the rule, the reason it
matters (the failure it prevents), and vetted code. Use the code — don't reconstruct from memory.

## Table of contents

1. Configuration & secrets
2. Constants & naming
3. Layering & structure
4. Input handling & safety
5. Async & I/O
6. Data modeling (Pydantic + Mongo)
7. Reliability patterns
8. API design
9. Observability

---

## 1. Configuration & secrets

**Use typed settings loaded from `.env`. Never hardcode a limit, URL, secret, or path.**

Env vars are always strings — `.env` has no notion of int or list. Typed settings convert and
**validate once at startup**; a bad value stops the app at boot naming the field, instead of a
`TypeError` deep in a request weeks later. A field with no default that's missing from `.env` means
the app refuses to start — which is correct for critical values like a DB URL.

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str
    APP_VERSION: str
    FILE_ALLOWED_TYPES: list[str]
    FILE_MAX_SIZE: int
    FILE_DEFAULT_CHUNK_SIZE: int
    MONGODB_URL: str          # no default → app won't start if unset (intended)
    MONGODB_DATABASE: str
    model_config = SettingsConfigDict(env_file=".env")

from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- **Give a default only when there's a genuinely safe fallback.** Secrets and DB URLs should have none.
- **The test for "does this belong in config?":** *"If I changed this value, would I want to change
  code and redeploy?"* If no → config.
- **Don't over-apply it.** `chunk_order = i + 1` is not a magic number — it expresses the logic. The
  smell is a value that's arbitrary, repeated, or environment-dependent.

**Commit `.env.example`, never `.env`.** The example is the one committed declaration of *which*
variables exist (with placeholder values); the real `.env` holds secrets and stays untracked. Update
`.env.example` in the same commit that adds a setting, so the requirement shows up in the diff.

---

## 2. Constants & naming

**Any value from a fixed, known set becomes an enum member — never a raw string typed inline.**

A magic-string typo (`".pfd"`) is a valid string that silently never matches; the bug is a
mysterious empty result, not an error. An enum typo (`ProcessingEnum.PFD`) is an `AttributeError` at
import. You convert a class of silent runtime bugs into loud import-time ones for free. Also: one
source of truth (rename in one place), autocomplete-discoverable, self-documenting.

```python
from enum import Enum

class ProcessingEnum(str, Enum):      # extensions
    TXT = ".txt"
    PDF = ".pdf"
    MD  = ".md"

class DatabaseEnum(str, Enum):        # collection names
    COLLECTION_PROJECT_NAME = "projects"
    COLLECTION_CHUNK_NAME   = "chunks"

class ResponseSignal(str, Enum):      # API outcome codes
    FILE_UPLOAD_SUCCESS   = "file_upload_success"
    FILE_TYPE_NOT_ALLOWED = "file_type_not_allowed"
    FILE_SIZE_EXCEEDED    = "file_size_exceeded"
```

- **Inherit `(str, Enum)`** whenever the value crosses a JSON or DB boundary. A plain `Enum` member
  is not JSON-serializable and won't `==` a raw string, forcing `.value` everywhere and breaking the
  moment you forget it. `(str, Enum)` makes the member *be* a string. (Use `(int, Enum)` for numeric
  sets.) **Consistency matters:** don't mix plain and `str` enums in one codebase.
- **Enum-worthy = fixed set + referenced more than once + the name adds meaning.** A one-off string
  used once does not qualify.
- **Group by domain** (extensions, collection names, signals) rather than one giant `Constants` class
  that becomes a junk drawer.

**Name for the reader, not the writer.** `chunk_project_id`, `chunk_order`, `chunk_metadata` — not
`pid`, `ord`, `meta`. A name is written once and read hundreds of times; the entity prefix
disambiguates when two models share a scope. Names are documentation that can't rot.

---

## 3. Layering & structure

**Routes → controllers → models → DB. Each layer does one job; dependencies point downward only.**

- **Routers**: parse the request, call a controller/model, shape the HTTP response. Nothing else.
- **Controllers**: business logic. **Must not import `fastapi`** or return `JSONResponse` — that's
  what makes them reusable from a CLI, a worker, or a test with no server running.
- **Models**: the *only* place that issues DB queries. This is what makes the DB swappable.

Verify continuously: `grep fastapi` in controllers → empty; DB calls in routers → empty. The moment a
route opens a connection and runs a query, the payoff (testability, swappability) is gone.

**Put shared construction in a base class.** Config, base paths, and shared helpers defined once;
subclasses inherit via `super().__init__()`. Without it, each controller repeats the same setup lines
and the one you forget to update becomes a bug. Base classes are for what *every* subclass needs — the
moment a method serves only one subclass, it belongs in that subclass.

**Use `__init__.py` as a curated public interface.** It makes the folder an importable package *and*
whatever you import into it becomes the package's public surface, so callers write
`from models.enums import ResponseSignal` without encoding the internal filename into every call site.

---

## 4. Input handling & safety

**Validate at the boundary, before doing any work.** Check type and size *before* writing bytes to
disk — validating after means you spent the I/O and briefly stored untrusted content for input you're
about to reject.

```python
def validate_file(self, file: UploadFile) -> tuple[bool, str]:
    if file.content_type not in self.settings.FILE_ALLOWED_TYPES:
        return False, ResponseSignal.FILE_TYPE_NOT_ALLOWED.value
    if file.size and file.size > self.settings.FILE_MAX_SIZE:
        return False, ResponseSignal.FILE_SIZE_EXCEEDED.value
    return True, ResponseSignal.FILE_UPLOAD_SUCCESS.value
```

Return `(bool, signal)` for *expected* failures (users upload wrong files constantly) so the route can
map them to a clean 400. Reserve exceptions for genuinely unexpected conditions (disk full).

**Sanitize user-controlled strings with an allowlist.** A filename is attacker-controlled input used
to build a path, not a label. A blocklist must enumerate everything dangerous (`..`, `/`, `\`, null
bytes, unicode tricks) — you'll miss one and the attacker needs one. An allowlist enumerates what's
*safe* and rejects everything else by default.

```python
import re
cleaned = re.sub(r'[^\w.-]', '_', original_filename.strip())
```

**Guarantee uniqueness with defense in depth.** A random prefix makes collision improbable; a
`while os.path.exists()` loop makes it impossible (and covers leftover files randomness can't). Keep a
cleaned original name alongside the random key so files stay human-identifiable.

```python
new_path = os.path.join(project_path, f"{random_key}_{cleaned}")
while os.path.exists(new_path):
    random_key = self.generate_random_string()
    new_path = os.path.join(project_path, f"{random_key}_{cleaned}")
```

**Namespace user data by tenant from day one.** `assets/files/{project_id}/` makes "delete everything
for project N" a directory op and mirrors the DB's `*_project_id` scoping. Retrofitting multi-tenancy
later is a migration; building it in costs one path segment.

**Build paths platform-independently, anchored to `__file__`.** Use `os.path.join`, never `+ "/"`
(separators differ by OS; concatenation doubles them). Anchor to `__file__`, never `os.getcwd()` —
cwd depends on where the process was launched and silently breaks every derived path.

```python
self.base_dir  = os.path.dirname(os.path.dirname(__file__))   # .../src
self.files_dir = os.path.join(self.base_dir, "assets", "files")
```

---

## 5. Async & I/O

**Async all the way down.** Async concurrency works because functions yield at `await`; one blocking
call anywhere holds the single event loop and stalls every concurrent request. A blocking call
produces no error — it silently turns a concurrent server sequential, visible only as latency under
load. So inside any `async def`: **Motor** not PyMongo, **`aiofiles`** not `open`, **`httpx.AsyncClient`**
not `requests`. For an unavoidable blocking call: `await loop.run_in_executor(None, blocking_fn)`.

**Stream unbounded input; never load it whole into memory.** Read/write in fixed slabs so a 200 MB
upload never exists as one object, and use `aiofiles` so the write doesn't block the loop.

```python
async with aiofiles.open(file_path, 'wb') as f:
    while chunk := await file.read(settings.FILE_DEFAULT_CHUNK_SIZE):
        await f.write(chunk)
```

Reflex question at any I/O call: *"how big can this get?"* and *"does this yield?"*

**Manage expensive connections with lifespan, not per request.** Opening a DB connection means a
handshake + auth (tens of ms) and consumes the connection limit; per-request opening adds latency to
every call and exhausts the pool under load. Open once at startup, store on `app.state`, close on
shutdown — the context manager guarantees the close even if startup partially failed.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.db_client = AsyncIOMotorClient(settings.MONGODB_URL)   # the connection
    app.state.db = app.state.db_client[settings.MONGODB_DATABASE]    # the database handle
    yield
    app.state.db_client.close()   # only the client has .close()
```

Keep **client** (has `.close()`) and **db** (the handle you query) distinct — confusing them is a
classic Motor bug. Reach shared state via `request.app.state.db`, not a module-level global (a global
executes at import, before the loop exists, and can bind to the wrong loop). The cleaner evolution is
a `Depends(get_db)` dependency, which also makes it overridable in tests.

---

## 6. Data modeling (Pydantic + Mongo)

**Put real constraints on schema fields so invalid objects can't be constructed.** A validation
function protects one call site; a schema constraint protects every construction forever. The object's
existence becomes proof of validity, deleting defensive `if not x:` checks downstream.

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from bson import ObjectId

class DataChunk(BaseModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    chunk_text: str  = Field(..., min_length=1)   # empty chunk = wasted embedding + a "match" with no info
    chunk_order: int = Field(..., ge=0)
    chunk_metadata: dict
    chunk_project_id: str

    model_config = {"arbitrary_types_allowed": True, "json_encoders": {ObjectId: str}}
```

- **`Field(...)` (Ellipsis) = required, no default.** Omitting it silently makes the field optional.
- **`description=` doubles as OpenAPI docs** — documentation that can't drift because it *is* the code.
- **Use `@field_validator` for semantic rules types can't express** (e.g. `project_id` must be
  alphanumeric — and note it becomes a directory name, so this validator is also a security control).
  Raise `ValueError`; FastAPI turns it into a clean 422.

**Bridge `_id` ↔ `id` and always dump with `by_alias`.** Mongo's key is `_id`; Pydantic won't treat a
field named `_id` normally, so alias it to `id`. On insert, dump with `by_alias=True` (writes `_id`) and
`exclude_none=True`/`exclude_unset=True` (drops `id=None` so Mongo generates the ObjectId).

```python
await collection.insert_one(model.model_dump(by_alias=True, exclude_none=True))
```

Forgetting `by_alias` writes a literal `"id": null` field *and* lets Mongo generate a separate `_id` —
two identity fields, queries by `id` silently return nothing. Fails silently; get it right consistently.

**Let the schema own its indexes** via a classmethod, so the index requirement lives next to the field.
Adding an indexed field is then a one-line change in one file, and init just asks the schema.

```python
@classmethod
def get_indexes(cls):
    return [{"key": [("chunk_project_id", 1)], "name": "chunk_project_id_index_1", "unique": False}]
```

Use `[(field, direction)]` **tuples** (pymongo's expected format), and **name indexes explicitly** so
they're a stable handle for `dropIndex` / `getIndexes` rather than an auto-generated name that changes
when the definition changes.

**Choose embed vs reference deliberately.** Embed when children are always read with the parent,
bounded, one-to-few. Reference (own collection + `*_id` key) when children grow unbounded, are queried
alone, or would risk Mongo's 16 MB document limit. Chunks are referenced.

---

## 7. Reliability patterns

**Use an async classmethod factory when object setup needs I/O.** `__init__` can't be `async`, so an
object that needs `await` during setup should expose `create_instance`, returning a fully-initialized
object — never a half-constructed one that requires a forgotten second call.

```python
@classmethod
async def create_instance(cls, db_client):
    instance = cls(db_client=db_client)
    await instance.init_collection()
    return instance
```

Use `cls(...)`, not the class name, so a subclass constructs itself.

**Make initialization idempotent.** Create-if-missing for dirs, collections, indexes, so it's safe to
run on every startup and every retry.

```python
if DatabaseEnum.COLLECTION_CHUNK_NAME.value not in await db.list_collection_names():
    await db.create_collection(DatabaseEnum.COLLECTION_CHUNK_NAME.value)
    for idx in DataChunk.get_indexes():
        await db[DatabaseEnum.COLLECTION_CHUNK_NAME.value].create_index(idx["key"], name=idx["name"])
```

Prefer the atomic forms where they exist — `os.makedirs(path, exist_ok=True)`, Mongo `upsert=True` —
which close the check-then-act race window entirely.

**Provide get-or-create so callers never write check-then-create,** and always return the *same type*
from both branches so callers don't branch on which path ran. Back it with a **unique index** so a
race resolves at the DB level instead of creating a duplicate.

**Expose an explicit reset flag for reprocessing** (default `False`). Re-ingesting updated input
without it leaves stale data alongside new; always-on reset makes every call destructive. The flag lets
the caller state intent, and the safe default is off.

**Batch bulk writes.** The cost is the network round-trip, not the write. 500 `insert_one` calls ≈ 500
round-trips; batched `bulk_write` ≈ a handful. Cap `batch_size` (~100) so a huge input doesn't blow
memory or Mongo's request-size limit.

```python
async def insert_many(self, items, batch_size: int = 100):
    for i in range(0, len(items), batch_size):
        ops = [InsertOne(x.model_dump(by_alias=True, exclude_none=True)) for x in items[i:i+batch_size]]
        await self.collection.bulk_write(ops)
```

Principle: *know what's actually expensive.* Optimize the I/O boundary, not the loop arithmetic.

---

## 8. API design

**Split routers by concern with a versioned prefix.** One router per domain (`health`, `admin`,
`chat`, …), each `APIRouter(prefix="/api/v1/<area>", tags=["..."])`. Prefix on the router (not typed
into each path) makes versioning a one-line change; `/api/v1` from day one lets you add `/api/v2`
alongside without breaking clients; tags make `/docs` navigable.

**Define request bodies as schemas with sensible optional defaults.** Required fields required,
tunables optional with defaults. FastAPI validates before your function runs (auto-422 on bad input),
and defaults declared in the schema show up in `/docs` where clients can see them. Expose the real
tuning knobs (e.g. `chunk_size`, `overlap`) as parameters; keep destructive options (`do_reset`)
opt-in with a `False` default.

**Use explicit `status.HTTP_*` constants, and get 4xx vs 5xx right.** 4xx = client's problem, don't
retry unchanged; 5xx = server's problem, retry may help. A rejected file type is 400; a disk write
failure is 500. Getting it backwards makes clients retry the hopeless and abandon the recoverable.
Constants over bare integers: `status.HTTP_40_BAD_REQUEST` is a loud `AttributeError`; `40` is a
silently wrong response.

**Return a stable machine-readable outcome code** (a `signal` from the enum) alongside any
human-readable message. Free-text errors force clients to string-match prose that breaks when you
reword it; a stable code lets the message change freely. This is the shape mature APIs converge on.

---

## 9. Observability

**Use the `logging` module, never `print()`.** `print` has no timestamp, no severity, no source
module, no destination control — you can't filter it, route errors to alerting, or quiet it in prod.
Attach to the framework's logger (`logging.getLogger('uvicorn.error')`) or use
`logging.getLogger(__name__)` so each line reports its source module.

Severity levels and when each applies: **DEBUG** (dev detail) · **INFO** (normal events) · **WARNING**
(recovered from something odd) · **ERROR** (an operation failed, app lives) · **CRITICAL**
(app-threatening). Levels let you run verbose locally and quiet in production without code changes.

**Wrap outside-world I/O in try/except; log *and* return.** Disk/network can fail in ways you can't
prevent (disk full, permissions, client disconnect). Log for yourself (searchable, with context) and
return a structured signal for the client. Log *before* returning so the record survives even if the
response never reaches the client. Catch specific exceptions (`OSError` for files) at inner layers so a
`TypeError` in your own code still surfaces loudly; a broad `except Exception` is acceptable only at the
outermost route boundary — and be wary of leaking `str(e)` (paths, internals) to clients in production.

**Check for empty, not just for errors.** "No exception raised" ≠ "useful work happened." A file that
processes into zero chunks should be a 400, not a 200 with `count: 0` — otherwise the user believes
their data is indexed and only finds out much later. Guard-clause the empty case early.
