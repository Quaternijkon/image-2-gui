import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import typer

from app.core.batch_engine import BatchEngine
from app.core.config import AppConfig
from app.core.manifest_store import sanitize_record
from app.core.openai_image_client import DeterministicMockImageClient, OpenAIImageClient
from app.core.task_planner import TaskPlanner


app = typer.Typer(
    no_args_is_help=True,
    help="GPT Image Batch command line interface.",
)


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
        summary = {
            "event": "dry_run_summary",
            "job_id": planned.job.job_id,
            "total_tasks": len(planned.tasks),
            "issues": len(planned.issues),
            "concurrency": app_config.execution.concurrency,
            "output_dir": str(planned.job.root),
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
