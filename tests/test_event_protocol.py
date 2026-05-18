import pytest

from app.core.event_protocol import EventProtocol, EventProtocolError


def test_event_protocol_serializes_and_parses_stable_jsonl_event():
    line = EventProtocol.serialize(
        "task_started",
        job_id="job-20260519-010203",
        task_id="task-000001",
        input_file="input/product.png",
        note="token sk-secret should disappear",
    )

    assert line.endswith("\n")
    assert "sk-secret" not in line
    event = EventProtocol.parse_line(line)
    assert event["event"] == "task_started"
    assert event["job_id"] == "job-20260519-010203"
    assert event["task_id"] == "task-000001"
    assert event["input_file"] == "input/product.png"
    assert "payload" not in event
    assert "timestamp" in event


@pytest.mark.parametrize("event_name", ["job_started", "partial_saved", "task_succeeded", "task_failed", "job_completed"])
def test_event_protocol_accepts_known_event_names(event_name):
    kwargs = {
        "job_started": {"job_id": "job-1", "total_tasks": 1},
        "partial_saved": {"job_id": "job-1", "task_id": "000001", "partial_file": "partials/a.png"},
        "task_succeeded": {"job_id": "job-1", "task_id": "000001", "output_files": ["final/a.png"]},
        "task_failed": {"job_id": "job-1", "task_id": "000001", "error": "failed"},
        "job_completed": {"job_id": "job-1", "summary": {"succeeded": 1}},
    }[event_name]
    event = EventProtocol.parse_line(EventProtocol.serialize(event_name, **kwargs))

    assert event["event"] == event_name


def test_event_protocol_rejects_unknown_event_name():
    with pytest.raises(EventProtocolError, match="unknown event"):
        EventProtocol.serialize("surprise")


def test_event_protocol_rejects_malformed_jsonl():
    with pytest.raises(EventProtocolError, match="invalid JSON"):
        EventProtocol.parse_line("{not-json}\n")


def test_event_protocol_rejects_missing_required_event_field():
    with pytest.raises(EventProtocolError, match="missing event"):
        EventProtocol.parse_line('{"timestamp": "2026-05-19T00:00:00Z"}\n')


def test_event_protocol_validates_required_fields_per_event():
    with pytest.raises(EventProtocolError, match="missing required field: total_tasks"):
        EventProtocol.serialize("job_started", job_id="job-1")


def test_event_protocol_redacts_secret_looking_strings_in_nested_values():
    line = EventProtocol.serialize(
        "task_failed",
        job_id="job-1",
        task_id="000001",
        error={"message": "bad sk-secret-value", "items": ["sk-nested"]},
    )

    assert "sk-secret-value" not in line
    assert "sk-nested" not in line
    assert "[REDACTED]" in line
