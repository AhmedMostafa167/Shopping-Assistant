---
name: production-python-backend
description: Clean-code and production-habit standard for building Python backends (FastAPI with async MongoDB/Motor, Pydantic v2, uv). Use this skill whenever writing, scaffolding, reviewing, or refactoring Python backend code - endpoints, controllers, models, schemas, config, database access, file handling, or a whole new service. Trigger it even when the user just says "add an endpoint", "write a FastAPI route", "set up a new project", "connect to Mongo", "review my code", or "clean this up", even if they don't mention "clean code" or "best practices". Encodes five core principles (fail loudly/early, single source of truth, separation of concerns, design for retry, never trust input) plus a concrete boilerplate and an anti-pattern review pass. Apply it proactively rather than waiting to be asked.
---

# Production Python Backend

A standard for writing Python backend code that is correct, maintainable, and production-shaped from
the first line — not code that "works" but code another engineer (or you in six months) can extend
without archaeology.

This skill exists because the small cross-cutting decisions — why enums instead of raw strings, why
config instead of literals, why validate at the boundary — are the transferable part of backend
engineering. They span every file and belong to no single feature, so they're easy to skip and
expensive to retrofit. This skill makes them the default.

## When to apply

Apply on any of these; they are all in scope:

- **Writing new code** — an endpoint, controller, model, schema, config, DB access, file handling.
- **Scaffolding a new service or module** — folder layout, entry point, settings, DB wiring.
- **Reviewing or refactoring** existing code — run the anti-pattern pass.

Do not wait for the words "clean code" or "best practices." If the task is Python backend work, this
is the standard.

## How to use this skill

1. **Internalize the five principles below.** Every specific rule is one of these wearing a costume.
   If you remember nothing else, remember these and the question at the end.
2. **For the specific rules** — the habit-by-habit "do this, not that" with rationale and code —
   read `references/checklist.md`. Consult it while writing; do not reproduce code from memory when
   the reference has the vetted version.
3. **When scaffolding anything new** — a project, a module, a new model/controller/router — read
   `references/boilerplate.md`. It has the exact layout, the entry point, the base classes, the
   settings, and the naming conventions, plus production patterns (health checks, error handling,
   dependency injection, testing seams) that a bare tutorial skips.
4. **When reviewing or before declaring code done** — run the pass in `references/antipatterns.md`.
   These are real, high-frequency mistakes; each entry is a thing to actively look for and the fix.

Read the reference file relevant to the task. Don't dump all three into context for a one-line change.

## The five principles

Every rule in this skill reduces to one of these. When a situation isn't covered by a specific rule,
reason from these.

### 1. Fail loudly, fail early

Convert silent wrong behavior into loud, immediate errors, and surface them as close to the cause as
possible. A magic string typo fails silently at runtime, maybe never; an enum typo is an
`AttributeError` at import. An untyped env var fails as a `TypeError` deep in a request weeks later; a
typed setting fails at startup naming the field. **The earlier and louder the failure, the cheaper the
fix.** Prefer: enums over strings, typed validated settings, Pydantic `Field` constraints, validation
at the boundary, explicit checks for empty/None results.

### 2. Single source of truth

Every fact your system depends on — a path, a collection name, a size limit, a setup step — is written
exactly once. Every duplicate is a future inconsistency waiting for someone to edit one copy and miss
the other. Prefer: config in one settings object, paths built in one place, constants in enums, shared
construction in base classes, `.env.example` as the one declaration of required config.

### 3. Separation of concerns

Each layer has one job and does not know how the others work internally; dependencies point toward
stable things (your logic), never toward volatile ones (HTTP frameworks, databases). Routes handle
HTTP, controllers hold logic and never import the web framework, models are the only place that
touches the database. This is what makes logic testable, reusable from a CLI or worker, and the
database swappable. Verify it: controllers have no `fastapi` import; routers issue no DB queries.

### 4. Design for retry (idempotency)

Assume every operation runs more times than you intended — servers restart, requests get retried,
users double-click, jobs re-run after failure. Ask of any state-changing code: *"what happens if this
runs twice?"* If the answer isn't "nothing bad," fix it. Prefer: idempotent init (create-if-missing,
`exist_ok=True`, `upsert`), get-or-create, explicit reset flags for reprocessing, and unique
constraints that make the database reject a duplicate the application logic raced on.

### 5. Never trust input

Data is checked the moment it enters the system, at the outermost boundary, so everything inside can
assume validity. Prefer: validate type/size before doing work, sanitize user-controlled strings with
an **allowlist** (never a blocklist — you will miss something), schema constraints that make invalid
objects unconstructable, streaming instead of buffering unbounded input, and treating filenames/paths
as attacker-controlled.

## The one question

When unsure whether a line is good enough, ask:

> **"If this were wrong, when would I find out — and how hard would it be to trace?"**

Good design shrinks the distance between the mistake and the noise it makes. Enums shrink it to
import time. Typed config shrinks it to startup. Boundary validation shrinks it to the first request.
Magic strings and untyped `os.getenv` stretch it to "three weeks later, in production, no stack trace."
Optimize for a short distance.

## Non-negotiables (the short list)

If you do nothing else on a small change, still do these:

- **No magic strings** for any value from a fixed set → enum (inherit `(str, Enum)` if it crosses a
  JSON/DB boundary).
- **No hardcoded config** — limits, URLs, secrets, paths → typed settings from `.env`.
- **No DB calls in routers, no `fastapi` in controllers** — keep the layers clean.
- **Validate and sanitize input at the boundary** before using it — especially anything that becomes
  a path.
- **`by_alias=True, exclude_none=True`** (or `exclude_unset=True`) on every Pydantic → Mongo dump.
- **Never commit `.env` or database data files** — see the git hygiene note in `antipatterns.md`.
- **Async all the way down** — Motor not PyMongo, `aiofiles` not `open`, `httpx.AsyncClient` not
  `requests`, inside any `async def`.

## Language and framework scope

The concrete examples target the stack this standard was distilled from: **FastAPI, Motor (async
MongoDB), Pydantic v2, and `uv`.** The five principles and most rules transfer directly to other
stacks (SQLAlchemy, Django, a different DB); when the stack differs, keep the principle and adapt the
mechanism. Note stack-specific advice as such rather than forcing it where it doesn't fit.
