import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.command_builder import CommandBuilder
from app.core.config import AppConfig
from app.core.manifest_store import sanitize_record
from app.core.models import JobLayout, OutputPlan, TaskPlan
from app.core.prompt_renderer import PromptRenderer


class OutputPlanner:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def create_job_layout(self) -> JobLayout:
        output_root = self.config.output.output_dir or Path.cwd() / "output"
        if self.config.output.job_subdir_enabled:
            job_id = _unique_job_id(output_root)
            root = output_root / job_id
        else:
            root = output_root
            job_id = root.name or "job-root"

        layout = JobLayout(
            job_id=job_id,
            root=root,
            final_dir=root / "final",
            partials_dir=root / "partials",
            logs_dir=root / "logs",
            events_dir=root / "logs" / "events",
            errors_dir=root / "logs" / "errors",
            failed_dir=root / "failed",
            thumbnails_dir=root / "thumbnails",
            manifest_path=root / "manifest.jsonl",
            summary_path=root / "summary.json",
            config_snapshot_path=root / "config.snapshot.json",
            command_path=root / "command.ps1",
        )

        for directory in [
            layout.root,
            layout.final_dir,
            layout.partials_dir,
            layout.logs_dir,
            layout.events_dir,
            layout.errors_dir,
            layout.failed_dir,
            layout.thumbnails_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        if self.config.output.save_config_snapshot:
            _write_json(layout.config_snapshot_path, _sanitized_config(self.config))
        if self.config.output.save_manifest:
            layout.manifest_path.touch(exist_ok=True)
        _write_json(layout.summary_path, {"total": 0, "succeeded": 0, "failed": 0, "skipped": 0})
        layout.command_path.write_text(
            CommandBuilder(self.config).build_powershell_command(
                config_path=layout.config_snapshot_path,
                input_dir=self.config.input.input_dir,
                output_dir=layout.root,
                concurrency=self.config.execution.concurrency,
                events_jsonl=True,
            ),
            encoding="utf-8",
        )
        return layout

    def plan_variant_output(self, job: JobLayout, task: TaskPlan, *, variant: int) -> OutputPlan:
        stem = _task_stem(task)
        extension = self.config.image.output_format.lower().lstrip(".")
        context = {
            "stem": stem,
            "index": _task_index(task.task_id),
            "variant": variant,
            "quality": self.config.image.quality,
            "size": self.config.image.size,
            "date": datetime.now().strftime("%Y%m%d"),
            "hash": _task_hash(task),
            "ext": extension,
        }
        filename = PromptRenderer(variables_enabled=True, context=context).render(
            self.config.output.filename_template
        )
        if Path(filename).suffix == "":
            filename = f"{filename}.{extension}"
        final_path = job.final_dir / filename
        policy = self.config.execution.overwrite_policy
        should_skip = False

        if final_path.exists():
            if policy == "skip_existing":
                should_skip = True
            elif policy == "append_counter":
                final_path = _append_counter(final_path)

        return OutputPlan(
            final_path=final_path,
            partials_dir=job.partials_dir / task.task_id,
            failed_dir=job.failed_dir,
            thumbnails_dir=job.thumbnails_dir,
            should_skip=should_skip,
            overwrite_policy=policy,
        )


def _unique_job_id(output_root: Path) -> str:
    base = datetime.now().strftime("job-%Y%m%d-%H%M%S")
    candidate = base
    counter = 1
    while (output_root / candidate).exists():
        candidate = f"{base}-{counter:03d}"
        counter += 1
    return candidate


def _sanitized_config(config: AppConfig) -> dict[str, Any]:
    return sanitize_record(config.model_dump(mode="json", exclude_none=True))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _task_stem(task: TaskPlan) -> str:
    if task.source_paths:
        return task.source_paths[0].stem
    return task.task_id


def _task_index(task_id: str) -> int:
    suffix = task_id.rsplit("-", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return 0


def _task_hash(task: TaskPlan) -> str:
    digest = hashlib.sha256()
    digest.update(task.task_id.encode("utf-8"))
    for path in task.source_paths:
        digest.update(str(path).encode("utf-8"))
    digest.update(task.rendered_prompt.encode("utf-8"))
    return digest.hexdigest()[:8]


def _append_counter(path: Path) -> Path:
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter:03d}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


__all__ = ["OutputPlanner"]
