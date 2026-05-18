import asyncio
import base64
import json
from pathlib import Path

from app.core.batch_engine import BatchEngine
from app.core.config import AppConfig
from app.core.errors import ImageBatchError
from app.core.manifest_store import ManifestStore
from app.core.models import InputImage, JobLayout, OutputPlan, PlannedJob, PreflightIssue, TaskPlan
from app.core.openai_image_client import CompletedImage, PartialImage


PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def _job(tmp_path: Path, tasks: list[TaskPlan]) -> PlannedJob:
    root = tmp_path / "job"
    layout = JobLayout(
        job_id="job-1",
        root=root,
        final_dir=root / "final",
        partials_dir=root / "partials",
        logs_dir=root / "logs",
        app_log_path=root / "logs" / "app.log",
        events_jsonl_path=root / "logs" / "events.jsonl",
        errors_jsonl_path=root / "logs" / "errors.jsonl",
        failed_dir=root / "failed",
        thumbnails_dir=root / "thumbs",
        manifest_path=root / "manifest.jsonl",
        summary_path=root / "summary.json",
        config_snapshot_path=root / "config.json",
        command_path=root / "command.ps1",
    )
    return PlannedJob(job=layout, tasks=tasks, issues=[])


def _task(tmp_path: Path, task_id: str, *, status="queued") -> TaskPlan:
    return TaskPlan(
        task_id=task_id,
        mode="generate",
        rendered_prompt=f"prompt {task_id}",
        output_plan=OutputPlan(
            final_path=tmp_path / "job" / "final" / f"{task_id}.png",
            partials_dir=tmp_path / "job" / "partials" / task_id,
            failed_dir=tmp_path / "job" / "failed",
            thumbnails_dir=tmp_path / "job" / "thumbs",
        ),
        status=status,
    )


class SequencedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def run_task(self, task):
        self.calls.append(task.task_id)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MeasuringClient:
    def __init__(self):
        self.running = 0
        self.max_running = 0

    async def run_task(self, task):
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        await asyncio.sleep(0.02)
        self.running -= 1
        return [CompletedImage(b64_json=PNG_B64)]


def test_batch_engine_writes_success_manifest_events_summary_and_output(tmp_path):
    task = _task(tmp_path, "task-1")
    events = []
    client = SequencedClient([[CompletedImage(b64_json=PNG_B64, usage={"total_tokens": 3})]])

    summary = asyncio.run(
        BatchEngine(
            AppConfig(prompt={"template": "prompt"}),
            _job(tmp_path, [task]),
            client,
            event_sink=events.append,
        ).run()
    )

    assert summary["succeeded"] == 1
    assert task.output_plan.final_path.exists()
    assert base64.b64encode(task.output_plan.final_path.read_bytes()).decode("ascii") == PNG_B64
    latest = ManifestStore(tmp_path / "job" / "manifest.jsonl").load_latest_by_task()
    assert latest["task-1"]["status"] == "succeeded"
    assert latest["task-1"]["usage"] == {"total_tokens": 3}
    assert json.loads((tmp_path / "job" / "summary.json").read_text())["succeeded"] == 1
    assert any(json.loads(line)["event"] == "task_succeeded" for line in events)


def test_batch_engine_saves_streaming_partials_but_only_completed_succeeds(tmp_path):
    task = _task(tmp_path, "task-1")
    client = SequencedClient(
        [[PartialImage(index=0, b64_json=PNG_B64), PartialImage(index=1, b64_json=PNG_B64), CompletedImage(b64_json=PNG_B64)]]
    )
    events = []

    summary = asyncio.run(
        BatchEngine(
            AppConfig(prompt={"template": "prompt"}, image={"stream": True, "partial_images": 2, "save_partials": True}),
            _job(tmp_path, [task]),
            client,
            event_sink=events.append,
        ).run()
    )

    assert summary["succeeded"] == 1
    assert (tmp_path / "job" / "partials" / "task-1" / "partial_0.png").exists()
    assert (tmp_path / "job" / "partials" / "task-1" / "partial_1.png").exists()
    assert [json.loads(line)["event"] for line in events].count("partial_saved") == 2


def test_batch_engine_does_not_save_partials_when_disabled(tmp_path):
    task = _task(tmp_path, "task-1")
    client = SequencedClient(
        [[PartialImage(index=0, b64_json=PNG_B64), CompletedImage(b64_json=PNG_B64)]]
    )
    events = []

    summary = asyncio.run(
        BatchEngine(
            AppConfig(
                prompt={"template": "prompt"},
                image={"stream": True, "partial_images": 1, "save_partials": False},
            ),
            _job(tmp_path, [task]),
            client,
            event_sink=events.append,
        ).run()
    )

    assert summary["succeeded"] == 1
    assert not (tmp_path / "job" / "partials" / "task-1" / "partial_0.png").exists()
    assert "partial_saved" not in [json.loads(line)["event"] for line in events]


def test_batch_engine_retries_rate_limit_and_succeeds(tmp_path):
    task = _task(tmp_path, "task-1")
    events = []
    client = SequencedClient(
        [
            ImageBatchError("rate_limit", "slow down", retryable=True),
            [CompletedImage(b64_json=PNG_B64)],
        ]
    )

    summary = asyncio.run(
        BatchEngine(
            AppConfig(prompt={"template": "prompt"}, execution={"max_retries": 1}),
            _job(tmp_path, [task]),
            client,
            event_sink=events.append,
            retry_backoff_seconds=0,
        ).run()
    )

    assert summary["succeeded"] == 1
    assert client.calls == ["task-1", "task-1"]
    records = ManifestStore(tmp_path / "job" / "manifest.jsonl").load_records()
    retry_records = [record for record in records if record.get("error_code") == "rate_limit"]
    assert retry_records == [
        {
            "attempt": 1,
            "error_code": "rate_limit",
            "message": "retry scheduled: slow down",
            "status": "failed",
            "task_id": "task-1",
        }
    ]
    failed_events = [json.loads(line) for line in events if json.loads(line)["event"] == "task_failed"]
    assert failed_events[0]["attempt"] == 1
    assert failed_events[0]["message"] == "retry scheduled: slow down"


def test_batch_engine_does_not_retry_content_policy_failure(tmp_path):
    task = _task(tmp_path, "task-1")
    client = SequencedClient([ImageBatchError("content_policy", "blocked", retryable=False)])

    summary = asyncio.run(
        BatchEngine(
            AppConfig(prompt={"template": "prompt"}, execution={"max_retries": 3}),
            _job(tmp_path, [task]),
            client,
            retry_backoff_seconds=0,
        ).run()
    )

    assert summary["failed"] == 1
    assert client.calls == ["task-1"]
    latest = ManifestStore(tmp_path / "job" / "manifest.jsonl").load_latest_by_task()
    assert latest["task-1"]["error_code"] == "content_policy"


def test_batch_engine_records_write_failure_as_failed_task(tmp_path):
    task = _task(tmp_path, "task-1")
    client = SequencedClient([[CompletedImage(b64_json=PNG_B64)]])

    class FailingWriter:
        def write_final(self, task, b64_json):
            raise ImageBatchError("write_error", "disk unavailable", retryable=False)

        def write_partial(self, task, b64_json, *, partial_index, output_format):
            raise AssertionError("no partial expected")

    summary = asyncio.run(
        BatchEngine(
            AppConfig(prompt={"template": "prompt"}),
            _job(tmp_path, [task]),
            client,
            writer=FailingWriter(),
            retry_backoff_seconds=0,
        ).run()
    )

    assert summary["failed"] == 1
    latest = ManifestStore(tmp_path / "job" / "manifest.jsonl").load_latest_by_task()
    assert latest["task-1"]["error_code"] == "write_error"


def test_batch_engine_rejects_output_paths_outside_job_root(tmp_path):
    task = _task(tmp_path, "task-1")
    task.output_plan.final_path = tmp_path / "outside.png"
    client = SequencedClient([[CompletedImage(b64_json=PNG_B64)]])

    summary = asyncio.run(
        BatchEngine(AppConfig(prompt={"template": "prompt"}), _job(tmp_path, [task]), client).run()
    )

    assert summary["failed"] == 1
    latest = ManifestStore(tmp_path / "job" / "manifest.jsonl").load_latest_by_task()
    assert latest["task-1"]["error_code"] == "write_error"


def test_batch_engine_records_validation_failed_without_api_call(tmp_path):
    task = _task(tmp_path, "task-1", status="validation_failed")
    task.input_image = InputImage(
        path=tmp_path / "input.png",
        width=32,
        height=32,
        format="png",
        validation_status="validation_failed",
        issues=[PreflightIssue(code="bad_mask", message="mask dimensions differ")],
    )
    client = SequencedClient([])
    events = []

    summary = asyncio.run(
        BatchEngine(
            AppConfig(prompt={"template": "prompt"}),
            _job(tmp_path, [task]),
            client,
            event_sink=events.append,
        ).run()
    )

    assert summary["failed"] == 1
    assert client.calls == []
    latest = ManifestStore(tmp_path / "job" / "manifest.jsonl").load_latest_by_task()
    assert latest["task-1"]["issues"][0]["code"] == "bad_mask"
    failed_event = [json.loads(line) for line in events if json.loads(line)["event"] == "task_failed"][0]
    assert failed_event["issues"][0]["message"] == "mask dimensions differ"


def test_batch_engine_pause_control_marks_remaining_tasks_paused(tmp_path):
    tasks = [_task(tmp_path, "task-1"), _task(tmp_path, "task-2")]
    planned = _job(tmp_path, tasks)
    planned.job.root.mkdir(parents=True)
    (planned.job.root / "job.control.json").write_text('{"pause_requested": true}', encoding="utf-8")
    client = SequencedClient([])

    summary = asyncio.run(
        BatchEngine(AppConfig(prompt={"template": "prompt"}), planned, client).run()
    )

    assert summary["paused"] == 2
    assert client.calls == []
    latest = ManifestStore(planned.job.manifest_path).load_latest_by_task()
    assert latest["task-1"]["status"] == "paused"
    assert latest["task-2"]["status"] == "paused"


def test_batch_engine_cancel_control_marks_remaining_tasks_canceled(tmp_path):
    tasks = [_task(tmp_path, "task-1"), _task(tmp_path, "task-2")]
    planned = _job(tmp_path, tasks)
    planned.job.root.mkdir(parents=True)
    (planned.job.root / "job.control.json").write_text('{"cancel_requested": true}', encoding="utf-8")
    client = SequencedClient([])

    summary = asyncio.run(
        BatchEngine(AppConfig(prompt={"template": "prompt"}), planned, client).run()
    )

    assert summary["canceled"] == 2
    assert client.calls == []
    latest = ManifestStore(planned.job.manifest_path).load_latest_by_task()
    assert latest["task-1"]["status"] == "canceled"
    assert latest["task-2"]["status"] == "canceled"


def test_batch_engine_failure_policy_stop_marks_later_tasks_stopped(tmp_path):
    tasks = [_task(tmp_path, "task-1"), _task(tmp_path, "task-2")]
    client = SequencedClient([ImageBatchError("content_policy", "blocked", retryable=False)])

    summary = asyncio.run(
        BatchEngine(
            AppConfig(
                prompt={"template": "prompt"},
                execution={"concurrency": 1, "failure_policy": "stop"},
            ),
            _job(tmp_path, tasks),
            client,
            retry_backoff_seconds=0,
        ).run()
    )

    assert summary["failed"] == 1
    assert summary["stopped"] == 1
    assert client.calls == ["task-1"]
    latest = ManifestStore(tmp_path / "job" / "manifest.jsonl").load_latest_by_task()
    assert latest["task-2"]["status"] == "stopped"


def test_batch_engine_resume_skips_succeeded_and_retries_failed(tmp_path):
    tasks = [_task(tmp_path, "task-1"), _task(tmp_path, "task-2")]
    planned = _job(tmp_path, tasks)
    store = ManifestStore(planned.job.manifest_path)
    store.append_task_record({"task_id": "task-1", "status": "succeeded"})
    store.append_task_record({"task_id": "task-2", "status": "failed"})
    client = SequencedClient([[CompletedImage(b64_json=PNG_B64)]])

    summary = asyncio.run(
        BatchEngine(AppConfig(prompt={"template": "prompt"}), planned, client, resume=True).run()
    )

    assert summary["skipped"] == 1
    assert summary["succeeded"] == 1
    assert client.calls == ["task-2"]


def test_batch_engine_limits_concurrency_to_config_value(tmp_path):
    tasks = [_task(tmp_path, f"task-{index}") for index in range(6)]
    client = MeasuringClient()

    summary = asyncio.run(
        BatchEngine(
            AppConfig(prompt={"template": "prompt"}, execution={"concurrency": 3}),
            _job(tmp_path, tasks),
            client,
        ).run()
    )

    assert summary["succeeded"] == 6
    assert client.max_running == 3
