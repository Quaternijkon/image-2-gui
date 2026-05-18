import base64
import binascii
import errno
from pathlib import Path

import pytest

from app.core.errors import ImageBatchError
from app.core.models import OutputPlan, TaskPlan
from app.core.output_writer import OutputWriter


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")


def _task(tmp_path):
    plan = OutputPlan(
        final_path=tmp_path / "final" / "image.png",
        partials_dir=tmp_path / "partials" / "task-1",
        failed_dir=tmp_path / "failed",
        thumbnails_dir=tmp_path / "thumbs",
    )
    return TaskPlan(
        task_id="task-1",
        mode="generate",
        rendered_prompt="make one",
        output_plan=plan,
    )


def test_output_writer_decodes_base64_and_writes_final_atomically(tmp_path):
    task = _task(tmp_path)

    path = OutputWriter().write_final(task, PNG_B64)

    assert path == task.output_plan.final_path
    assert path.read_bytes() == PNG_BYTES
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_output_writer_writes_partials_under_task_directory(tmp_path):
    task = _task(tmp_path)

    path = OutputWriter().write_partial(task, PNG_B64, partial_index=2, output_format="png")

    assert path == tmp_path / "partials" / "task-1" / "partial_2.png"
    assert path.read_bytes() == PNG_BYTES


def test_output_writer_rejects_invalid_base64_as_decode_error(tmp_path):
    task = _task(tmp_path)

    with pytest.raises(ImageBatchError) as exc_info:
        OutputWriter().write_final(task, "not base64")

    assert exc_info.value.code == "decode_error"
    assert isinstance(exc_info.value.__cause__, binascii.Error)


def test_output_writer_rejects_paths_outside_output_plan_root(tmp_path):
    task = _task(tmp_path)
    task.output_plan.final_path = tmp_path / "final" / ".." / ".." / "escape.png"

    with pytest.raises(ImageBatchError) as exc_info:
        OutputWriter(output_root=tmp_path / "final").write_final(task, PNG_B64)

    assert exc_info.value.code == "write_error"
    assert exc_info.value.retryable is False


def test_output_writer_rejects_resolved_paths_outside_output_root(tmp_path):
    task = _task(tmp_path)
    task.output_plan.final_path = tmp_path / "outside.png"

    with pytest.raises(ImageBatchError) as exc_info:
        OutputWriter(output_root=tmp_path / "job").write_final(task, PNG_B64)

    assert exc_info.value.code == "write_error"
    assert exc_info.value.retryable is False


def test_output_writer_permission_denied_is_not_retryable(tmp_path, monkeypatch):
    task = _task(tmp_path)

    def raise_permission_denied(self, *args, **kwargs):
        raise PermissionError(errno.EACCES, "denied", str(self))

    monkeypatch.setattr(Path, "open", raise_permission_denied)

    with pytest.raises(ImageBatchError) as exc_info:
        OutputWriter(output_root=tmp_path).write_final(task, PNG_B64)

    assert exc_info.value.code == "write_error"
    assert exc_info.value.retryable is False


def test_output_writer_temporary_busy_error_is_retryable(tmp_path, monkeypatch):
    task = _task(tmp_path)

    def raise_busy(self, *args, **kwargs):
        raise OSError(errno.EBUSY, "busy", str(self))

    monkeypatch.setattr(Path, "open", raise_busy)

    with pytest.raises(ImageBatchError) as exc_info:
        OutputWriter(output_root=tmp_path).write_final(task, PNG_B64)

    assert exc_info.value.code == "write_error"
    assert exc_info.value.retryable is True


def test_output_writer_uses_unique_temp_names(tmp_path, monkeypatch):
    task = _task(tmp_path)
    opened_paths = []
    real_open = Path.open

    def recording_open(self, *args, **kwargs):
        opened_paths.append(self)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording_open)

    OutputWriter(output_root=tmp_path).write_final(task, PNG_B64)
    OutputWriter(output_root=tmp_path).write_final(task, PNG_B64)

    temp_paths = [path for path in opened_paths if path.name.endswith(".tmp")]
    assert len(temp_paths) == 2
    assert temp_paths[0] != temp_paths[1]
