import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import typer

from app.core.batch_engine import BatchEngine
from app.core.config import AppConfig
from app.core.cost_estimator import CostEstimator
from app.core.manifest_store import sanitize_record
from app.core.openai_image_client import DeterministicMockImageClient, OpenAIImageClient
from app.core.profile_store import ProfileStore
from app.core.task_planner import TaskPlanner


app = typer.Typer(
    no_args_is_help=True,
    help="GPT Image Batch command line interface.",
)
profile_app = typer.Typer(help="Save, load, list, and switch named job profiles.")
app.add_typer(profile_app, name="profile")


@app.callback()
def root() -> None:
    """GPT Image Batch command line interface."""


@app.command()
def run(
    config: Path = typer.Option(..., "--config", help="Path to the job configuration JSON file."),
    input_dir: Optional[Path] = typer.Option(None, "--input-dir", help="Input image directory."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Output directory."),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", min=1, help="Override job concurrency."),
    events_jsonl: bool = typer.Option(False, "--events-jsonl", help="Emit runner events as JSONL."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan and validate the job without calling the API."),
) -> None:
    """Run or preflight a GPT Image batch job."""
    app_config = _load_config_with_overrides(
        config_path=config,
        input_dir=input_dir,
        output_dir=output_dir,
        concurrency=concurrency,
    )
    planned = TaskPlanner(app_config).build()

    if dry_run:
        estimate = CostEstimator(app_config).estimate(planned)
        summary = {
            "event": "dry_run_summary",
            "job_id": planned.job.job_id,
            "total_tasks": len(planned.tasks),
            "issues": len(planned.issues),
            "concurrency": app_config.execution.concurrency,
            "output_dir": str(planned.job.root),
            "estimate": estimate.model_dump(mode="json"),
        }
        _echo(summary, jsonl=events_jsonl)
        raise typer.Exit(code=0)

    client = (
        DeterministicMockImageClient()
        if os.environ.get("GPT_IMAGE_BATCH_MOCK_API") == "1"
        else OpenAIImageClient(app_config)
    )
    event_sink = (lambda line: typer.echo(line.rstrip("\n"))) if events_jsonl else None
    summary = asyncio.run(BatchEngine(app_config, planned, client, event_sink=event_sink).run())
    if not events_jsonl:
        _echo({"summary": summary, "output_dir": str(planned.job.root)}, jsonl=False)
    raise typer.Exit(code=0)


@app.command()
def gui() -> None:
    """Launch the PySide6 GUI."""
    try:
        from app.presentation.gui_app import launch_gui

        exit_code = launch_gui()
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=exit_code)


@profile_app.command("list")
def profile_list(
    profiles_dir: Path = typer.Option(
        Path.home() / ".gpt-image-batch" / "profiles",
        "--profiles-dir",
        help="Directory containing saved profile JSON files.",
    ),
) -> None:
    """List saved profile names."""
    store = ProfileStore(profiles_dir)
    payload = {"profiles": store.list_profiles(), "active": store.active_profile()}
    _echo(payload, jsonl=False)


@profile_app.command("save")
def profile_save(
    name: str = typer.Argument(..., help="Profile name to save."),
    config: Path = typer.Option(..., "--config", help="Config JSON file to save as a profile."),
    profiles_dir: Path = typer.Option(
        Path.home() / ".gpt-image-batch" / "profiles",
        "--profiles-dir",
        help="Directory for saved profile JSON files.",
    ),
) -> None:
    """Save a config JSON file as a named profile."""
    app_config = AppConfig.model_validate(json.loads(config.read_text(encoding="utf-8")))
    saved_path = ProfileStore(profiles_dir).save(name, app_config)
    _echo({"saved": name, "path": str(saved_path)}, jsonl=False)


@profile_app.command("load")
def profile_load(
    name: str = typer.Argument(..., help="Profile name to load."),
    profiles_dir: Path = typer.Option(
        Path.home() / ".gpt-image-batch" / "profiles",
        "--profiles-dir",
        help="Directory containing saved profile JSON files.",
    ),
) -> None:
    """Print a saved profile as JSON."""
    config = ProfileStore(profiles_dir).load(name)
    payload = config.model_dump(mode="json")
    payload.get("api", {}).pop("api_key", None)
    _echo(payload, jsonl=False)


@profile_app.command("delete")
def profile_delete(
    name: str = typer.Argument(..., help="Profile name to delete."),
    profiles_dir: Path = typer.Option(
        Path.home() / ".gpt-image-batch" / "profiles",
        "--profiles-dir",
        help="Directory containing saved profile JSON files.",
    ),
) -> None:
    """Delete a saved profile."""
    deleted = ProfileStore(profiles_dir).delete(name)
    _echo({"deleted": deleted, "profile": name}, jsonl=False)


@profile_app.command("switch")
def profile_switch(
    name: str = typer.Argument(..., help="Profile name to mark active."),
    profiles_dir: Path = typer.Option(
        Path.home() / ".gpt-image-batch" / "profiles",
        "--profiles-dir",
        help="Directory containing saved profile JSON files.",
    ),
) -> None:
    """Mark a saved profile as the active profile."""
    ProfileStore(profiles_dir).switch(name)
    _echo({"active": name}, jsonl=False)


def _load_config_with_overrides(
    *,
    config_path: Path,
    input_dir: Optional[Path],
    output_dir: Path,
    concurrency: Optional[int],
) -> AppConfig:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload.setdefault("input", {})
    payload.setdefault("output", {})
    payload.setdefault("execution", {})
    if input_dir is not None:
        payload["input"]["input_dir"] = str(input_dir)
    payload["output"]["output_dir"] = str(output_dir)
    if concurrency is not None:
        payload["execution"]["concurrency"] = concurrency
    return AppConfig.model_validate(payload)


def _echo(payload: dict[str, object], *, jsonl: bool) -> None:
    if jsonl:
        typer.echo(json.dumps(sanitize_record(payload), sort_keys=True, default=str))
        return
    typer.echo(json.dumps(sanitize_record(payload), indent=2, sort_keys=True, default=str))


def main() -> None:
    app()
