# Anti-patterns

A review pass. Every entry is a failure that actually happened, with the tell and the fix.

Work down the list before declaring ML work done. Most of these fail **silently** — the system keeps
returning plausible numbers — which is why a checklist beats intuition.

## Contents

1. Training/serving skew
2. Data leakage
3. Path-based model loading
4. Serialisation coupled to your source layout
5. Module-level imports
6. Environment boundaries
7. Checks that cannot fail
8. Decisions made on noise
9. Config mutated by runs
10. Credentials and the client/server split
11. Tests that hang instead of skipping
12. Coverage that lies
13. Sweeps and reproducibility
14. Metrics that need probabilities
15. Artifact bloat

---

## 1. Training/serving skew

**The failure.** Training applies a transformation that serving omits, or applies differently.

**Why it is the worst one.** There is no error. The model returns confidently wrong predictions,
every offline metric looks fine, and it presents as "the model underperforms in production" — a
sentence that sends people to retrain rather than to the bug.

**Real instance.** A `StandardScaler` was added to the feature pipeline during training. The serving
class, written earlier, called `dv.transform()` directly without scaling. Predictions were wrong for
weeks and nothing complained.

**The tell.** Serving code that constructs features itself, rather than calling the same function
training used.

**The fix.** Bundle preprocessing with the model (`tracking-and-registry.md` §2). Serving should not
know how features are made. Import column lists and transform functions from one module — never
duplicate them.

---

## 2. Data leakage

**The failure.** A transformer fitted on the full dataset before splitting, so validation has seen
information from training.

**Why it is dangerous.** It *rewards* you. Metrics improve. Nothing looks wrong until production,
where the advantage does not exist.

**The tell.** `fit_transform` on anything before the split, or on validation/test data.

**The fix.** Fit on train only; `transform` everywhere else. And write the test:

```python
def test_scaler_fit_on_train_only(sample_df):
    train, val, test = split(sample_df)
    *_, scaler = featurize(train, val, test)
    np.testing.assert_allclose(scaler.mean_, train[NUMERICAL].mean().values, rtol=1e-6)
```

That test is worth more than any number of "accuracy is above 0.8" assertions.

**Related, at inference.** `fit_transform` on a single incoming row sets that row's value as the
mean, scaling it to exactly 0. Every request looks identical to the model.

---

## 3. Path-based model loading

**The failure.** Serving loads `model.pkl` from a path baked into the image.

**The cost.** Rollback requires a rebuild and redeploy — minutes during which a bad model keeps
serving. The image tag identifies a commit, not a model, so "which model produced this prediction?"
is unanswerable from the container.

**The fix.** Resolve from a registry by role: `models:/name@production`. Moving the alias and
restarting swaps the model with zero code changes.

**The test.** Move the alias, restart, confirm predictions changed. If that requires editing
anything, you do not have it yet.

**The honest trade-off.** The service now needs a reachable registry at startup and will not boot
without one. That is correct — failing loudly beats serving a stale model — but it is a real
operational dependency to state.

---

## 4. Serialisation coupled to your source layout

**The failure.** Renaming or moving the module containing a custom model wrapper breaks every
already-registered version:

```
ModuleNotFoundError: No module named 'prodml.ml_flow.ChurnModelWrapper'
```

**Why.** `log_model(python_model=MyWrapper())` serialises a **reference to the module path**, not the
class body. At load time it imports from that path. Rename the file and the path no longer exists.

**Real instance.** Renaming `ChurnModelWrapper.py` to `wrapper.py` — a tidy-up prompted by a linter —
invalidated all seventeen registered versions. It surfaced at load time, in the API, not at the
rename.

**The fix.** Recognise that **the registry is coupled to your source layout.** Renaming a wrapper
module is a breaking change requiring re-registration, not a refactor. Recovery: retrain, and move
the alias by hand if the gate declines to promote an identical-scoring model (see §8).

**The related trap.** The wrapper is pickled at log time. Editing the file changes nothing about
versions already registered — they run the old code. Adding a field to `load_context` requires
retraining to take effect.

---

## 5. Module-level imports

**The failure.** A top-level `import` forces every consumer of that module to install the library,
including ones that never call it.

**Two real instances, same root cause:**

A provenance helper did `from git import Repo` at module level. GitPython refuses to import without a
`git` binary on PATH, and a slim serving image has no reason to include one. Since the model module
imported the helper for a decorator, and the app imported the model, **the entire service died at
import** — on a function serving never calls.

A model factory imported `torch` at module level so one loader could use it. Every image needing that
module then installed PyTorch with bundled CUDA libraries — **a 12 GB orchestration image** for a
workload that never touches a GPU.

**The tell.** An import at the top of a module used by exactly one function.

**The fix.** Defer it:

```python
def _load_torch(path):
    import torch                      # only when this backend is actually dispatched to
    return TorchAdapter(torch.load(path, weights_only=False))
```

Now a service whose champion is a linear model needs no deep-learning framework at all.

**Where this bites hardest:** factories. A dispatch table over frameworks that imports all of them at
module level forces every deployment to install every backend.

---

## 6. Environment boundaries

**The failure.** `localhost` means a different machine depending on where the code runs.

| Running on | `localhost:5000` means |
|---|---|
| Your host shell | Your machine |
| Inside a container | **That container** |
| A CI runner | **The runner** |

**Real instances.** A service whose `.env` said `localhost:5000` could not reach the tracking server
from inside its own container and had shown unhealthy for weeks. An artifact upload failed because
the credentials were given to the *server* container while the upload happens from the *client*
process. A CI job hung for twenty minutes retrying against a server that does not exist on a runner.

**The fix.** Configuration by environment, overridden per context:

```yaml
  api:
    env_file: [../.env]                          # localhost values, for host use
    environment:                                 # override wins inside the network
      MLFLOW_TRACKING_URI: http://mlflow:5000
      S3_ENDPOINT_URL: http://minio:9000
```

**And fail fast when it is unreachable.** A socket check at startup turns a forty-frame timeout into
one clear line:

```python
def require_service(name: str, host: str, port: int) -> None:
    try:
        socket.create_connection((host, port), timeout=1).close()
    except OSError:
        raise SystemExit(f"{name} unreachable at {host}:{port}. Is the stack running?")
```

---

## 7. Checks that cannot fail

**The failure.** A gate that structurally always passes.

**The canonical case.** A quality gate compares a candidate against the current production model.
Run it where the registry is **ephemeral** — a CI runner that stands up a fresh, empty tracking
server each time — and it finds no baseline, takes its bootstrap branch, and returns success. Every
time. It looks like a working gate and gates nothing.

**Related instances.** A script that catches all exceptions and exits 0. A job made
`continue-on-error` during debugging and never reverted. A required check that a path filter skips —
**skipped is not passed.**

**Why it is the one to fear.** Every other failure is loud. This one is silent and can persist for
months.

**The fix.** Break it on purpose and confirm it goes red. Invert the margin, deploy a deliberately
bad model, force a lint error. Do it when you build the check and again whenever you change it.

**And if it genuinely cannot work in that environment, say so.** "The gate is implemented and exits
non-zero on regression, but cannot gate here because the registry is ephemeral; making it functional
requires a persistent registry" is a better artifact than a gate that appears to work.

---

## 8. Decisions made on noise

**The failure.** Promoting or rejecting a model on a difference smaller than run-to-run variance.

**Real instance.** A gate comparing with a bare `>` promoted on a `roc_auc` difference of 0.00023 and
declined on 0.00011 — two consecutive runs of the *same* model, differing only by solver
nondeterminism. Those are coin flips.

**The fix.** Measure the noise floor: run training five times unchanged and look at the spread. Set
the margin above it. If the margin you need is wider than the improvements you expect, the answer is
**more stable evaluation** — cross-validation, a larger test set — not a tighter threshold on a noisy
measurement.

**The tie case.** `>` means an identical score does not promote. Reasonable, but a change that alters
the artifact without changing the metric — a runtime conversion, a dependency bump — can never
self-promote. Move that alias deliberately.

**The metric direction.** `>` is right for `roc_auc` and wrong for `log_loss`, where it silently
promotes the worse model.

---

## 9. Config mutated by runs

**The failure.** A tuning run writes its best parameters back into the committed config file.

**Three things break.** Checking out a commit no longer reproduces its results. CI cannot do it — a
read-only checkout, and you would not want a bot pushing to the default branch. And a pipeline stage
that modifies its own declared dependency leaves the dependency graph permanently dirty.

**The fix.** Config files are inputs; results go to the tracking store. Search *ranges* are config.
Best params are a result. Promoting one to a default is a hand-written commit.

---

## 10. Credentials and the client/server split

**The failure.** Giving the artifact store's credentials only to the tracking server.

**Why it surprises people.** The tracking server receives params and metrics over HTTP, but the
**client process uploads artifacts directly** to the object store. Your training script needs those
credentials, not just the server.

**The tell.** `NoCredentialsError` or `EndpointConnectionError` deep inside a cloud SDK, during
`log_model` or `log_figure`, after params and metrics logged fine.

**The fix.** Push credentials into the process environment where the client library will find them,
from typed settings rather than scattered literals:

```python
def apply_env_credentials() -> None:
    s = get_settings()
    os.environ["AWS_ACCESS_KEY_ID"] = s.AWS_ACCESS_KEY_ID
    os.environ["AWS_SECRET_ACCESS_KEY"] = s.AWS_SECRET_ACCESS_KEY
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = s.S3_ENDPOINT_URL
```

Call it in every entry point that logs: training, batch jobs, serving, orchestrator tasks.

---

## 11. Tests that hang instead of skipping

**The failure.** A test whose fixture reaches a service that is not running. The client retries with
exponential backoff rather than failing fast, and the test stalls for minutes.

**Real instance.** Six tests calling a fixture that loads a model from the registry. On a CI runner
with no registry, the suite hit a **20-minute timeout** — seven retries each, with backoff.

**The fix.** A one-second raw socket check, not a library call, and a module-level skip marker:

```python
def _reachable(host="localhost", port=5000, timeout=1.0) -> bool:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


requires_registry = pytest.mark.skipif(
    not _reachable(), reason="registry unreachable; skipping tests that load a model"
)
```

```python
# at the top of the test module
pytestmark = requires_registry
```

The socket check matters: a client-library call would retry, which is the thing you are avoiding.

Job time went from 20 minutes to under 5.

---

## 12. Coverage that lies

**The failure.** A coverage number that implies the whole codebase is unit-tested when large parts
are not — or a threshold that cannot be met because infrastructure-dependent tests skip.

**The fix.** Exclude from *measurement* the code that is genuinely integration-tested rather than
unit-tested — training loops, sweep functions, model wrappers that only execute inside a loaded
model:

```toml
[tool.coverage.run]
omit = [
    "src/pkg/train.py",       # exercised by the pipeline, not unit tests
    "src/pkg/sweep.py",
    "src/pkg/wrapper.py",     # only runs inside a loaded model
]
```

**And state it.** "84%, with training code excluded as integration-tested by the pipeline" is honest.
An unqualified 84% is not.

Note the threshold must be reachable in the environment that enforces it. If six tests skip on CI,
the CI-reachable subset is what the threshold applies to.

---

## 13. Sweeps and reproducibility

**The failure.** An unseeded sampler, so repeated sweeps select different "best" parameters.

**The consequence.** Reported best params are one draw from a distribution, not a stable answer. Two
people running the same sweep get different configs and neither is wrong.

**The fix.** Seed the sampler if you need reproducibility, and say which you chose. "The sweep is not
reproducible run-to-run; the reported parameters are one draw" is a legitimate note.

**Related.** Every trial should be a nested run under a parent. Ten loose top-level runs per sweep
makes the tracking UI unusable within a week.

---

## 14. Metrics that need probabilities

**The failure.** Passing predicted labels to a metric that expects probabilities.

**Why it is silent.** `roc_auc_score` accepts labels without complaint and computes a degraded,
wrong-shaped curve. You get a number. It is not the number you think.

**The fix.** Be explicit about which is which:

```python
y_proba = model.predict_proba(X_val)[:, 1]          # ranking metrics
y_pred = (y_proba >= threshold).astype(int)         # threshold metrics
```

**The network case.** A model trained with a logits loss emits **logits**, unbounded in both
directions. Passing them to a probability metric raises (`y_prob contains values lower than 0`) —
loud, and easy to fix — but the subtler error is applying the activation before the loss, which
double-applies it and quietly corrupts training.

---

## 15. Artifact bloat

**The failure.** Shipping gigabytes you never use.

**Real instance.** An orchestration image at **12 GB**, almost all of it a deep-learning framework
with bundled GPU libraries, in a container that never touches a GPU. Every rebuild: 20+ minutes.

**Three fixes, in order of impact:**

- **Lazy imports** (§5) so the dependency is optional at all
- **CPU-only wheels** where the framework publishes them — often an order of magnitude smaller
- **Trim the dependency list** to what the image actually runs; a training image and a serving image
  need different things

**Related.** Stale model files committed to the repository and copied into images after the code
stopped reading them. Remove them — they are in Git history if ever needed — and remove the volume
mounts that reference them.
