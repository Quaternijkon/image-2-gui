import json
import subprocess
import sys


def test_cli_dry_run_loads_config_applies_overrides_and_prints_summary(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "prompt": {"template": "Generate {index}"},
                "input": {"mode": "generate"},
                "image": {"n": 1},
            }
        ),
        encoding="utf-8",
    )

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
            "--concurrency",
            "3",
            "--dry-run",
            "--events-jsonl",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert lines[-1]["event"] == "dry_run_summary"
    assert lines[-1]["total_tasks"] == 1
    assert lines[-1]["concurrency"] == 3
    assert "sk-" not in result.stdout


def test_cli_non_dry_run_uses_mock_api_env_without_network(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    output_dir = tmp_path / "out"
    config_path.write_text(
        json.dumps(
            {
                "prompt": {"template": "Generate"},
                "input": {"mode": "generate"},
                "image": {"n": 1},
                "output": {"job_subdir_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    env = {**dict(**__import__("os").environ), "GPT_IMAGE_BATCH_MOCK_API": "1"}

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app",
            "run",
            "--config",
            str(config_path),
            "--output-dir",
            str(output_dir),
            "--events-jsonl",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0
    assert (output_dir / "summary.json").exists()
    assert json.loads((output_dir / "summary.json").read_text())["succeeded"] == 1
    assert list((output_dir / "final").glob("*.png"))
    assert "sk-" not in result.stdout
