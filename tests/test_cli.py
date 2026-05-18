import subprocess
import sys


def test_python_module_exposes_run_subcommand_help():
    result = subprocess.run(
        [sys.executable, "-m", "app", "run", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--config" in result.stdout
    assert "--output-dir" in result.stdout


def test_python_module_accepts_run_subcommand_dry_run_arguments(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"prompt":{"template":"Generate"},"input":{"mode":"generate"}}', encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app",
            "run",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--dry-run",
            "--events-jsonl",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "dry_run_summary" in result.stdout
