import base64
import binascii

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
        OutputWriter().write_final(task, PNG_B64)

    assert exc_info.value.code == "write_error"
