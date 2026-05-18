import pytest

from app.core.event_protocol import EventProtocol, EventProtocolError


def test_event_protocol_serializes_and_parses_stable_jsonl_event():
    line = EventProtocol.serialize(
        "task_started",
        job_id="job-20260519-010203",
        task_id="task-000001",
        payload={"path": "input/product.png", "api_key": "sk-secret"},
    )

    assert line.endswith("\n")
    assert "sk-secret" not in line
    event = EventProtocol.parse_line(line)
    assert event["event"] == "task_started"
    assert event["job_id"] == "job-20260519-010203"
    assert event["task_id"] == "task-000001"
    assert event["payload"] == {"path": "input/product.png"}
    assert "timestamp" in event


@pytest.mark.parametrize("event_name", ["job_started", "partial_saved", "task_succeeded", "task_failed", "job_completed"])
def test_event_protocol_accepts_known_event_names(event_name):
    event = EventProtocol.parse_line(EventProtocol.serialize(event_name))

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
