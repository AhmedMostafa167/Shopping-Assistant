# Anti-patterns — the review pass

Run this before declaring code done, and when reviewing existing code. Each entry is a concrete thing
to **actively look for**, why it's a problem, and the fix. These are real, high-frequency mistakes —
several were found in production-ish code that otherwise looked fine. Ordered by severity.

For each finding, prefer showing the specific line and the corrected version over a general lecture.

## Table of contents

- 🔴 Security & data-loss
- 🔴 Correctness bugs
- 🟡 Maintainability & consistency
- 🟢 Polish

---

## 🔴 Security & data-loss

### `.env` (or any secret) committed to git
**Look for:** a tracked `.env`, hardcoded API keys/passwords/connection strings in source or history.
**Why:** anything committed is in history *permanently*, even after deletion — rotating the secret is
the only real remedy. **Fix:** `echo ".env" >> .gitignore` then `git rm --cached .env`; keep
`.env.example` with placeholders. Remember: **`.gitignore` only affects untracked files** — if it was
ever committed, ignoring it does nothing without `git rm --cached`.

### Database / data volumes committed
**Look for:** DB data files under version control (e.g. `docker/mongodb/`, `*.wt`, `mongod.lock`,
`data/db/`). **Why:** runtime state, not source — it bloats the repo, causes unresolvable binary
conflicts, and can leak real data. **Fix:** `git rm -r --cached <data-dir>` and add it to
`.gitignore` (which won't help until untracked — same trap as above).

### Blocklist sanitization of user input
**Look for:** filtering untrusted input by removing known-bad patterns (`filename.replace("..","")`).
**Why:** a blocklist must enumerate everything dangerous; you'll miss one and the attacker needs one.
**Fix:** allowlist what's safe and reject the rest: `re.sub(r'[^\w.-]', '_', name.strip())`.

### Untrusted input used to build a path without sanitization
**Look for:** `os.path.join(base, user_value)` where `user_value` is a filename, project id, etc.
straight from the request. **Why:** path traversal (`../../etc/passwd`) escapes the intended
directory. **Fix:** sanitize (allowlist) and/or validate (`@field_validator` requiring alphanumeric)
before the value ever reaches a path.

### Leaking internals to clients
**Look for:** `content={"error": str(e)}` returned to the client on exceptions. **Why:** exception
text can expose absolute paths, DB structure, or stack internals. **Fix:** log the detail
server-side; return a stable `signal` code (and a generic message) to the client.

---

## 🔴 Correctness bugs

### Referencing an enum member / attribute that doesn't exist
**Look for:** `SomeEnum.MEMBER_NAME` where the enum defines a differently-spelled member
(`FILE_INGESTION_FAILED` vs `FILE_INGESTION_FAILURE`). **Why:** raises `AttributeError` at the moment
that branch runs — and error branches are rarely exercised, so it hides until a real failure triggers
it, then crashes the error handler itself. **This is the enum principle proving itself** — with a magic
string it would fail silently forever. **Fix:** align the names; deliberately test failure paths, not
just happy paths.

### The mutable / call-in-default-argument trap
**Look for:** a default argument that is a function call or mutable literal —
`def __init__(self, config=get_settings())`, `def f(items=[])`. **Why:** defaults are evaluated **once
at function-definition (import) time**, so every call shares the same object. It "works" until state
leaks between instances/calls. **Fix:**
```python
def __init__(self, config: Settings | None = None):
    self.settings = config or get_settings()
```

### Pagination that skips by page number instead of offset
**Look for:** `.skip((page - 1))` or similar. **Why:** `skip` takes a *document count*; page 2 then
skips 1 doc instead of `page_size`, so pages overlap. **Fix:** `.skip((page - 1) * page_size)`.

### Pydantic → Mongo dump without `by_alias`
**Look for:** `collection.insert_one(model.model_dump())` (or `.dict()`) with no `by_alias=True`.
**Why:** writes a literal `"id": null` field *and* lets Mongo generate a separate `_id` — two identity
fields; queries by `id` silently return nothing. Fails silently. **Fix:**
`model.model_dump(by_alias=True, exclude_none=True)`.

### Blocking call inside `async def`
**Look for:** `open()`/`.read()`/`.write()`, `requests.get()`, `time.sleep()`, or PyMongo inside an
`async` function. **Why:** freezes the single event loop; every concurrent request stalls. No error —
just latency under load. **Fix:** `aiofiles`, `httpx.AsyncClient`, `asyncio.sleep`, Motor; or
`await loop.run_in_executor(None, blocking_fn)` for unavoidable blocking libs.

### Reporting success on empty output
**Look for:** a pipeline that returns 200/OK without checking it produced anything. **Why:** an empty
or unreadable input processes into zero results and reports success; the user thinks their data is
there and finds out much later. **Fix:** guard-clause the empty case early and return a 400 with an
explanatory signal.

### `authSource` omitted from the Mongo URL
**Look for:** a connection string with credentials but no `?authSource=admin`. **Why:** the driver
authenticates against the target DB (where the root user doesn't exist) and fails with a *misleading*
"authentication failed" — sending you to debug the password. **Fix:** append `?authSource=admin`.

---

## 🟡 Maintainability & consistency

### Magic strings for a fixed value set
**Look for:** repeated string literals for states, types, collection names, messages (`"pdf"`,
`"chunks"`, `"completed"`). **Why:** typos fail silently; renames require a full-codebase search.
**Fix:** an enum (`(str, Enum)` if it crosses JSON/DB).

### Hardcoded config values
**Look for:** inline limits, URLs, ports, paths, keys. **Why:** changing them requires a code change +
redeploy, so the running code diverges from what was tested. **Fix:** typed settings from `.env`.

### DB query in a router, or `fastapi` import in a controller
**Look for:** `collection.find(...)` inside a route function; `from fastapi import ...` or
`JSONResponse` in a controller. **Why:** the layers are fused — logic can't be tested without HTTP,
reused from a worker, or the DB swapped. **Fix:** move queries into the model layer; keep controllers
framework-free.

### Inconsistent enum base classes
**Look for:** some enums `(str, Enum)`, others plain `Enum` in the same codebase. **Why:** the plain
ones need `.value` everywhere and break serialization the moment you forget; the inconsistency is a
constant papercut. **Fix:** standardize on `(str, Enum)` for anything crossing a JSON/DB boundary.

### Frozen typos in names
**Look for:** misspellings baked into class/function/field names (`ProccessController`, `ResponseSignel`,
`resault`). **Why:** every future use must remember the misspelling, and it reads as careless in a
portfolio. **Fix:** rename in one dedicated commit — cheapest now, more expensive with every new
reference. Names are an interface.

### Bare `object` (or missing) type hints on non-trivial params
**Look for:** `def __init__(self, db_client: object)`, untyped public function signatures. **Why:**
`object` documents nothing and disables autocomplete/type-checking. **Fix:** the concrete type
(`AsyncIOMotorDatabase`).

### Comparing a bool to an int
**Look for:** `if do_reset == 1:` where `do_reset` is a `bool`. **Why:** works by coincidence
(`True == 1`) but obscures intent. **Fix:** `if do_reset:`.

### Schema constraint that doesn't match the real invariant
**Look for:** `ge=0` on a field that's always 1-indexed, `str` on something that's really an enum, an
optional field that's actually required. **Why:** constraints should encode the *actual* rule, or they
mislead. **Fix:** tighten to the true invariant (`ge=1`, the enum type, `Field(...)`).

### Two formats for one concept
**Look for:** the same idea expressed two ways in different files (e.g. an index `key` as a list of
dicts in one schema and a list of tuples in another). **Why:** one of them is probably wrong for the
library, and the inconsistency is a maintenance trap. **Fix:** pick the correct form (pymongo wants
`[(field, direction)]` tuples) and use it everywhere.

---

## 🟢 Polish

### Unused imports / dead code
**Look for:** imports the file never references; results assigned and never used; commented-out blocks.
**Why:** they mislead readers about dependencies and intent. **Fix:** delete them; run `ruff` to catch
them automatically.

### Duplicate / redundant work
**Look for:** a value computed and never used, or a helper called twice for the same result. **Why:**
noise that suggests the code wasn't re-read. **Fix:** remove the redundant path.

### Runtime artifacts committed
**Look for:** uploaded files, logs, caches, generated output under version control. **Why:** they're
runtime state, bloat the repo, and can leak data. **Fix:** gitignore the directory contents (keep the
folder with a `.gitkeep`).

### Comments that restate the code
**Look for:** `# increment counter` over `counter += 1`. **Why:** adds nothing and rots into a lie when
the code changes. **Fix:** delete it; spend comments on *why* (motivation, rejected alternatives), and
let clear names/small functions express *what*.

### Placeholder metadata
**Look for:** `description = "Add your description here"` in `pyproject.toml`, a missing/empty README,
no LICENSE. **Why:** signals an unfinished, not-meant-to-be-read project — and unlicensed code is
legally unusable by others even when public. **Fix:** real description, a README answering
what/setup/run, an MIT (or chosen) LICENSE.

---

## The two-minute review

If time is short, check these six — they catch the highest-severity issues:

1. Is `.env` or any DB data committed? (`git ls-files | grep -E '\.env$|/data/|mongodb/'`)
2. Any magic strings that should be enums? Any hardcoded config?
3. Any DB call in a router or `fastapi` import in a controller?
4. Any blocking call inside `async def`?
5. Every Pydantic→Mongo dump using `by_alias=True`?
6. Is untrusted input validated/sanitized before it's used (especially in a path)?
