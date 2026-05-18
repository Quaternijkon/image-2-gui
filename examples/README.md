# Examples

This directory contains a safe starting config with no API keys or secret material.

Dry-run the example before any API call:

```powershell
python -m app run --config examples/example.config.json --output-dir .\out --dry-run
```

Run without network access by enabling mock mode:

```powershell
$env:GPT_IMAGE_BATCH_MOCK_API=1
python -m app run --config examples/example.config.json --output-dir .\out
```

Run against the real API only after setting `OPENAI_API_KEY` in your environment:

```powershell
$env:OPENAI_API_KEY="..."
python -m app run --config examples/example.config.json --output-dir .\out
```

Use profiles to save repeatable settings:

```powershell
python -m app profile save demo --config examples/example.config.json
python -m app profile list
python -m app profile load demo
python -m app profile switch demo
```
