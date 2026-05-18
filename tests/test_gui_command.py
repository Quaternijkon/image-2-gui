import json
import subprocess
import sys

from app.cli.main import _load_config_with_overrides
from app.core.task_planner import TaskPlanner
from app.presentation.gui_app import GuiFormState, RunnerEventState


def test_gui_command_preview_does_not_create_filesystem_artifacts(tmp_path):
    output_dir = tmp_path / "preview-output"
    state = GuiFormState(
        output_dir=output_dir,
        prompt="Generate preview only",
        mode="generate",
    )

    preview = state.build_command_preview(dry_run=True)

    assert not output_dir.exists()
    assert str(output_dir).replace("\\", "/") in preview.command
    assert "config.snapshot.json" in preview.command
    assert "--dry-run" in preview.command


def test_gui_prepared_job_plans_cli_runner_to_same_exact_root_and_control_path(tmp_path):
    state = GuiFormState(
        output_dir=tmp_path / "output",
        prompt="Generate exact root",
        mode="generate",
        concurrency=4,
    )

    prepared = state.prepare_job_files(dry_run=False)
    runner_config = _load_config_with_overrides(
        config_path=prepared.config_snapshot_path,
        input_dir=None,
        output_dir=prepared.root,
        concurrency=4,
    )
    planned = TaskPlanner(runner_config).build()

    assert runner_config.output.job_subdir_enabled is False
    assert planned.job.root == prepared.root
    assert planned.job.config_snapshot_path == prepared.config_snapshot_path
    assert prepared.control_path == planned.job.root / "job.control.json"
    assert not (prepared.root / prepared.root.name).exists()


def test_gui_form_state_builds_config_and_command_without_secret_material(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    state = GuiFormState(
        input_dir=input_dir,
        output_dir=output_dir,
        prompt="Retouch the product photo",
        mode="edit",
        size="1024x1024",
        quality="high",
        output_format="webp",
        background="opaque",
        moderation="low",
        image_count=3,
        concurrency=3,
        api_key_source="env:OPENAI_API_KEY",
        api_key="sk-secret-never-write",
    )

    config = state.build_config()
    assert config.input.input_dir == input_dir
    assert config.output.output_dir == output_dir
    assert config.prompt.template == "Retouch the product photo"
    assert config.image.output_format == "webp"
    assert config.image.n == 3
    assert config.execution.concurrency == 3

    layout = state.prepare_job_files(dry_run=True)

    snapshot = json.loads(layout.config_snapshot_path.read_text(encoding="utf-8"))
    command = layout.command_path.read_text(encoding="utf-8")
    assert snapshot["prompt"]["template"] == "Retouch the product photo"
    assert snapshot["image"]["n"] == 3
    assert "api_key" not in snapshot["api"]
    assert "sk-secret-never-write" not in layout.config_snapshot_path.read_text(encoding="utf-8")
    assert "sk-secret-never-write" not in command
    assert "--dry-run" in command
    assert "--events-jsonl" in command
    assert snapshot["output"]["job_subdir_enabled"] is False


def test_runner_event_state_updates_progress_log_and_errors():
    state = RunnerEventState()

    state.handle_runner_event({"event": "task_started", "task_id": "task-001"})
    state.handle_runner_event({"event": "task_succeeded", "task_id": "task-001", "output_path": "out.png"})
    state.handle_runner_event({"event": "task_failed", "task_id": "task-002", "error": "bad prompt"})
    state.handle_runner_event({"event": "dry_run_summary", "total_tasks": 2, "issues": 1})

    assert state.total_tasks == 2
    assert state.completed_tasks == 1
    assert state.failed_tasks == 1
    assert state.issues == 1
    assert state.rows["task-001"]["status"] == "succeeded"
    assert state.rows["task-002"]["message"] == "bad prompt"
    assert any("dry_run_summary" in line for line in state.log_lines)


def test_python_module_exposes_gui_subcommand_help():
    result = subprocess.run(
        [sys.executable, "-m", "app", "gui", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Launch the PySide6 GUI" in result.stdout


def test_gui_launch_reports_clear_error_when_pyside6_unavailable():
    try:
        import PySide6  # noqa: F401
    except ImportError:
        pass
    else:
        return

    result = subprocess.run(
        [sys.executable, "-m", "app", "gui"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "PySide6 is required" in result.stderr
