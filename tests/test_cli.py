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


def test_python_module_accepts_run_subcommand_stub_arguments():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app",
            "run",
            "--config",
            "D:/job.config.json",
            "--output-dir",
            "D:/out",
            "--events-jsonl",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "not implemented" in result.stdout
