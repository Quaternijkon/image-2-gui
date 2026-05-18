import json
from pathlib import Path
from typing import Any


RUNNING_STATUSES = {"queued", "running", "started", "in_progress"}
TERMINAL_SUCCESS_STATUSES = {"succeeded", "skipped"}


class ManifestStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sanitized = sanitize_record(record)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sanitized, sort_keys=True, default=str) + "\n")

    def load_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(json.loads(line))
        return records

    def load_latest_by_task(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for record in self.load_records():
            task_id = record.get("task_id")
            if task_id:
                latest[str(task_id)] = record
        return latest

    def summarize(self) -> dict[str, int]:
        summary = {"succeeded": 0, "failed": 0, "skipped": 0, "running": 0, "total": 0}
        for record in self.load_latest_by_task().values():
            summary["total"] += 1
            status = str(record.get("status", "running"))
            if status == "succeeded":
                summary["succeeded"] += 1
            elif status == "failed":
                summary["failed"] += 1
            elif status == "skipped":
                summary["skipped"] += 1
            else:
                summary["running"] += 1
        return summary

    def tasks_needing_resume(
        self, task_ids: list[str], *, retry_failed: bool = True
    ) -> list[str]:
        latest = self.load_latest_by_task()
        resume: list[str] = []
        for task_id in task_ids:
            record = latest.get(task_id)
            if record is None:
                resume.append(task_id)
                continue
            status = str(record.get("status", ""))
            if status in TERMINAL_SUCCESS_STATUSES:
                continue
            if status == "failed" and not retry_failed:
                continue
            resume.append(task_id)
        return resume


def sanitize_record(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_record(item)
            for key, item in value.items()
            if key.lower() not in {"api_key", "authorization"}
        }
    if isinstance(value, list):
        return [sanitize_record(item) for item in value]
    return value


__all__ = ["ManifestStore", "sanitize_record"]
