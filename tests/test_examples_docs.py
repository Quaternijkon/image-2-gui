import json
from pathlib import Path

from app.core.config import AppConfig


def test_example_config_is_valid_and_contains_no_api_key_material():
    path = Path("examples/example.config.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    config = AppConfig.model_validate(payload)

    assert config.prompt.template
    assert config.api.api_key is None
    assert "sk-" not in path.read_text(encoding="utf-8")


def test_examples_readme_and_root_docs_cover_required_user_flows():
    examples_readme = Path("examples/README.md").read_text(encoding="utf-8")
    root_readme = Path("README.md").read_text(encoding="utf-8")
    build_script = Path("scripts/build_windows.ps1").read_text(encoding="utf-8")

    combined = f"{examples_readme}\n{root_readme}\n{build_script}"
    for expected in [
        "OPENAI_API_KEY",
        "python -m app run",
        "python -m app gui",
        "GPT_IMAGE_BATCH_MOCK_API=1",
        "--dry-run",
        "GPT_IMAGE_BATCH_REAL_API_SMOKE=1",
        "profile",
        "PySide6",
        "PyInstaller",
        "no API keys",
    ]:
        assert expected in combined
