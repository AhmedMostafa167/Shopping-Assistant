---
name: mlops-model-lifecycle
description: Production standard for the machine-learning lifecycle — experiment tracking, data versioning, model registries, promotion gates, serving patterns, and release strategy. Use whenever work touches a model after training — logging runs, registering or promoting a model, versioning a dataset, wiring a training pipeline, choosing between online/batch/streaming inference, converting to ONNX, load testing a prediction service, or rolling out a new version. Trigger it even when the user just says "log this to MLflow", "set up DVC", "deploy the model", "serve this with BentoML", "why is inference slow", or "add a training DAG" — and even when they never say "MLOps". Encodes five principles (lineage is not optional, the model is a reference not a file, preprocessing travels with the model, measure before you believe, your code runs in more environments than you think) plus an anti-pattern review pass drawn from real failures. Apply proactively rather than waiting to be asked.
---

# MLOps Model Lifecycle

A standard for everything that happens to a model after `fit()` returns — and for the decisions that
make a trained model into a system someone else can operate, audit, and roll back.

This skill exists because the failures here are quiet. A model that loads the wrong preprocessing
still returns plausible numbers. A promotion gate with no baseline passes every time. A pickled
wrapper breaks six months after a file rename, in production, at load time. None of these announce
themselves the way a syntax error does, and none of them appear in a tutorial that ends at
`model.predict(X)`.

**Companion skill:** `production-python-backend` covers writing the service code — layering, config,
validation, the anti-pattern pass on Python. This skill covers everything around the model. When
building a prediction API, both apply: that one for the endpoint, this one for how the model gets
there and what happens when it changes.

## When to apply

All of these are in scope:

- **Tracking** — logging runs, params, metrics, artifacts, or tags
- **Versioning** — datasets, pipelines, reproducibility
- **Registry** — registering, promoting, aliasing, rolling back a model
- **Serving** — choosing a pattern, wrapping a model, exposing it over HTTP, batch, or a stream
- **Runtime** — ONNX, OpenVINO, TensorRT, quantisation, any "make it faster" claim
- **Release** — canary, shadow, blue/green, automatic rollback
- **Orchestration** — training DAGs, schedules, retraining triggers
- **Reviewing** any of the above

Do not wait for the word "MLOps". If the task touches a model's life after training, this is the
standard.

## How to use this skill

1. **Internalize the five principles below.** Every specific rule is one of them wearing a costume.
2. **For tracking, registry, and promotion mechanics** — read `references/tracking-and-registry.md`.
3. **For data versioning, pipelines, and orchestration** — read `references/data-and-pipelines.md`.
4. **For serving patterns, runtimes, load testing, and release** — read
   `references/serving-and-release.md`.
5. **Before declaring anything done, or when reviewing** — run the pass in
   `references/antipatterns.md`. Every entry is a failure that actually happened, with the fix.
6. **Before writing code against MLflow, Airflow, BentoML, or DVC** — read
   `references/version-drift.md` first. These tools have all broken their APIs recently, most
   tutorials online are for the old version, and the wrong code usually *imports fine* and fails
   later.

Read the reference relevant to the task. Don't load all five for a one-line change.

## The five principles

### 1. Lineage is not optional

Every artifact records what produced it: the code commit, the data version, the parameters, the
environment. Not as documentation — as a queryable fact attached to the run.

The question this answers is the one that always gets asked and can almost never be answered:
*"the model scored 0.86 last month and 0.81 today — what changed?"* Without lineage that is a shrug.
With it, it is a diff.

Tag every run with at minimum: `git_commit`, a data version hash, and the framework. Record params
*and* metrics, never one without the other — metrics with no params are unreproducible, params with
no metrics are pointless. Include cost signals alongside quality ones: training duration and model
size are decision inputs, not trivia.

### 2. The model is a reference, not a file

The serving code names a *role* — "whatever is currently production" — and a registry resolves it.
It never names a path, and a model is never baked into an image.

The test: **can you switch the served model with zero code changes and zero rebuilds?** If swapping
a model means editing a config, rebuilding an image, and redeploying, you do not have a rollback —
you have a deploy, and it will take minutes you do not have while a bad model serves traffic.

This is also what makes promotion a *decision* rather than an event. The alias moves; nothing else
does.

### 3. Preprocessing travels with the model

A model artifact that is only weights is not servable. The vectoriser, the scaler, the encoder, the
tokenizer — whatever turns raw input into features — is part of the model and ships with it, as one
versioned unit.

The failure this prevents is the worst kind: **training and serving silently disagree.** A scaler
fitted at training but absent at inference does not raise; it produces confidently wrong predictions
that every offline metric says are fine. There is no error to find, only a model that mysteriously
underperforms in production.

Corollary: the raw-input contract belongs to the artifact too. If the service accepts a customer
record, the artifact knows how to turn a customer record into features — the caller should not.

### 4. Measure before you believe

Every performance claim gets a number from your own workload. Every gate gets a margin derived from
your own noise floor.

Accelerated runtimes, batching, quantisation and bigger hardware all *usually* help. Usually is not
a measurement. A graph optimiser has nothing to optimise on a one-node graph; batching costs latency
and only repays it under load; a GPU idles if the bottleneck is preprocessing.

And on gating: before comparing two models, know how much two *identical* runs differ. Decisions made
on differences smaller than that are coin flips wearing a lab coat. A gate that compares with a bare
`>` will promote on noise; a gate with no persistent baseline will pass unconditionally and gate
nothing at all.

> **A check that cannot fail is not a check.** Break something on purpose and confirm it goes red.

### 5. Your code runs in more environments than you think

The same training script runs on a laptop, in CI, inside an orchestrator's worker, and in a
container. The same service runs locally and behind a proxy. They differ in ways that are invisible
until they aren't.

`localhost` means the host, or the container itself, or the CI runner — three different machines,
one word. A file present in your working tree may be gitignored and absent in the image. A dependency
on your PATH may not be in the base image. A module-level import forces every environment to install
that library, including ones that never call it.

Write for the boundary, not for your machine: configuration by environment variable rather than
literal, imports deferred to where they're used, explicit checks that dependencies are reachable, and
failures that name the missing thing rather than surfacing as a timeout forty frames deep.

## The one question

When unsure whether something is production-shaped, ask:

> **"If this model were wrong, how would I find out, how fast could I undo it, and could I prove what
> caused it?"**

Lineage answers the third. A registry alias answers the second. Monitoring and gates answer the
first. Anything that leaves one of them unanswerable is the thing to fix next.

## Non-negotiables (the short list)

Even on a small change:

- **Log params and metrics together**, plus `git_commit` and a data version tag.
- **Never load a model by file path** in serving code — resolve it from a registry.
- **Bundle preprocessing with the model**, versioned as one artifact.
- **State the serving pattern and the SLA that drives it** before choosing a tool.
- **Give every promotion gate a margin**, and verify it can fail.
- **No secrets, no credentials, no data files in the repo** — config from the environment.
- **Check the tool's current major version before writing against it** — see
  `references/version-drift.md`.

## Stack scope

The worked examples use the stack this standard was distilled from: **MLflow** (tracking + registry),
**DVC** (data and pipeline versioning), **Airflow** (orchestration), **BentoML** (serving), and
**ONNX Runtime** (accelerated inference). The principles transfer directly to alternatives —
Weights & Biases, LakeFS, Dagster, Triton, TorchServe, SageMaker. When the tool differs, keep the
principle and adapt the mechanism, and say which is which rather than forcing a tool where it does
not fit.
