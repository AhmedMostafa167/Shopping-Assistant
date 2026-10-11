"""Run the agent behaviour tasks through the real chat path and score them.

    PYTHONPATH=src:eval uv run python eval/eval_agent.py --label baseline

Each task runs with a fresh test user that is deleted afterwards. Every run is a trace
in Langfuse with its check results attached as scores (the SDK files experiment traces
under the environment "sdk-experiment", apart from development traffic), and the
summary is also logged to MLflow. Finished runs are saved locally, so an interrupted
evaluation continues where it stopped.
"""
import argparse
import asyncio
import concurrent.futures
import contextvars
import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from langfuse import Evaluation  # noqa: E402
from sqlalchemy import text as sql_text  # noqa: E402

from agent.prompts import SYSTEM_PROMPT_NAME, warm_prompt_cache  # noqa: E402
from agent_checks import compare, run_checks, summarize  # noqa: E402
from helpers.config import get_settings  # noqa: E402
from main import app, lifespan  # noqa: E402
from routes.chat import chat  # noqa: E402
from routes.schemas.Chat import ChatRequest  # noqa: E402

TASKS_FILE = Path(__file__).parent / "agent_tasks.json"
EXPERIMENT_NAME = "agent-behaviour"
TEST_USER_PREFIX = "eval-"
# Langfuse drops run metadata values longer than this.
MAX_DESCRIPTION_LENGTH = 200
# Two failed conversations in a row mean something systemic (most likely the generation
# model's daily token limit); stop instead of failing through the rest of the tasks.
MAX_CONSECUTIVE_FAILURES = 2


class EvaluationStopped(RuntimeError):
    """Raised for the remaining tasks once the evaluation has given up."""

DELETE_TEST_USER_SQL = [
    "DELETE FROM checkpoint_writes WHERE thread_id IN (SELECT c.thread_id::text FROM conversations c JOIN profiles p USING (profile_id) WHERE p.username = :username)",
    "DELETE FROM checkpoint_blobs WHERE thread_id IN (SELECT c.thread_id::text FROM conversations c JOIN profiles p USING (profile_id) WHERE p.username = :username)",
    "DELETE FROM checkpoints WHERE thread_id IN (SELECT c.thread_id::text FROM conversations c JOIN profiles p USING (profile_id) WHERE p.username = :username)",
    "DELETE FROM memories WHERE profile_id IN (SELECT profile_id FROM profiles WHERE username = :username)",
    "DELETE FROM conversations WHERE profile_id IN (SELECT profile_id FROM profiles WHERE username = :username)",
    "DELETE FROM profiles WHERE username = :username",
]


class AppRunner:
    """Keeps the application running on its own event loop thread.

    Langfuse's experiment runner drives tasks from its own loop, while the application's
    database connections belong to the loop they were opened on. Tasks therefore hand
    their work to this loop, carrying the caller's context so traces stay nested.
    """

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self._stop = None
        self._serving = None

    def start(self) -> None:
        started = threading.Event()
        failure = []

        async def serve():
            self._stop = asyncio.Event()
            try:
                async with lifespan(app):
                    started.set()
                    await self._stop.wait()
            except BaseException as error:  # surface startup failures to the caller
                failure.append(error)
                started.set()
                raise

        self._serving = asyncio.run_coroutine_threadsafe(serve(), self.loop)
        started.wait()
        if failure:
            raise failure[0]

    def run(self, make_coroutine):
        """Run a coroutine on the application loop and wait for its result."""
        context = contextvars.copy_context()
        result = concurrent.futures.Future()

        def schedule():
            task = self.loop.create_task(make_coroutine(), context=context)

            def finished(done):
                if done.cancelled():
                    result.cancel()
                elif done.exception():
                    result.set_exception(done.exception())
                else:
                    result.set_result(done.result())

            task.add_done_callback(finished)

        self.loop.call_soon_threadsafe(schedule)
        return result.result()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self._stop.set)
        self._serving.result()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()


async def delete_test_user(username: str) -> None:
    async with app.db_client() as session, session.begin():
        for statement in DELETE_TEST_USER_SQL:
            await session.execute(sql_text(statement), {"username": username})


async def conversation_tool_calls(thread_id: str) -> list[dict]:
    """Every tool call of the conversation, in order, with its arguments and result."""
    state = await app.graph.aget_state({"configurable": {"thread_id": thread_id}})
    outputs = {
        message.tool_call_id: message.content
        for message in state.values.get("messages", [])
        if message.type == "tool"
    }
    return [
        {"name": call["name"], "args": call["args"], "output": str(outputs.get(call["id"], ""))}
        for message in state.values.get("messages", [])
        if message.type == "ai"
        for call in (message.tool_calls or [])
    ]


async def run_task(task: dict, turn_pause: float) -> dict:
    """One conversation with a fresh user; returns what the checks need."""
    username = f"{TEST_USER_PREFIX}{task['id']}-{uuid.uuid4().hex[:8]}"
    request = SimpleNamespace(app=app)
    try:
        profile = await app.profile_model.get_profile_or_create_one(username)
        for fact in task.get("seed_memory", []):
            await app.memory_controller.add_fact(
                username=username, fact_type=fact["fact_type"], content=fact["content"], confidence=0.9
            )
        conversation = await app.conversation_model.create_conversation(
            profile_id=profile.profile_id, title=f"eval {task['id']}"
        )

        replies, started = [], time.perf_counter()
        for index, message in enumerate(task["turns"]):
            if index:
                await asyncio.sleep(turn_pause)
            response = await chat(request, ChatRequest(
                username=username, conversation_id=conversation.conversation_uuid, message=message,
            ))
            replies.append(response.response)

        facts = await app.memory_controller.read_facts(username)
        return {
            "user_messages": task["turns"],
            "replies": replies,
            "tool_calls": await conversation_tool_calls(str(conversation.thread_id)),
            "seed_memory": task.get("seed_memory", []),
            "memory_after": [{"fact_type": f.fact_type, "content": f.content} for f in facts],
            "latency_s": time.perf_counter() - started - turn_pause * (len(task["turns"]) - 1),
        }
    finally:
        await delete_test_user(username)


def saved_summary(records_dir: Path, tasks: dict) -> dict:
    """Score an earlier evaluation again from its saved runs, with the current checks."""
    results: dict[str, list[dict]] = {}
    for path in sorted(records_dir.glob("*__trial-*.json")):
        task_id = path.stem.split("__trial-")[0]
        if task_id in tasks:
            results.setdefault(task_id, []).append(
                run_checks(json.loads(path.read_text()), tasks[task_id]["expect"])
            )
    return summarize(results)


def sync_dataset(langfuse, spec: dict) -> None:
    """Make the Langfuse dataset match the tasks file (stable ids, so re-running updates)."""
    langfuse.create_dataset(name=spec["dataset"], description=spec["description"])
    for task in spec["tasks"]:
        langfuse.create_dataset_item(
            dataset_name=spec["dataset"],
            id=f"agent-task-{task['id']}",
            input={"turns": task["turns"], "seed_memory": task.get("seed_memory", [])},
            expected_output=task["expect"],
            metadata={"task_id": task["id"], "capability": task["capability"],
                      "uses_search": task["uses_search"]},
        )


def record_path(records_dir: Path, task_id: str, trial: int) -> Path:
    return records_dir / f"{task_id}__trial-{trial}.json"


def make_task(runner: AppRunner, tasks: dict, records_dir: Path, trial: int, args, pace: dict):
    def task(*, item, **kwargs):
        spec = tasks[item.metadata["task_id"]]

        if pace["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            raise EvaluationStopped("skipped after repeated failures; re-run to resume")

        # One conversation at a time, spaced out for the generation model's rate limit.
        wait = pace["next_start"] - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            record = runner.run(lambda: run_task(spec, args.turn_pause))
        except Exception:
            pace["consecutive_failures"] += 1
            raise
        finally:
            pace["next_start"] = time.monotonic() + args.turn_pause
        pace["consecutive_failures"] = 0
        record_path(records_dir, spec["id"], trial).write_text(json.dumps(record, indent=2))
        return record

    return task


def evaluate(*, input, output, expected_output, metadata, **kwargs):
    return [
        Evaluation(name=name, value=passed, data_type="BOOLEAN")
        for name, passed in run_checks(output, expected_output).items()
    ]


def log_to_mlflow(args, summary: dict, prompt_version) -> None:
    import mlflow

    settings = get_settings()
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
    mlflow.set_experiment(EXPERIMENT_NAME)
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        git_commit = "unknown"
    with mlflow.start_run(run_name=args.label):
        mlflow.set_tag("git_commit", git_commit)
        mlflow.set_tag("langfuse_experiment", EXPERIMENT_NAME)
        mlflow.set_tag("langfuse_run_names", f"{args.label}-trial-1..{args.trials}")
        mlflow.set_tag("description", args.description)
        mlflow.set_tag("compared_to", args.compare_to or "none")
        mlflow.log_params({
            "label": args.label,
            "trials": args.trials,
            "tasks": summary["tasks"],
            "generation_model": settings.GENERATION_MODEL,
            "system_prompt": f"{SYSTEM_PROMPT_NAME} v{prompt_version}",
            "prompt_label": args.prompt_label,
        })
        metrics = {
            "tasks_reliably_passed": summary["tasks_reliably_passed"],
            "trial_pass_rate": summary["trial_pass_rate"],
        }
        metrics.update({f"check_{name}": result["rate"] for name, result in summary["per_check"].items()})
        mlflow.log_metrics(metrics)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--label", required=True, help="Name of this evaluation, e.g. baseline")
    parser.add_argument("--description", required=True,
                        help="What this run changes or measures; stored with the run")
    parser.add_argument("--compare-to", help="Label of an earlier evaluation to compare against")
    parser.add_argument("--prompt-label", default="production",
                        help="Which prompt versions to evaluate, e.g. staging for a candidate")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--tasks", help="Comma-separated task ids (default: all)")
    parser.add_argument("--turn-pause", type=float, default=65.0,
                        help="Seconds between conversations, for the model's tokens-per-minute limit")
    parser.add_argument("--output-dir", default="eval_outputs")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()
    if len(args.description) > MAX_DESCRIPTION_LENGTH:
        parser.error(f"--description must be at most {MAX_DESCRIPTION_LENGTH} characters")

    # The application reads this setting when it starts, below.
    os.environ["LANGFUSE_PROMPT_LABEL"] = args.prompt_label
    settings = get_settings()
    if not (settings.langfuse_configured and settings.LANGFUSE_TRACING_ENABLED):
        raise SystemExit("Langfuse keys and LANGFUSE_TRACING_ENABLED=true are required.")

    spec = json.loads(TASKS_FILE.read_text())
    tasks = {task["id"]: task for task in spec["tasks"]}
    selected = set(args.tasks.split(",")) if args.tasks else set(tasks)
    unknown = selected - set(tasks)
    if unknown:
        raise SystemExit(f"Unknown task ids: {sorted(unknown)}")

    records_dir = Path(args.output_dir) / f"agent__{args.label}"
    records_dir.mkdir(parents=True, exist_ok=True)

    runner = AppRunner()
    runner.start()
    try:
        langfuse = app.langfuse
        prompt_version = warm_prompt_cache(langfuse, args.prompt_label).get(SYSTEM_PROMPT_NAME)
        sync_dataset(langfuse, spec)
        items = [item for item in langfuse.get_dataset(spec["dataset"]).items
                 if item.metadata["task_id"] in selected]

        pace = {"next_start": 0.0, "consecutive_failures": 0}
        trial_results: dict[str, list[dict]] = {task_id: [] for task_id in sorted(selected)}
        for trial in range(1, args.trials + 1):
            # Runs saved by an earlier, interrupted evaluation are scored from disk and
            # not sent to Langfuse again, where they are already recorded.
            pending = []
            for item in items:
                task_id = item.metadata["task_id"]
                saved = record_path(records_dir, task_id, trial)
                if saved.exists():
                    trial_results[task_id].append(
                        run_checks(json.loads(saved.read_text()), tasks[task_id]["expect"])
                    )
                else:
                    pending.append(item)
            if not pending:
                continue
            result = langfuse.run_experiment(
                name=EXPERIMENT_NAME,
                run_name=f"{args.label}-trial-{trial}",
                description=args.description,
                data=pending,
                task=make_task(runner, tasks, records_dir, trial, args, pace),
                evaluators=[evaluate],
                max_concurrency=1,
                metadata={"label": args.label, "trial": trial,
                          "description": args.description,
                          "compared_to": args.compare_to or "none",
                          "prompt_label": args.prompt_label,
                          "system_prompt_version": prompt_version,
                          "generation_model": settings.GENERATION_MODEL},
            )
            for item_result in result.item_results:
                if item_result.output is None:
                    continue  # the run failed; it is not saved, so a re-run retries it
                task_id = item_result.item.metadata["task_id"]
                trial_results[task_id].append(
                    run_checks(item_result.output, tasks[task_id]["expect"])
                )
        langfuse.flush()
    finally:
        runner.stop()

    summary = summarize(trial_results)
    expected_runs = len(selected) * args.trials
    completed_runs = sum(result["trials"] for result in summary["per_task"].values())
    summary["runs_completed"], summary["runs_expected"] = completed_runs, expected_runs
    if completed_runs < expected_runs:
        # An incomplete evaluation is not logged as a result; saved runs are kept.
        (records_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        raise SystemExit(
            f"Incomplete: {completed_runs} of {expected_runs} runs finished. "
            "Run the same command again to resume."
        )
    summary.update({"label": args.label, "trials_requested": args.trials,
                    "description": args.description, "prompt_label": args.prompt_label,
                    "system_prompt_version": prompt_version})
    (records_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    if not args.no_mlflow:
        log_to_mlflow(args, summary, prompt_version)

    print(f"label={args.label} prompt={SYSTEM_PROMPT_NAME} v{prompt_version} "
          f"tasks={summary['tasks']} trials={args.trials}")
    print(f"  tasks passing every trial: {summary['tasks_reliably_passed']}/{summary['tasks']}"
          f" | runs passing all checks: {summary['trial_pass_rate']:.0%}")
    for name, result in summary["per_check"].items():
        print(f"  {name}: {result['passed']}/{result['total']} ({result['rate']:.0%})")
    for task_id, result in summary["per_task"].items():
        print(f"  task {task_id}: {result['passed']}/{result['trials']} runs passed")

    if args.compare_to:
        before = saved_summary(Path(args.output_dir) / f"agent__{args.compare_to}", tasks)
        print(f"compared to {args.compare_to} (re-scored with the current checks):")
        print(f"  tasks passing every trial: {before['tasks_reliably_passed']} -> "
              f"{summary['tasks_reliably_passed']} of {summary['tasks']}")
        for row in compare(before, summary):
            print(f"  {row['check']}: {row['before']['passed']}/{row['before']['total']} -> "
                  f"{row['after']['passed']}/{row['after']['total']}")
        for task_id in sorted(tasks):
            was, now = before["per_task"].get(task_id), summary["per_task"].get(task_id)
            if was and now and was["passed"] != now["passed"]:
                print(f"  task {task_id}: {was['passed']}/{was['trials']} -> {now['passed']}/{now['trials']}")


if __name__ == "__main__":
    main()
