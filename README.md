# ClipAI v2

Desktop AI companion with typed commands, render-only UI, a single runtime lifecycle, provider abstraction, and cooperative cancellation.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Configure `provider.active` in `config/config.yaml` as `gemini`, `openai`, `anthropic`, or `fake`, and set the corresponding API-key environment variable. ClipAI never performs automatic provider fallback.

## Run and verify

```powershell
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pytest
```
