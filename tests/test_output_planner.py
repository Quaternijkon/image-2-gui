import json
import re

from app.core.config import AppConfig
from app.core.models import InputImage, TaskPlan
from app.core.output_planner import OutputPlanner


def test_output_planner_creates_job_structure_and_sanitized_snapshot(tmp_path):
    config = AppConfig(
        api={"api_key": "sk-secret"},
        prompt={"template": "Create {stem}"},
        output={"output_dir": tmp_path, "job_subdir_enabled": True},
    )

    job = OutputPlanner(config).create_job_layout()

    assert job.root.parent == tmp_path
    assert re.match(r"job-\d{8}-\d{6}", job.root.name)
    for name in ["final", "partials", "logs", "failed", "thumbnails"]:
        assert (job.root / name).is_dir()
    assert (job.root / "logs" / "events").is_dir()
    assert (job.root / "logs" / "errors").is_dir()
    snapshot = json.loads((job.root / "config.snapshot.json").read_text(encoding="utf-8"))
    assert "sk-secret" not in json.dumps(snapshot)
    assert "api_key" not in snapshot["api"]
    assert (job.root / "manifest.jsonl").exists()
    assert (job.root / "command.ps1").exists()


def test_output_planner_root_output_mode_still_writes_manifest_and_snapshot(tmp_path):
    config = AppConfig(
        prompt={"template": "Create"},
        output={"output_dir": tmp_path, "job_subdir_enabled": False},
    )

    job = OutputPlanner(config).create_job_layout()

    assert job.root == tmp_path
    assert (tmp_path / "manifest.jsonl").exists()
    assert (tmp_path / "config.snapshot.json").exists()


def test_output_planner_renders_filename_template_and_append_counter(tmp_path, make_image):
    source = make_image(tmp_path / "input" / "Product 001.png")
    config = AppConfig(
        prompt={"template": "Create"},
        image={"quality": "high", "size": "1024x1024", "output_format": "png"},
        output={
            "output_dir": tmp_path / "out",
            "job_subdir_enabled": False,
            "filename_template": "{stem}_{quality}_{size}_{date}_{hash}_{variant}.{ext}",
        },
        execution={"overwrite_policy": "append_counter"},
    )
    input_image = InputImage(path=source, width=32, height=24, format="PNG")
    task = TaskPlan(
        task_id="task-000001",
        mode="edit",
        source_paths=[source],
        mask_path=None,
        rendered_prompt="Create",
        output_plan=None,
        input_image=input_image,
    )

    job = OutputPlanner(config).create_job_layout()
    first = OutputPlanner(config).plan_variant_output(job, task, variant=1)
    first.final_path.write_text("exists", encoding="utf-8")
    second = OutputPlanner(config).plan_variant_output(job, task, variant=1)

    assert first.final_path.name.startswith("Product 001_high_1024x1024_")
    assert first.final_path.name.endswith("_1.png")
    assert second.final_path.stem.endswith("_001")


def test_output_planner_skip_existing_marks_existing_output(tmp_path, make_image):
    source = make_image(tmp_path / "input" / "product.png")
    config = AppConfig(
        prompt={"template": "Create"},
        output={"output_dir": tmp_path / "out", "job_subdir_enabled": False},
        execution={"overwrite_policy": "skip_existing"},
    )
    task = TaskPlan(
        task_id="task-000001",
        mode="edit",
        source_paths=[source],
        mask_path=None,
        rendered_prompt="Create",
        output_plan=None,
        input_image=InputImage(path=source, width=32, height=24, format="PNG"),
    )

    job = OutputPlanner(config).create_job_layout()
    first = OutputPlanner(config).plan_variant_output(job, task, variant=1)
    first.final_path.write_text("exists", encoding="utf-8")
    second = OutputPlanner(config).plan_variant_output(job, task, variant=1)

    assert second.should_skip is True
    assert second.final_path == first.final_path
