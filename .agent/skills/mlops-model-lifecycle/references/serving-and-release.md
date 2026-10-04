# Serving and Release

Choosing a pattern, making it fast, proving it is fast, and changing it safely.

## Contents

1. Decide the pattern before the tool
2. The four-layer stack
3. Online serving
4. Batch scoring
5. Streaming
6. Accelerated runtimes
7. Load testing and bottleneck diagnosis
8. Release strategies

---

## 1. Decide the pattern before the tool

**Write this down before opening any documentation.** Every wrong serving architecture started with
someone choosing a tool before answering these.

### The three failure modes

**Cost blowout.** Scoring the entire customer base hourly through a web service, paying full
per-request overhead, to answer a question whose inputs change weekly. Most of those predictions are
identical to the last hour's.

**Latency SLA breach.** A human is waiting and a 3-second p99 is dead air in a live conversation.
They stop waiting, the feature goes unused, it gets switched off. The model was accurate and still
failed.

**Over-engineering.** A message queue, an inference server and a GPU node to score seven thousand
rows nightly — work a loop finishes in four seconds. Every component is another thing to operate,
monitor, and be paged about.

### The decision table

Fill this in for your own scenarios. The SLA column is what actually decides.

| Scenario | Pattern | SLA that drives it | Why not the others |
|---|---|---|---|
| A human waits for the answer | **Online** | p95 < 200 ms | Batch is stale; streaming adds queue latency for a synchronous request |
| Scheduled scoring of everything | **Batch** | Done by 06:00; per-row latency irrelevant | Online costs 50–100× for identical output |
| React to an event within seconds | **Streaming** | End-to-end < 5 s | Batch misses the window; online needs something to *ask*, and nothing does |

The third row is what justifies streaming's complexity: the trigger is an event nobody waits on
synchronously, but which goes stale within minutes.

### Vocabulary that carries weight

**Latency** is one request; **throughput** is requests per second. They trade against each other —
batching deliberately delays individuals to serve more per model call.

**p50 / p95 / p99** are percentiles, and the mean is close to useless here. With p50 at 40 ms and
p99 at 4 s, one request in a hundred takes 100× the median and the mean hides it entirely. At 1,000
rps, p99 is ten unhappy users every second. And a page making five API calls turns a 1% tail into
roughly one bad page load in twenty.

**The gap between p95 and p99 describes the shape.** Close together means consistent. Far apart means
something occasional is very slow — a pause, a cold cache, lock contention. A flat 400 ms is often a
better system than p95=200 ms with p99=4 s.

**Cold start** is the first-request penalty after a process starts: loading the model, downloading
artifacts, initialising the runtime.

---

## 2. The four-layer stack

```
┌──────────────────────────────────────────────────────────┐
│  4. DEPLOYMENT   proxy, weights, canary, rollback        │
├──────────────────────────────────────────────────────────┤
│  3. SERVING      request lifecycle, batching, workers    │
├──────────────────────────────────────────────────────────┤
│  2. RUNTIME      eager / ONNX / OpenVINO / TensorRT      │
├──────────────────────────────────────────────────────────┤
│  1. MODEL        the weights, plus the preprocessing     │
└──────────────────────────────────────────────────────────┘
```

The value is independence: swapping the runtime should not touch the serving layer; shifting canary
weights should not touch the model. **A factory at layer 1 (see `tracking-and-registry.md` §3) is
what buys that independence** — the serving layer never learns which framework won.

---

## 3. Online serving

### The four problems with a plain web framework

Each is measurable. Do not assert them.

| Problem | How to prove it |
|---|---|
| Batch size is always 1 | Time N single requests vs one batch of N |
| The interpreter lock serialises work | Watch CPU under load — plateau well below `100% × cores` while latency climbs |
| Eager runtime | Compare against an accelerated runtime (§6) |
| The model is welded to the image | A written answer: what does rollback cost? |

A representative result from a small tabular model: **100 single requests took 1.34 s; the same 100
as one batch took 0.019 s.** Roughly 70×. Be honest about what is in that gap — client process
startup, HTTP round trips, validation, DataFrame construction, and only then the model. Attributing
all of it to inference overstates the case.

### Adaptive micro-batching

The batch win above is unavailable to online serving, because requests come from *different users at
different moments*. No client can batch them. Only the server can, by holding each request briefly
and combining:

```
t=0ms    A arrives  → held
t=3ms    B arrives  → held
t=20ms   window closes → run([A, B]) as one call → split, reply to each
```

Every client made an ordinary single request and got an ordinary single response.

**The two dials:**

- **`max_latency_ms`** — how long a request waits for company. Raise it → bigger batches → better
  throughput, **worse p50**. You are deliberately slowing every request so more fit per call.
- **`max_batch_size`** — the cap. Only binds under load.

**The asymmetry is why it is nearly free.** Idle: requests go out alone, costing nothing. Busy:
batches fill and throughput climbs. It costs least when you are quiet and helps most when you are
not.

Pick `max_latency_ms` from your SLA. If p95 must stay under 200 ms and inference takes 10 ms, 20 ms
buys most of the benefit for 10% of budget.

**Measure both ways** — batching off, then on. That delta is the evidence, and it isolates batching
from everything else that changed.

### Worker processes

A serving framework runs your model in worker processes separate from HTTP handling, which is the
direct answer to the interpreter-lock measurement. More workers, more parallel execution.

The cost is memory: **each worker loads its own copy of the model.** For a small model, irrelevant.
For a large one, this is the constraint that sets your worker count.

### The batchable-signature trap

Enabling batching usually requires declaring it in **two** places — on the saved model's signature
*and* on the serving endpoint. Miss one and batching silently does not happen: no error, no warning,
and the headline feature of your serving layer is inert.

And note what it changes: a batched method receives **many rows**, not one. Write it that way; the
framework handles the one-row case as a batch of one. This interacts awkwardly with per-item schema
validation — a batched endpoint often has to drop to arrays and lose it. That trade is worth stating
rather than discovering.

---

## 4. Batch scoring

Read a partition, score in chunks, write partitioned output.

```python
CHUNK = 50_000

for start in range(0, len(df), CHUNK):
    chunk = df.iloc[start:start + CHUNK]
    results.append(model.predict(chunk))
```

Record wall clock, peak memory, and **cost per million predictions**. Then compare against the same
volume through the web service. The gap is typically 50–100×, and naming where it comes from is worth
more than the number: no per-request HTTP overhead, no idle capacity provisioned for peak, and
vectorised scoring over fifty thousand rows instead of one.

If your dataset is too small to benchmark, duplicate it — you are measuring machine throughput, not
prediction quality. **Say so in the write-up.**

---

## 5. Streaming

The properties that make streaming hard are not "reading from a queue" — they are delivery
guarantees.

**Consumer groups** distribute partitions across consumers for parallelism.

**Acknowledge after success, never before.** Ack first and a crash between read and completion
silently drops the event (at-most-once). Ack after and a crash leaves the message pending for another
consumer to claim (at-least-once).

**At-least-once means duplicates.** The consumer must be idempotent, or downstream must deduplicate
on a source ID.

**A dead-letter path** for poison messages — an event that crashes the consumer every time is
retried forever and blocks the group. Find messages delivered more than N times, move them aside,
acknowledge the original.

**Measure end-to-end latency** — event produced to prediction published — not model latency. That
interval includes queue wait, poll interval, preprocessing and inference, and it is the number a
user experiences.

**Choosing the broker:** a lightweight in-memory stream is simpler to operate and fine to tens of
thousands of events per second. A durable log adds replay from arbitrary offsets, partition-level
ordering, and a much larger operational surface. For modest volume, the lightweight option is right
and the heavy one is the over-engineering failure mode.

---

## 6. Accelerated runtimes

Converting to ONNX, OpenVINO, TensorRT, or a quantised format. Two deliverables, both mandatory.

### Accuracy delta

Score the same held-out set through both runtimes and report the difference. It should be
approximately 1e-6. Anything larger means the conversion is wrong, and it is easy to miss because a
subtly broken conversion still returns plausible numbers.

### Throughput delta, honestly

**Accelerated runtimes are not free wins.** A real measured result:

| Runtime | roc_auc | Throughput |
|---|---|---|
| Eager sklearn | 0.859365 | 25,218 rows/sec |
| ONNX Runtime | 0.859365 | **16,665 rows/sec** |

Identical accuracy, **34% slower**. The reason is structural: logistic regression is a single matrix
multiply, so a graph optimiser has nothing to fuse — no chains to collapse, no redundant nodes. What
the measurement captures is the runtime's per-call marshalling overhead against a thin wrapper over a
BLAS call on data already in memory.

**Graph optimisation pays off on deep networks with many fusable operations. On a one-node graph it
is pure overhead.** Report the regression; it is a more interesting finding than a win, and it is
principle 4 in action.

### Conversion notes

**Export with a dynamic batch axis.** Freeze it to 1 and you have defeated every batching feature
downstream.

**Inspect the raw output before trusting it.** Converted classifiers commonly emit a *list* —
`[labels, probabilities]`, with probabilities as `(N, 2)` — rather than a single array. Print shapes
once; assuming here is where an hour disappears.

**Append the output activation if the eager model omitted it.** A network trained with a logits loss
emits logits. Fold the sigmoid into the exported graph so every consumer does not have to remember.

---

## 7. Load testing and bottleneck diagnosis

### The payload must be realistic

Randomise every field, and respect correlations between them. A record with two months of tenure and
$8,000 in lifetime charges is an impossible customer, and if anything caches or short-circuits on
implausible input your numbers are fiction.

Sending the same row ten thousand times measures your cache, not your model.

Mix the traffic — mostly single predictions, some batch, a few cheap reads. And use a **wait time**
between requests; without one each virtual user hammers in a tight loop, which measures how hard your
machine can flood the server rather than how the server behaves.

### Compare like with like

**Two runs at different user counts are not a comparison.** A stack tested at 1,000 users showing
p50 = 400 ms is not slower than one tested at 50 users showing p50 = 8 ms — they were asked different
questions.

Run both ways, deliberately:

- **Matched load** — same users, same wait times. Isolates the stack.
- **Matched stress** — push both to their limit. Shows what each absorbs before degrading, and this
  is often the more useful result. "A held 419 rps with zero failures where B failed every request"
  is a stronger finding than any latency table.

### Diagnose with evidence

Watch CPU, memory and device utilisation **during** the run. It is gone afterwards.

| Observation | Diagnosis |
|---|---|
| CPU near `100% × cores`, latency climbing | CPU-bound |
| CPU far below capacity, latency climbing | Interpreter lock, or I/O — check whether requests queue |
| Memory climbing to OOM | Memory-bound |
| Latency improves when batch size rises | Batching-bound |
| Device idle while requests queue | Insufficient device concurrency |

A concrete example: **82% CPU on a 12-core machine** — roughly 7% of 1200% available, one core at
77% while eleven sat near idle. That is the interpreter lock serialising bytecode, and it is
unusually clean when per-request cost is dominated by Python-level work (validation, DataFrame
construction) rather than the model call itself.

Which is its own finding: **the model was not the bottleneck; the Python around it was.**

**Report what you observe, including when it contradicts theory.** Numerical libraries release the
lock during C-level work, so the effect is often muddier. "CPU reached 340% of 400%, so the lock was
not the binding constraint" is a better finding than repeating the expected answer.

**Then change exactly one parameter** based on the diagnosis and re-measure. Changing three and
reporting an improvement teaches you nothing about which mattered.

### The saturation point

Where p95 stops rising linearly and turns sharply upward. That knee is where queueing begins, and it
is the number that tells you your actual headroom.

---

## 8. Release strategies

| Strategy | Traffic mechanics | Risk reduced | Cost |
|---|---|---|---|
| **Blue/Green** | 100% switch between two identical environments | Deploy failure; instant rollback | 2× infrastructure |
| **Canary** | Small weighted %, ramped | Gradual blast radius | ~1.1× |
| **A/B test** | Split by user attribute, held for a period | Business-metric risk | 2× + analytics |
| **Shadow** | Mirrored traffic, response discarded | **Correctness**, zero exposure | 2× compute, no user risk |

### Shadow mode is the one for model changes

A canary exposes real users to the new model's predictions. If the model is not slow, not erroring,
just **wrong**, every latency and error metric looks fine while 10% of users get bad answers.

Shadow mode runs production traffic through the candidate and **discards the response**. Users always
get the stable answer. You compare predictions offline. It is the only strategy that validates
*correctness* rather than availability, and it is therefore the right default for a model change as
opposed to a code change.

Note that mirroring a POST body often requires explicit configuration — mirror the request without
the body and your shadow receives nothing useful.

### Traffic must be attributable

Tag responses with the serving version, in a header or the body. Without it you cannot tell which
version answered, and the canary is unmeasurable. In the body is better; it survives proxies and
logging.

### Automatic rollback

```python
breaches = 0
while True:
    p95, error_rate = measure_canary()
    if p95 > SLA_P95_MS or error_rate > ERROR_THRESHOLD:
        breaches += 1
        if breaches >= CONSECUTIVE_BREACHES:
            rollback()
            break
    else:
        breaches = 0          # ← the important line
    time.sleep(INTERVAL)
```

**The reset on success is what makes it usable.** Without it, two breaches an hour apart trigger a
rollback and you are rolled back by unrelated noise. "Consecutive" means the counter resets the
moment things look healthy.

**Time the rollback and report the number in seconds.** A graceful proxy reload finishes in-flight
requests on the old config while new ones use the new one, so the number should be small — and
knowing it is the difference between a rollback plan and a rollback hope.

**Trigger it deliberately.** Deploy a candidate with an artificial delay, watch the guard fire, then
restore. A rollback that has never been exercised is a hypothesis.
