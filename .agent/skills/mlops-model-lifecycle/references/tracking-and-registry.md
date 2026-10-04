# Tracking and Registry

How to log runs, package models so they're actually servable, and move them through a lifecycle.

## Contents

1. What to log on every run
2. The wrapper problem — why a bare model isn't servable
3. The framework-dispatch pattern
4. Registry: aliases, not stages
5. Promotion gates
6. Loading in serving code
7. What breaks a registered model

---

## 1. What to log on every run

Six categories. Missing any one of them makes a run unreproducible or undecidable.

| Category | Contents | Why |
|---|---|---|
| **Params** | Hyperparameters, split seed, data version hash | Reproduce the run |
| **Metrics** | Quality (`roc_auc`, `f1`, `log_loss`) **plus** training duration and model size | Cost is a decision input, not trivia |
| **Artifacts** | The model, diagnostic plots, resolved dependencies | Diagnose *how* it fails, not just how well it scores |
| **Tags** | `git_commit`, `data_version`, `framework`, author | Lineage |
| **Input example** | A few real rows | Signature inference, and a serving smoke test |
| **Run name** | Human-readable | You will have hundreds |

```python
with mlflow.start_run(run_name="lr-baseline") as run:
    mlflow.log_params(params)
    mlflow.log_param("split_seed", SEED)

    with timer() as t:
        model.fit(X_train, y_train)

    y_proba = model.predict_proba(X_val)[:, 1]
    y_pred = (y_proba >= threshold).astype(int)

    mlflow.log_metrics({
        "roc_auc": roc_auc_score(y_val, y_proba),
        "f1": f1_score(y_val, y_pred),
        "log_loss": log_loss(y_val, y_proba),
        "train_duration_sec": t["elapsed"],
        "model_size_mb": model_size_mb(model),
    })

    fig, ax = plt.subplots()
    ConfusionMatrixDisplay.from_predictions(y_val, y_pred, ax=ax)
    mlflow.log_figure(fig, "confusion_matrix.png")
    plt.close(fig)                       # matplotlib leaks figures otherwise

    mlflow.set_tags({
        "framework": "logistic_regression",
        "git_commit": get_git_commit(),
        "data_version": get_data_version(),
    })
```

### Probabilities vs labels

For classification, ranking metrics (`roc_auc`, `log_loss`) need **probabilities**; threshold metrics
(`f1`, precision, recall) need **labels**. Passing labels to `roc_auc_score` does not raise — it
silently computes a degraded curve. Compute both explicitly:

```python
y_proba = model.predict_proba(X_val)[:, 1]
y_pred = (y_proba >= threshold).astype(int)
```

For a network trained with a logits loss (`BCEWithLogitsLoss`), the model emits **logits**, not
probabilities. Apply the sigmoid before metrics, never before the loss.

### Autologging

Turn it on for **one** framework, deliberately, so you can see what it captures for free versus what
you logged by hand. It is process-global and sticky — enabling it in one function affects every
subsequent run in the process, including hyperparameter sweeps.

What it will not capture: metrics at your business threshold, your plots, duration and size, and your
lineage tags. Autolog is a floor.

### Sweeps

Every trial is a **nested run** under a parent, or the UI becomes unusable. Search ranges live in
committed config; the best params are a **result** and belong in the tracker, never written back into
the config file — see `data-and-pipelines.md` §4.

Seed the sampler if you want the sweep to be reproducible. Unseeded, "best params" is one draw from a
distribution and repeated runs disagree.

---

## 2. The wrapper problem

**A framework-specific saver serialises only the estimator.** It knows nothing about the vectoriser
and scaler that raw input must pass through first. A registry version holding a bare estimator is not
servable — it is half a model.

This is principle 3 in mechanical form. The fix is a custom model wrapper that bundles everything:

```python
class ChurnModelWrapper(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        with open(context.artifacts["metadata"]) as f:
            meta = json.load(f)

        self.framework = meta["framework"]
        self.pipeline = LOADERS[self.framework](context.artifacts["model"])

        with open(context.artifacts["dv"], "rb") as f:
            self.dv = pickle.load(f)
        with open(context.artifacts["scaler"], "rb") as f:
            self.scaler = pickle.load(f)

    def predict(self, context, model_input: pd.DataFrame):
        df = model_input.copy()
        df[NUMERICAL] = self.scaler.transform(df[NUMERICAL])      # transform, never fit_transform
        X = self.dv.transform(df[CATEGORICAL + NUMERICAL].to_dict(orient="records"))
        return self.pipeline.predict_proba(X)
```

Four things this gets right, each of which is a bug if you get it wrong:

**`transform`, not `fit_transform`.** Re-fitting a scaler on one incoming row sets that row's value as
the mean, so it scales to exactly 0 — every customer looks identical to the model. Silent, and
catastrophic.

**The exact column list and order.** `dv` learned feature positions from a specific list. A different
order, or a stray extra column, lands features in the wrong slots without erroring. Import the column
lists from the same module training uses — single source of truth.

**Probabilities, not labels.** The threshold is a *serving* decision, tunable without retraining. Bake
it into the artifact and tuning it means re-registering.

**One uniform interface.** `predict()` has no framework branching. See next section.

### One artifact or several?

Separate artifacts when any piece has an independent lifecycle — the model half can become ONNX while
the transformers stay pickled. One bundle when the pieces are meaningless apart.

For a servable model: **separate.** For a build-time intermediate consumed once by the next pipeline
stage: **one file**, because there is nothing to swap and splitting only creates a way for the halves
to drift.

---

## 3. The framework-dispatch pattern

If the champion can be any of several frameworks — and if you compare model families, it can — the
naive wrapper needs branching in both loading and prediction. Loading differs (a booster's native
format, a state dict, a pickle); so does prediction (`predict_proba` vs a forward pass plus sigmoid).

A factory returning **thin adapters with one uniform method** removes all of it:

```python
class SklearnAdapter:                      # covers sklearn and any sklearn-API model
    def __init__(self, model):
        self.model = model
    def predict_proba(self, X) -> np.ndarray:
        return self.model.predict_proba(X)[:, 1]


class TorchAdapter:
    def __init__(self, model):
        self.model = model
        self.model.eval()                  # once, at load — not per request
    def predict_proba(self, X) -> np.ndarray:
        X_t = torch.tensor(X, dtype=torch.float32)
        with torch.no_grad():
            proba = torch.sigmoid(self.model(X_t))
        return proba.numpy().ravel()       # (N,1) -> (N,), matching the others


LOADERS = {"sklearn": _load_sklearn, "xgboost": _load_xgboost, "pytorch": _load_torch}
SAVERS  = {"sklearn": _save_sklearn, "xgboost": _save_xgboost, "pytorch": _save_torch}
```

Three things that make it work:

**Every adapter returns the same shape.** If one returns `(N,)` and another `(N,1)`, the uniform
interface is a lie and the caller needs to know which. Flatten explicitly.

**The framework is recorded in the artifact**, not inferred. A small `metadata.json` beside the model,
read by `load_context`. Run tags are not available to a loading model.

**`LOADERS` and `SAVERS` live side by side.** They are halves of one contract. Adding a backend means
adding both, and if they drift you get an artifact you can write but not read.

The payoff arrives later: adding ONNX is one adapter and one loader. `predict()` never learns it
exists.

---

## 4. Registry: aliases, not stages

A registry holds **named, versioned pointers** to runs. Serving asks for a name and a role; the
registry resolves it to a version.

Stages (`None → Staging → Production`) are the older model and are deprecated in current MLflow.
Aliases replace them:

```python
client.set_registered_model_alias("churn-predictor", "production", version)
mlflow.pyfunc.load_model("models:/churn-predictor@production")
```

Two reasons aliases are better, beyond not being deprecated:

- A version holds exactly one stage, but **any number of aliases**. `@champion` and `@production` can
  be the same version, or diverge during a canary.
- Moving an alias is one idempotent call. No state machine, no "archive existing versions" flag.

Note the API difference when the alias does not exist: `get_model_version_by_alias` **raises**, where
the old `get_latest_versions` returned an empty list. Catch it explicitly.

### When to register

Registering every training run fills the registry with throwaway experiments. Two reasonable rules:

- **Register the champion only** — after comparing families, register the winner. Requires reopening
  that run so the version attaches to the metrics it earned (below).
- **Register everything, promote selectively** — every run becomes a version; the alias is the real
  decision.

Either way, **promotion is the decision**, not registration.

### Attaching to the right run

If you register from a different context than training, the version attaches to a *new, empty* run —
and any gate that looks up metrics by run ID gets a `KeyError`. Reopen the champion's run:

```python
with mlflow.start_run(run_id=champion_run_id):
    log_wrapped_model(model, framework, dv, scaler)
```

This means each training function must return its run ID along with the model and metric.

---

## 5. Promotion gates

```python
MARGIN = 0.05
METRIC = "roc_auc"


def promote_if_better(candidate_run_id: str, model_name: str) -> bool:
    candidate = client.get_run(candidate_run_id).data.metrics[METRIC]
    version = _find_version_for_run(model_name, candidate_run_id)

    try:
        current = client.get_model_version_by_alias(model_name, PRODUCTION_ALIAS)
    except RestException:
        client.set_registered_model_alias(model_name, PRODUCTION_ALIAS, version)
        return True                                   # nothing to beat; bootstrap

    production = client.get_run(current.run_id).data.metrics[METRIC]

    if candidate > production * (1 - MARGIN):         # or + MARGIN for improvement-required
        client.set_registered_model_alias(model_name, PRODUCTION_ALIAS, version)
        return True
    return False
```

Five things to get right:

**The margin is the point.** A bare `>` promotes on any difference, including differences smaller
than run-to-run variance. Measure that variance — run training five times unchanged and look at the
spread — and set the margin above it.

**Direction depends on the metric.** `>` is right for `roc_auc`; for `log_loss` it silently promotes
the worse model. Either hardcode one metric or carry a `higher_is_better` flag.

**The empty-registry branch must return success**, or the pipeline can never bootstrap. But be honest
about the consequence: **if the registry is always empty — as it is on an ephemeral CI runner — this
branch always fires and the gate gates nothing.** See `antipatterns.md` §7.

**Ties do not promote.** Reasonable, but it means a change that alters the artifact without changing
the metric — an ONNX conversion, a dependency bump — can never self-promote. Move that alias by hand.

**A metric is a crude gate.** Better pipelines also check behaviour on known edge cases, per-segment
metrics (aggregate fine, one segment collapsed), inference latency, and artifact size.

---

## 6. Loading in serving code

```python
class ChurnPredictor:
    def __init__(self, threshold: float = settings.CHURN_THRESHOLD):
        self.threshold = threshold
        apply_env_credentials()                       # artifact store needs these, client-side
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)

        self.model_uri = f"models:/{settings.MODEL_NAME}@production"
        self.model = mlflow.pyfunc.load_model(self.model_uri)   # once, at startup

    def predict(self, X: dict) -> dict:
        df = pd.DataFrame([X])
        probability = float(self.model.predict(df)[0])
        return {
            "churn_probability": round(probability, 4),
            "churn": bool(probability >= self.threshold),
            "threshold": self.threshold,
        }
```

**Load at startup, never per request.** Reloading per request is the single most common performance
mistake in model serving.

**Let it fail loudly if the model is unavailable.** A container that will not start is obvious —
restart loops, alerts. A container that starts and returns 503 to everything looks alive to your
orchestrator while serving nothing.

**Expose which model is live.** A metadata endpoint returning name, URI, run ID, training time and
framework turns "which model answered this?" from a guess into a request. It is also how you prove a
swap worked.

**Set the tracking URI explicitly in every entry point.** It is process-global and defaults to a local
directory. A client that silently points at `./mlruns` reports "model not found" for a model that
plainly exists.

---

## 7. What breaks a registered model

Three failure modes worth knowing before they happen, all covered in `antipatterns.md`:

**Renaming or moving the wrapper's module.** Serialisation stores a *reference* to the module path,
not the class body. Rename the file and every existing version fails at load with
`ModuleNotFoundError`. The registry is coupled to your source layout.

**Changing the wrapper's code without re-registering.** The wrapper is pickled at log time. Editing
the file changes nothing about versions already registered — they run the old code. Adding a field to
`load_context` requires retraining to take effect.

**Dependency drift.** A pickled sklearn transformer may not load under a different sklearn. Frameworks
with a native format (a booster's JSON, ONNX) are more durable than pickle; prefer them for the model
half.
