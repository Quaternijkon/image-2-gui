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
    assert "estimate" in result.stdout


def test_python_module_exposes_profile_commands_help():
    result = subprocess.run(
        [sys.executable, "-m", "app", "profile", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "list" in result.stdout
    assert "save" in result.stdout
    assert "load" in result.stdout
    assert "delete" in result.stdout


def test_python_module_profile_save_list_load_delete_round_trip(tmp_path):
    config_path = tmp_path / "config.json"
    profiles_dir = tmp_path / "profiles"
    config_path.write_text(
        '{"api":{"api_key":"sk-secret","api_key_source":"env"},"prompt":{"template":"Generate"}}',
        encoding="utf-8",
    )

    save = subprocess.run(
        [
            sys.executable,
            "-m",
            "app",
            "profile",
            "save",
            "demo",
            "--config",
            str(config_path),
            "--profiles-dir",
            str(profiles_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    listed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app",
            "profile",
            "list",
            "--profiles-dir",
            str(profiles_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    loaded = subprocess.run(
        [
            sys.executable,
            "-m",
            "app",
            "profile",
            "load",
            "demo",
            "--profiles-dir",
            str(profiles_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    deleted = subprocess.run(
        [
            sys.executable,
            "-m",
            "app",
            "profile",
            "delete",
            "demo",
            "--profiles-dir",
            str(profiles_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert save.returncode == 0
    assert listed.returncode == 0
    assert "demo" in listed.stdout
    assert loaded.returncode == 0
    assert "Generate" in loaded.stdout
    assert "sk-secret" not in loaded.stdout
    assert deleted.returncode == 0
