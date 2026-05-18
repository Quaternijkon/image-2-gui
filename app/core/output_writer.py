from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from app.core.errors import ImageBatchError
from app.core.models import TaskPlan


class OutputWriter:
    def write_final(self, task: TaskPlan, b64_json: str) -> Path:
        if task.output_plan is None:
            raise ImageBatchError("write_error", "task has no output plan")
        return self._write_b64(task.output_plan.final_path, b64_json)

    def write_partial(
        self,
        task: TaskPlan,
        b64_json: str,
        *,
        partial_index: int,
        output_format: str,
    ) -> Path:
        if task.output_plan is None:
            raise ImageBatchError("write_error", "task has no output plan")
        extension = output_format.lower().lstrip(".")
        partial_path = task.output_plan.partials_dir / f"partial_{partial_index}.{extension}"
        return self._write_b64(partial_path, b64_json)

    def _write_b64(self, path: Path, b64_json: str) -> Path:
        if ".." in path.parts:
            raise ImageBatchError("write_error", f"unsafe output path: {path}")
        try:
            payload = base64.b64decode(b64_json, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageBatchError("decode_error", "image payload is not valid base64") from exc
        return self._write_bytes(path, payload)

    def _write_bytes(self, path: Path, payload: bytes) -> Path:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tmp_path.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            tmp_path.replace(path)
            return path
        except OSError as exc:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise ImageBatchError("write_error", str(exc), retryable=True) from exc


__all__ = ["OutputWriter"]
