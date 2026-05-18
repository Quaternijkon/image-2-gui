# GPT Image Batch

Foundation for a Python 3.10 Windows-friendly GUI and CLI batch runner for the OpenAI Image API `gpt-image-2`.

This first task establishes the package scaffold, centralized API capability data, Pydantic configuration validation, a reproducible PowerShell command builder, and a CLI help surface.

## Development

```powershell
python -m app run --help
pytest
```

The generated commands intentionally do not include API key material. Configure `OPENAI_API_KEY` in the environment before running future API-backed tasks.
