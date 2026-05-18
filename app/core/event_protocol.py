import json
from datetime import datetime, timezone
from typing import Any

from app.core.manifest_store import sanitize_record


ALLOWED_EVENTS = {
    "job_started",
    "task_started",
    "partial_saved",
    "task_succeeded",
    "task_failed",
    "job_completed",
}


class EventProtocolError(ValueError):
    pass


class EventProtocol:
    @staticmethod
    def serialize(
        event: str,
        *,
        job_id: str | None = None,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> str:
        _validate_event_name(event)
        emitted_at = timestamp or datetime.now(timezone.utc)
        record = {
            "timestamp": emitted_at.isoformat().replace("+00:00", "Z"),
            "event": event,
        }
        if job_id is not None:
            record["job_id"] = job_id
        if task_id is not None:
            record["task_id"] = task_id
        if payload is not None:
            record["payload"] = sanitize_record(payload)
        return json.dumps(sanitize_record(record), sort_keys=True, default=str) + "\n"

    @staticmethod
    def parse_line(line: str) -> dict[str, Any]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EventProtocolError(f"invalid JSON event line: {exc}") from exc

        if not isinstance(record, dict):
            raise EventProtocolError("event record must be a JSON object")
        if "event" not in record:
            raise EventProtocolError("missing event field")
        _validate_event_name(str(record["event"]))
        if "timestamp" not in record:
            raise EventProtocolError("missing timestamp field")
        return record


def _validate_event_name(event: str) -> None:
    if event not in ALLOWED_EVENTS:
        raise EventProtocolError(f"unknown event: {event}")


__all__ = ["EventProtocol", "EventProtocolError"]
