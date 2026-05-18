# GPT Image Batch

Python 3.10+ Windows-friendly GUI and CLI batch runner for the OpenAI Image API `gpt-image-2`.

The app supports validated JSON job configs, dry-run preflight, deterministic mock runs, resumable output artifacts, named profiles, and a simple estimated token-unit cost summary. API parameter restrictions live in the centralized capability data and config validators; the cost estimator is explicitly marked as an estimate and does not claim USD pricing.

## First Run

Create and activate a virtual environment, then install the package in editable mode:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

The GUI uses `PySide6`. If the GUI command reports that Qt/PySide6 is missing, install the project dependencies again or install `PySide6` in the active environment.

Set the API key only in your environment. Do not put API keys in config files or profiles.

```powershell
$env:OPENAI_API_KEY="..."
```

Generated configs, profile files, command snapshots, logs, manifests, and summaries are designed to contain no API keys.

## CLI

Show command help:

```powershell
python -m app run --help
python -m app gui --help
python -m app profile --help
```

Dry-run an example job. This validates the config, plans outputs, and prints an estimated token-unit summary without calling the API:

```powershell
python -m app run --config examples/example.config.json --output-dir .\out --dry-run
```

Run in mock mode with no network call:

```powershell
$env:GPT_IMAGE_BATCH_MOCK_API=1
python -m app run --config examples/example.config.json --output-dir .\out
```

Run against the real API after setting `OPENAI_API_KEY`:

```powershell
Remove-Item Env:\GPT_IMAGE_BATCH_MOCK_API -ErrorAction SilentlyContinue
python -m app run --config examples/example.config.json --output-dir .\out
```

Real API smoke tests are guarded and only run when explicitly enabled:

```powershell
$env:GPT_IMAGE_BATCH_REAL_API_SMOKE=1
pytest tests/test_real_api_smoke.py
```

## GUI

Launch the GUI:

```powershell
python -m app gui
```

The GUI requires `PySide6` and uses the same config model and runner underneath the CLI.

## Profiles

Profiles save named `AppConfig` JSON snapshots under a profile directory. Secret `api.api_key` material is omitted when profiles are written or printed.

```powershell
python -m app profile save demo --config examples/example.config.json
python -m app profile list
python -m app profile load demo
python -m app profile switch demo
python -m app profile delete demo
```

Use `--profiles-dir <path>` on profile commands to keep profiles in a project-local or test directory.

## Examples

See [examples/example.config.json](examples/example.config.json) and [examples/README.md](examples/README.md) for a minimal config and copyable commands.

## Packaging

A non-destructive Windows PyInstaller helper is provided at [scripts/build_windows.ps1](scripts/build_windows.ps1). It is not run by tests and does not execute automatically.

Directory build:

```powershell
.\scripts\build_windows.ps1
```

Single-file build:

```powershell
.\scripts\build_windows.ps1 -OneFile
```

Install `PyInstaller` in the target environment before packaging, or let the script install/upgrade it. Packaging should still use environment variables for API keys; no API keys are embedded.

## Development

```powershell
pytest
python -m app run --help
python -m app gui --help
python -m app profile --help
```
