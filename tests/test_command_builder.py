from app.core.command_builder import CommandBuilder
from app.core.config import AppConfig


def test_powershell_command_quotes_paths_and_uses_line_continuations():
    config = AppConfig(
        input={"input_dir": "D:/Input Images"},
        prompt={"template": "Create a clean product image"},
        output={"output_dir": "D:/Output Images"},
        execution={"concurrency": 4},
    )

    command = CommandBuilder(config).build_powershell_command(
        config_path="D:/Jobs/My Job/job.config.json",
        input_dir="D:/Input Images",
        output_dir="D:/Output Images",
        concurrency=4,
        events_jsonl=True,
    )

    assert command.startswith("# Configure OPENAI_API_KEY")
    assert "python -m app run `" in command
    assert '--config "D:/Jobs/My Job/job.config.json" `' in command
    assert '--input-dir "D:/Input Images" `' in command
    assert '--output-dir "D:/Output Images" `' in command
    assert "--concurrency 4 `" in command
    assert "--events-jsonl" in command


def test_powershell_command_never_includes_api_key_material():
    config = AppConfig(
        prompt={"template": "Create a clean product image"},
        api={"api_key_source": "env:OPENAI_API_KEY", "api_key": "sk-secret-should-not-appear"},
    )

    command = CommandBuilder(config).build_powershell_command(
        config_path="D:/job.config.json",
        input_dir=None,
        output_dir="D:/Output",
        concurrency=None,
        events_jsonl=True,
    )

    assert "sk-secret-should-not-appear" not in command
    assert "OPENAI_API_KEY" in command
    assert "--api-key" not in command


def test_powershell_quote_escapes_embedded_double_quotes_and_dollars():
    command = CommandBuilder().build_powershell_command(
        config_path='D:/Jobs/Quoted "Name"/$job.json',
        input_dir=None,
        output_dir='D:/Out "$folder"',
    )

    assert '--config "D:/Jobs/Quoted `"Name`"/`$job.json"' in command
    assert '--output-dir "D:/Out `"`$folder`""' in command
