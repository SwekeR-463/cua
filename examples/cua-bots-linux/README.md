# Cua Bots for Linux

A Linux port of [`examples/cua-bots-macos`](../cua-bots-macos): persistent bots,
each with a face you design, its own [Cua Space](https://cua.ai/docs/spaces),
a memory that outlives the computer, routines, approvals and rules.

The macOS sample is SwiftUI/AppKit on the Cua Swift SDK. SwiftUI cannot run on
Linux, so this port keeps the same product and the same Cua runtime but
reimplements the presentation layer:

* **Backend** — Python 3 and the published `cua` Spaces SDK (the same Rust
  runtime the Swift app links), FastAPI + WebSocket.
* **UI** — React + Vite, served by the backend; the koala avatar uses the
  geometry from `CuaBotsCore/Avatar`, and the screens follow the macOS layout.
* **Desktop shell** — optional Electron window; `run.sh` falls back to a
  Chrome app window.

The Volume layout, directives (`[[status: …]]`, `[[ask: …]]`, …), rules,
schedules, approvals, tasks, notifications and bot state mirror
`CuaBotsCore`/`CuaBotsCua` closely, so the two apps behave the same.

## Quick start

```sh
cd examples/cua-bots-linux
./run.sh
```

The first run creates `.venv`, installs `requirements.txt`, builds `web/dist`
if needed, starts the backend on `127.0.0.1:8765`, then opens Electron (if
installed) or Chrome in app mode. To install the desktop shell:

```sh
(cd electron && npm install)
```

If npm blocks Electron's postinstall, run
`node electron/node_modules/electron/install.js` once.

```sh
./run.sh --backend-only     # API + UI only, no window
```

Requirements:

* Linux (tested on Ubuntu 24.04, x64), Docker Engine.
* Python 3.11–3.13.
* Node 20+ to build the UI (only needed on the first run or after changing
  `web/src`).
* A model: local Ollama, a custom OpenAI-compatible endpoint, or a provider
  key. Without one the app runs a scripted demo.

## Models

### Local Ollama (default, free)

If `ollama` and a model store exist, the backend starts a small **sidecar**
container on the Docker bridge using the host's Ollama binary and model store.
The bot's harness runs inside its Space, so it talks to the sidecar over the
bridge instead of trying to reach the host's loopback. Nothing leaves the
machine. It uses the GPU when the Docker host has one.

```sh
# default model
./run.sh
# choose another model already present in the host's Ollama store
CUA_BOTS_MODEL=llama3.2:3b ./run.sh
```

The sidecar starts Ollama with a 65,536-token context and an 8-bit KV cache
(the context Hermes expects) and uses the GPU when available. A 3B model is
fine for trying the app, but small local models are best-effort at the
directive protocol and multi-step tool use. Use a provider key or a larger
model with at least 64k context for reliable work. The sidecar speaks the
OpenAI chat wire, so use **Hermes** or **OpenClaw** with it; Codex and Claude
Code need their own provider endpoint/keys.

The sidecar is named `cua-bots-ollama`; stop it with
`docker rm -f cua-bots-ollama`. Set `CUA_BOTS_OLLAMA_SIDECAR=0` to disable it.
The app listens on `127.0.0.1` by default; only set `CUA_BOTS_HOST=0.0.0.0`
when you deliberately want the API reachable from another machine.

If the host's Docker bridge can reach your Ollama (Docker Desktop,
`host.docker.internal`, or a LAN address), point the app at it directly:

```sh
CUA_BOTS_MODEL_URL=http://host.docker.internal:11434/v1 \
CUA_BOTS_MODEL=llama3.2:3b CUA_BOTS_MODEL_KEY_VARS=OPENAI_API_KEY \
OPENAI_API_KEY=ollama ./run.sh
```

### Provider keys

The four harnesses from the macOS app are available: Hermes, OpenClaw, Codex
and Claude Code. The backend forwards only the key variables the harness
needs:

```sh
ANTHROPIC_API_KEY=... ./run.sh          # Claude Code, Hermes, OpenClaw
OPENAI_API_KEY=... ./run.sh             # Codex, Hermes, OpenClaw
OPENROUTER_API_KEY=... ./run.sh         # Hermes, OpenClaw
```

### Scripted demo

```sh
CUA_BOTS_DEMO=1 ./run.sh
```

Useful for screenshots and UI work: the bot replies with scripted directives,
so the chat, tasks, approvals and routines flow without a model.

## Data

| Path | What |
| --- | --- |
| `~/.local/share/cua-bots-linux/state.json` | conversations, approvals, notifications, runtime ids |
| `~/.local/share/cua-bots-linux/Volume/` | one folder per bot, same layout as the Mac sample |
| `~/.local/share/cua-bots-linux/routines.json` | the routine clock's recent firings |

`CUA_BOTS_DATA_DIR` moves the whole data directory; `CUA_BOTS_VOLUME` only the
Volume root.

## What matches the macOS app

* Create a bot: name, color/eyes/ears, this computer or Cua Cloud (cloud is
  disabled because Cua Cloud ended), harness, Volume home.
* A Space per bot (`bot-<name>`) with `Space.agent_start`, events streamed into
  the chat, tool activity, setup/install progress.
* Memory/outputs/inbox under `agents/<name>/`; the home is copied into the
  Space before a turn and back after it; secrets are refused.
* The directive protocol: status, steps, approvals, hand-off, login, notify,
  output, done, schedule.
* Custom rules with the four behaviours, locked credential rules, YAML and
  standing instructions.
* Routines: daily, weekly and every-N-minutes, fired while the app runs.
* Approvals and notifications across bots.
* The computer pane: live JPEG frames, the bot's pointer, take-over with
  click/double-click/scroll/type/key, open in a separate window (PiP).
* Pause, resume, reset, activity, outputs, scheduled, approvals, memory and
  rules screens.

## Known differences

The Linux port keeps the same limits as the sample where it can, and drops
features that depend on macOS or Cua's signed app:

* **Keyvault saved sign-ins** are not available. The sign-in card tells you to
  take over the bot's computer and type the password yourself; "I'm signed in"
  resumes the bot.
* **Host access** (`cua host`, "use this Mac") is not ported.
* **Teleport** is not ported.
* **iPhone app** is not ported. Picture-in-picture opens a small browser
  window with the same live screen.
* **System notifications** use the browser Notification API when granted;
  otherwise they stay in the window.
* **Rules are instructions, not enforcement** — the harness auto-approves its
  own tool calls inside the Space, exactly like the macOS sample.
* **Routines fire while the backend runs**, not from a launchd agent.
* **Cua Volume is a local folder** (the sample's `LocalVolume`), not the
  daemon's synchronized Volume.

## Layout

```
cua-bots-linux/
  cua_bots/
    models.py        dataclasses/enums: Bot, ChatMessage, BotTask, Approval, rules
    directives.py    the [[...]] parser and the bot's standing instructions
    rules.py         action classes and the rule engine
    volume.py        Volume layout + secret scanner
    engine.py        Cua Spaces: provision, agent_start, events, checkpoint, input
    store.py         app state and the run loop
    scheduler.py     the routine clock
    sidecar.py       host Ollama in a Docker sidecar on the bridge
    model_gateway.py OpenAI-compatible gateway for a host model
    server.py        FastAPI + WebSocket + static UI
  web/               React UI (Vite)
    src/koala.jsx    the SVG koala, moods and animations
    src/views.jsx    sidebar, chat, computer, profile, scheduled, approvals, outputs
  electron/          optional desktop shell
  tests/             core and store tests
```

## Tests

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
(cd web && npm run build)
```

## License

FSL-1.1-MIT, the same licence as the macOS sample. The Cua SDK and CLI are MIT.
