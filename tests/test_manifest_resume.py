import json

from app.core.manifest_store import ManifestStore


def test_manifest_store_appends_sanitized_jsonl_and_loads_latest_by_task(tmp_path):
    store = ManifestStore(tmp_path / "manifest.jsonl")

    store.append({"task_id": "task-1", "status": "running", "api_key": "sk-secret"})
    store.append({"task_id": "task-1", "status": "succeeded", "output": "final/a.png"})
    store.append({"task_id": "task-2", "status": "failed"})

    text = (tmp_path / "manifest.jsonl").read_text(encoding="utf-8")
    assert "sk-secret" not in text
    assert "api_key" not in text
    latest = store.load_latest_by_task()
    assert latest["task-1"]["status"] == "succeeded"
    assert latest["task-2"]["status"] == "failed"


def test_manifest_store_summarizes_and_selects_resume_tasks(tmp_path):
    store = ManifestStore(tmp_path / "manifest.jsonl")
    for record in [
        {"task_id": "task-1", "status": "succeeded"},
        {"task_id": "task-2", "status": "failed"},
        {"task_id": "task-3", "status": "skipped"},
        {"task_id": "task-4", "status": "running"},
        {"task_id": "task-5", "status": "queued"},
    ]:
        store.append(record)

    summary = store.summarize()

    assert summary == {
        "succeeded": 1,
        "failed": 1,
        "skipped": 1,
        "running": 2,
        "total": 5,
    }
    assert store.tasks_needing_resume(["task-1", "task-2", "task-3", "task-4", "task-5"]) == [
        "task-2",
        "task-4",
        "task-5",
    ]
    assert store.tasks_needing_resume(
        ["task-1", "task-2", "task-3", "task-4", "task-5"], retry_failed=False
    ) == ["task-4", "task-5"]


def test_manifest_store_ignores_blank_lines_when_loading(tmp_path):
    path = tmp_path / "manifest.jsonl"
    path.write_text('\n{"task_id": "task-1", "status": "succeeded"}\n\n', encoding="utf-8")

    assert ManifestStore(path).load_latest_by_task()["task-1"]["status"] == "succeeded"
