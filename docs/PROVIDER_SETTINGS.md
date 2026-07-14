# Provider and model settings

ClipAI keeps provider choices explicit: the Tray selects a provider first, then
shows only that provider's model catalog. A new workflow captures the current
provider and model when it starts, so switching settings never changes an
in-flight request or an existing workflow's follow-up context.

## Tray workflow

1. Open **Provider Settings...** to add or replace a Gemini, OpenAI, or
   Anthropic API key. The key is validated against the provider's Models API
   before ClipAI saves or activates it.
2. Choose the provider from **Provider**, then choose its default model from
   **Model**.
3. Use **Refresh Models** to request a fresh OpenAI, Gemini, or custom-gateway
   catalog. Anthropic uses the local catalog in `config/config.yaml` in this
   release.
4. After editing `.env` manually, choose **Reload Configuration**. ClipAI keeps
   the previous runtime settings if the file is invalid or incomplete.

Pending, success, and failure states reflect the real validation, persistence,
reload, and refresh lifecycle. A choice is not marked successful before its
`.env` update succeeds.

## `.env` contract

Copy `.env.example` to `.env`. The file takes precedence over same-named system
environment variables.

```dotenv
CLIPAI_PROVIDER=gemini

GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-5
```

Tray changes preserve comments and unrelated values and atomically update only
the requested settings. Never commit `.env`; `.env.example` contains only empty
or illustrative values.

Models listed in `config/config.yaml` are the offline fallback. A selected
non-YAML model is retained in `.env` and appears after restart as
`custom/current`; it can be checked again with **Refresh Models**.

## OpenAI-compatible custom gateway

This release supports one gateway profile using `POST /v1/chat/completions`:

```dotenv
CLIPAI_GATEWAY_NAME=Local AI
CLIPAI_GATEWAY_BASE_URL=http://localhost:8000
CLIPAI_GATEWAY_API_KEY=
CLIPAI_GATEWAY_MODEL=my-model
```

- The API key is optional.
- Plain HTTP is accepted only for loopback hosts; remote gateways require
  HTTPS.
- ClipAI normalizes the base URL to one `/v1` suffix.
- **Validate and Save** first requests `/v1/models`. If the gateway responds
  with 404 or 405, ClipAI sends one minimal Chat Completions request, which may
  consume a small number of tokens.
- The gateway URL and API key are not shown in the Tray or diagnostics.
