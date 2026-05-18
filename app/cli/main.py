from pathlib import Path
from typing import Optional

import typer


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
) -> None:
    """Stub runner command for the initial scaffold."""
    typer.echo("Runner execution is not implemented in this foundation task.")
    raise typer.Exit(code=0)


def main() -> None:
    app()
