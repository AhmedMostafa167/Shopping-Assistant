# Data, Pipelines, and Orchestration

Versioning datasets, declaring pipelines, and deciding what runs where.

## Contents

1. Why Git cannot version data
2. Versioning data with DVC
3. Pipeline stages
4. Params are inputs, never outputs
5. Closing the lineage loop
6. CI versus orchestration
7. Writing a training DAG

---

## 1. Why Git cannot version data

Git stores changes as diffs, which works beautifully for text and not at all for data. A 50 MB CSV
has no meaningful diff — change one row and Git stores a whole new 50 MB blob. Ten versions is
500 MB, permanently, in every clone forever. Model checkpoints are worse.

So people stop versioning data, and then this happens:

> "Production scores 0.86. I retrained today with the same code and got 0.81. What changed?"

The code is in Git, so that is identical. The data is `final_v2_CLEANED_use_this.csv` on someone's
laptop. The experiment is unreproducible and the honest answer is a shrug.

Three things must line up for reproducibility: **code** (Git), **params** (Git, if you are
disciplined), **data** (the gap). A data-versioning tool fills it, and — this is the part that
matters — ties all three to the *same commit*.

---

## 2. Versioning data with DVC

The whole idea: **big files go to cheap storage, a tiny text pointer goes to Git.**

```bash
dvc add data/raw/dataset.csv
git add data/raw/dataset.csv.dvc data/raw/.gitignore
git commit -m "data: track dataset"
dvc push
```

The `.dvc` file is under 200 bytes and contains a hash. Git versions it perfectly, because it is text.
The real file lives in S3, MinIO, or a network share.

The commands mirror Git deliberately, and **every Git operation on data has a DVC twin**:

| Intent | Commands |
|---|---|
| Save a change | `git push` **and** `dvc push` |
| Get someone's change | `git pull` **and** `dvc pull` |
| Go to an old version | `git checkout <ref>` **and** `dvc checkout` |
| Check sync | `git status` and `dvc status -c` |

Almost every confusing problem is one half of a pair being forgotten. `git push` without `dvc push`
means your colleague gets a pointer to data that exists only on your laptop.

### Proving it works

The demonstration that matters is **content versioning at a fixed path** — not two differently-named
files:

```bash
wc -l data/raw/dataset.csv          # 5001
git checkout HEAD~1 && dvc checkout
wc -l data/raw/dataset.csv          # 7044   ← the proof
git checkout main && dvc checkout
wc -l data/raw/dataset.csv          # 5001
```

Three different contents from one path, driven entirely by the commit. If `dvc checkout` reports a
*modification* rather than an add or delete, you are versioning content.

### Installing it

**Install the CLI as a standalone tool, not a project dependency.** You never `import dvc`; it is a
command like `git` or `docker`. Adding it to your project forces it to resolve against your
interpreter and your pins, and the resolver may silently fall back to a release from years ago that
crashes on a modern Python. See `version-drift.md` §5.

```bash
uv tool install "dvc[s3]"      # not uv add
```

---

## 3. Pipeline stages

Versioning files is half of it. The other half is versioning the *process*.

```yaml
# dvc.yaml — at the repository root
stages:
  prepare:
    cmd: python pipelines/run_prepare.py
    deps:
      - pipelines/run_prepare.py
      - src/prodml/data.py                    # source files ARE dependencies
      - data/raw/dataset.csv
    outs:
      - data/interim/clean.parquet

  featurize:
    cmd: python pipelines/run_featurize.py
    deps:
      - pipelines/run_featurize.py
      - src/prodml/data.py
      - data/interim/clean.parquet
    params:
      - featurize.seed
    outs:
      - data/processed/features.pkl

  train:
    cmd: python pipelines/run_train.py
    deps:
      - pipelines/run_train.py
      - src/prodml/train.py
      - data/processed/features.pkl
    params:
      - train.learning_rate
    metrics:
      - metrics/train.json:
          cache: false
```

`dvc repro` hashes each stage's deps and params, compares against the lockfile, and **runs only what
changed.** Change a training hyperparameter and `prepare` and `featurize` skip; change the cleaning
code and everything downstream re-runs.

Five things that decide whether this works:

**Source files must be in `deps`.** DVC has no way to know your code changed unless you tell it.
Omit them and editing training logic triggers nothing.

**Path resolution is relative to the file's own directory.** Put `dvc.yaml` at the repository root
and the paths you naturally write are correct. Elsewhere, every path needs `../` or a `wdir`.

**Commit the lockfile.** It records which input hashes produced which output hashes — the thing that
makes a run reproducible rather than merely repeatable. Treat it like any lockfile: never hand-edit,
always commit.

**Stage outputs are tracked automatically.** Never `dvc add` a pipeline output; two mechanisms would
claim the same path.

**A stage can legitimately have no outputs.** A training stage whose real product is a registered
model version has nothing on disk to track but the metrics file. That is a genuine seam between the
pipeline tool and the model registry, not a modelling error — name it rather than inventing a
placeholder output.

### Ordering stages that share no file

DVC infers order from shared filenames. Two stages that share none are **parallel branches**, and may
run in either order — so an evaluation stage might score the *previous* model while the training
stage produces a new one. If evaluation must follow training, give it the training stage's metrics
file as a dependency. The dependency is the edge.

---

## 4. Params are inputs, never outputs

A tuning run produces "best parameters". The temptation is to write them back into the config file.
**Do not.**

Config is committed to Git — it is part of your code, the declaration of *how we train*. If runs
mutate it:

- **Reproducibility inverts.** Checking out a commit no longer gives you the config that produced its
  results; it gives you whatever ran most recently.
- **CI cannot do it.** A runner has a read-only checkout, and you would not want a bot pushing to the
  default branch on every training run.
- **Pipeline caching becomes nonsense.** A stage that modifies its own declared dependency leaves the
  graph permanently dirty.

The principle: **config files are inputs; results go to the tracking store.** Search *ranges* are
config and are committed. Best params are a result, logged to the tracker on the sweep's parent run.
To promote a tuned value to a default, read it from the tracker and edit the config **by hand, as a
commit** — a deliberate human decision, not a side effect.

---

## 5. Closing the lineage loop

The payoff of data versioning is one tag:

```python
def get_data_version(dvc_file: str) -> str:
    with open(dvc_file) as f:
        return yaml.safe_load(f)["outs"][0]["md5"]

mlflow.set_tag("data_version", get_data_version("data/raw/dataset.csv.dvc"))
```

Now any run ID identifies the exact dataset it learned from. Find the commit whose `.dvc` file carries
that hash, `dvc checkout`, and you have the precise bytes.

**Run ID → data hash → exact file.** That closed loop is what "reproducible" means operationally, as
opposed to aspirationally.

---

## 6. CI versus orchestration

These get confused because both "run things automatically". They answer different questions.

| | CI (GitHub Actions, GitLab CI) | Orchestrator (Airflow, Dagster, Prefect) |
|---|---|---|
| Triggered by | A code change | Time, or data arriving |
| Answers | "Does this commit work?" | "Did this week's training complete?" |
| Duration | Minutes | Hours, indefinitely |
| Output | Pass/fail on a diff | A state machine you can inspect |
| Retry | Rerun the whole job | Retry from the failed task |
| Backfill | No concept | First-class |

**Training does not belong in PR CI.** A runner has a couple of cores and a time limit; training
needs hours and sometimes a GPU. Nobody trains a real model on a pull-request check — it would take
longer than the review and cost more than the reviewer. Put lint and fast tests in CI; put training
in the orchestrator.

The corollary matters for quality gates. A gate compares a candidate against the current production
model, which requires a **persistent registry**. An orchestrator has one. An ephemeral CI runner does
not — it stands up an empty registry, finds no baseline, and passes unconditionally. The gate is the
right logic in the wrong lane. See `antipatterns.md` §7.

### Three lanes, in practice

| Lane | Trigger | Runs | Where |
|---|---|---|---|
| **CI** | Every PR | Lint, unit tests on fixtures | Hosted runner, under 5 min |
| **Training** | Schedule, new data, manual | Full pipeline, real data, quality gate | Orchestrator, real hardware |
| **CD** | Merge, or gate passing | Build image, deploy | Hosted runner → cluster |

---

## 7. Writing a training DAG

```
extract → validate → featurize → train → evaluate → branch → [register | skip] → notify
```

Six things that matter more than the operator syntax, which changes between versions anyway.

### Pass references, never data

Inter-task values are serialised into the orchestrator's metadata database and read on every
scheduler heartbeat. A DataFrame there bloats the database and slows *every* pipeline in the
deployment, not just yours. Each task returns a **path or an ID**; the next task reads the file
itself.

### Branching skips, and skipped is not success

After a conditional branch, exactly one downstream path is *skipped*. A join task with the default
"all upstream succeeded" rule therefore never runs, regardless of which branch was taken. Use the
rule that accepts skipped upstreams (`none_failed_min_one_success` in Airflow).

This fails silently — the task simply never appears — which makes it the most common branching bug.

### Sensors need a reason to exist

A sensor watching a fixed, always-present file never waits for anything. A meaningful sensor watches
for a **new partition**, which requires date-partitioned data. If you do not have that, say so rather
than shipping a decorative sensor.

### Retries and timeouts on every task

`retries=2` with a delay handles transient failure. An explicit `execution_timeout` on the training
task specifically — it is the one that can plausibly hang, and the platform default is typically
hours.

### Idempotency

Running the same logical date twice must not corrupt anything. Ask of every task: *what happens if
this runs twice?* If the answer is not "nothing bad", fix it before you need to.

### Backfill needs partitioned data to mean anything

Backfilling three past dates against a single fixed file produces three **identical** runs, because
"the data as of last Tuesday" does not exist. This is worth demonstrating and then naming honestly:
backfill is only meaningful when a run's logical date selects a different slice of data.

### Tasks should be thin

An orchestrator task that trains a model in-process holds a worker slot for hours. In production the
task *submits* work — a job, a container, a cluster step — and waits. On a single-machine setup that
is not achievable, which is fine; name it as a limitation rather than pretending otherwise.
