# Version Drift

The MLOps stack breaks its own APIs faster than the internet updates. Most tutorials, blog posts, and
course material you will find are written against a version you are not running — and the wrong code
usually **imports fine and fails later**, which is the worst way to find out.

**Read this before writing code against any of these tools.**

## Contents

1. The habit
2. MLflow — stages → aliases
3. Airflow — 2 → 3
4. BentoML — 1.1 → 1.2+
5. Python version choice
6. How to write about a deviation

---

## 1. The habit

Before following any example, run two commands:

```bash
<tool> --version
pip show <package> | head -3
```

Then check the tool's docs **with the version selector set to what you actually have.** Old docs stay
online and stay wrong for you.

Three tells that a code sample is for an older version:

- It uses a concept the current docs call "legacy"
- Its import paths are shorter than the current ones (frameworks tend to split into provider packages
  as they mature)
- It configures something the current version does automatically

Some tools ship linters for their own migrations. Use them if they exist — automated detection beats
reading release notes.

---

## 2. MLflow — stages → aliases

**Deprecated since 2.9.** `transition_model_version_stage` and `get_latest_versions` emit a
`FutureWarning` pointing at a migration guide.

```python
# Old — deprecated
client.transition_model_version_stage(name, version, "Production")
client.get_latest_versions(name, stages=["Production"])
mlflow.pyfunc.load_model("models:/name/Production")

# Current
client.set_registered_model_alias(name, "production", version)
client.get_model_version_by_alias(name, "production")
mlflow.pyfunc.load_model("models:/name@production")
```

**Behavioural differences, not just syntax:**

- `get_model_version_by_alias` **raises** when the alias does not exist; `get_latest_versions`
  returned an empty list. Catch `RestException` explicitly.
- A version holds one stage but **any number of aliases**, so `@champion` and `@production` can
  diverge during a canary.
- Setting an alias is idempotent. No state machine, no archive flag.

**Also renamed:** `artifact_path` → `name` on `log_model`.

**Also deprecated:** framework-specific savers in some serving tools; check before building on
`bentoml.onnx`, `bentoml.sklearn` and their siblings.

---

## 3. Airflow — 2 → 3

Airflow 3 shipped in April 2025; **Airflow 2 reached end of life in April 2026.** If your material
says "webserver", it is for a version no longer supported.

### Services

Airflow 3 splits into more components. A local deployment needs roughly six services, not one:

`postgres` · `init` · `api-server` · `scheduler` · `dag-processor` · `triggerer`

The command is `airflow api-server`, not `airflow webserver`, and the DAG processor is now its own
service.

### Imports

```python
# Airflow 2
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.sensors.filesystem import FileSensor

# Airflow 3
from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.standard.sensors.filesystem import FileSensor
```

`airflow.decorators.dag` is **removed**. Operators moved into provider packages.

### Task workers no longer read the database

This one is architectural and produces a genuinely misleading error.

In Airflow 3, tasks fetch connections and variables over an **Execution API** served by the API
server, rather than querying the metadata database directly. A misconfigured or unreachable endpoint
produces:

```
AirflowNotFoundException: The conn_id `fs_default` isn't defined
```

**Identical to the message for a connection that genuinely does not exist** — even when
`airflow connections list` shows it right there. If you see this while the connection demonstrably
exists, suspect the Execution API URL, not the connection.

### Auth

`airflow users create` fails on Airflow 3 with a security-manager `AttributeError`, because the
default auth manager no longer stores users in the database. It generates a password at startup and
prints it:

```bash
docker compose logs airflow-apiserver | grep -i "Password for user"
```

Switching to the database-backed auth manager is possible but is a configuration change, not a
command.

### Setup traps

- **Init containers must run as the airflow user**, not root. Airflow is installed under that user's
  home; as root, `import airflow` fails outright.
- **Mounted log directories must be owned by the container's UID.** Otherwise the DAG processor
  crash-loops with a `FileNotFoundError` on its own log file — a permissions failure disguised as a
  missing file.
- **Default connections do not exist.** Anything that ships with a `_default` connection in Airflow 2
  must be created explicitly.

---

## 4. BentoML — 1.1 → 1.2+

**The single largest source of confusion in this stack**, because almost every tutorial online is
1.1 and the concept it centres on is gone.

```python
# BentoML 1.1 — most tutorials. Runners are legacy.
runner = bentoml.sklearn.get("model:latest").to_runner()
svc = bentoml.Service("my_service", runners=[runner])

@svc.api(input=JSON(), output=JSON())
def predict(payload):
    return runner.predict.run(payload)
```

```python
# BentoML 1.2+
@bentoml.service(workers=4, resources={"cpu": "4"})
class MyService:
    def __init__(self):
        self.model = bentoml.onnx.load_model("model:latest")

    @bentoml.api
    def predict(self, payload: MyPydanticModel) -> MyResponse:
        ...
```

A class with decorators. Plain Python type hints instead of `IODescriptor` objects. No `Runner`.
`bentoml.runner_service()` exists as a migration shim and is marked deprecated in the source.

**If material asks for a "Runner", it maps onto three things in 1.2+:**

| 1.1 concept | 1.2+ equivalent |
|---|---|
| Process separation | Automatic — the service decorator already does it |
| Worker count | `workers=N` on the decorator |
| Independent scaling | `bentoml.depends()` between services |

**Also deprecated since 1.4:** the framework-specific savers (`bentoml.onnx`, `bentoml.sklearn`, and
siblings) in favour of a generic model API. They still work; they will not forever.

---

## 5. Python version choice

**Picking the newest Python costs tool compatibility, and the cost is not theoretical.**

Two real instances from one project on Python 3.14:

**A data-versioning tool resolved to a release from 2021.** No recent version declared 3.14 support,
so the resolver walked backwards until it found one with no upper bound — then crashed on a private
`pathlib` API removed in 3.12. The traceback pointed at the tool, not at the Python version.

**An orchestrator's official image shipped Python 3.13**, so installing the project into it failed on
`Requires-Python >=3.14`. The constraint had to be relaxed.

**Guidance:**

- **The newest Python is a cost, not a feature**, unless you need something specific from it. A
  version one or two behind has wheels for everything.
- **Check base images before pinning.** Official images for orchestrators and serving tools lag by a
  release or two, and your project must install into them.
- **Install CLI tools standalone**, not as project dependencies. `uv tool install`, `pipx` — anything
  you never `import` should resolve against its own interpreter, not yours. This alone fixes the
  first instance.
- **Watch for silent backward resolution.** A package manager that "successfully" installs something
  years old is telling you about an incompatibility, quietly. Check the version it chose.

---

## 6. How to write about a deviation

When the current version forces you away from what your reference material specifies, **say so
explicitly.** It is a stronger artifact than silently following deprecated instructions, and a
reviewer will spot the difference anyway.

The shape:

> The handbook specifies the `None → Staging → Production` stage lifecycle. MLflow deprecated stages
> in 2.9 with a `FutureWarning` pointing at the alias migration guide. This project uses
> `models:/churn-predictor@production` instead — a deliberate deviation, on the grounds that building
> on an API scheduled for removal was the worse option.

Three parts: **what was specified**, **what changed and how you know**, **what you did and why**.

This applies to every entry above. A note saying "Airflow 3 moved operators into provider packages,
so the import paths differ from the handbook" takes one line and demonstrates that you read the
warnings rather than ignoring them.
