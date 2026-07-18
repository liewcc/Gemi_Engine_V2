# Gemi Engine V2

Atomic browser-automation kernel for provider web UIs (Gemini, DeepSeek,
Copilot, z.ai), driven via Playwright and exposed as a local HTTP service
(FastAPI, default port from `engine_config.json`).

The engine is a **dumb executor**: it performs single browser actions
(navigate, new chat, set prompt, submit, wait for response, download images,
switch account/service, discover capabilities) and holds no automation logic —
no loops, retries, quotas, or goals. Orchestration lives in the consuming
projects, which embed this repo as a git submodule:

- [Gemi_MCP_V2](https://github.com/liewcc/Gemi_MCP_V2) — MCP server + TUI
- [GemiPersona_V2](https://github.com/liewcc/GemiPersona_V2) — Electron app + conductor

## Layout

- `engine_service.py` — FastAPI service: `/engine/*` lifecycle + `/browser/*`
  atomic operations, single browser lock, idle-timeout watchdog.
- `browser_engine.py` — Playwright lifecycle, profile sandbox (junction into
  `browser_user_data/`), provider registry, one tab per provider.
- `providers/` — per-service DOM logic (`dom.py` selectors + `sequences.py`
  action sequences) behind a common abstract base.

## Run

```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python engine_service.py
```

Playwright browsers install into the repo-local `ms-playwright/` directory
(portable; not committed).
