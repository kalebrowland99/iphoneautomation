# iMouse Farm

Multi-device iPhone orchestration platform built directly on the **iMouseXP Python SDK** (`imouse-xp`). Manages 1–100 devices simultaneously with screenshot-driven, state-based automation.

> **No GUI automation.** This project does not control the Windows iMouseXP desktop UI, use screen coordinates on your monitor, or depend on PyAutoGUI. All device communication goes through the official SDK.

**USB board vs AirPlay:** the hardware board can tap/type/Home/Control Bar **without** Screen Mirroring; screenshots and vision need AirPlay. See [docs/imouse-usb-vs-airplay.md](docs/imouse-usb-vs-airplay.md) (refs: [iosautot.com](https://www.iosautot.com/#视频教程), [Some3C](https://doc.some3c.com/iphone-farm-setup/xp-api-documentation/python-library)).

**Daily 5 AM start:** Windows Task Scheduler — same idea as androidautomationig’s LaunchAgent. See [docs/morning-start.md](docs/morning-start.md).

**Telegram alerts:** android-style `config/telegram.yml` — see [docs/telegram.md](docs/telegram.md).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Dashboard                         │
│         (real-time WebSocket, device status, screenshots)    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Workflow Engine                            │
│   Screenshot → Analyze → State → Action → Verify → Repeat   │
└──┬────────────┬──────────────┬──────────────┬───────────────┘
   │            │              │              │
┌──▼───┐  ┌─────▼─────┐  ┌────▼────┐  ┌──────▼──────┐
│Vision│  │  Popup    │  │ Action  │  │   Device    │
│Layer │  │  Manager  │  │ Engine  │  │   Manager   │
└──┬───┘  └───────────┘  └────┬────┘  └──────┬──────┘
   │                          │              │
   │                   ┌──────▼──────────────▼──┐
   │                   │   DeviceController    │
   │                   │  (imouse-xp SDK only) │
   │                   └──────────┬────────────┘
   │                              │
   │                   ┌──────────▼────────────┐
   │                   │   iMouseXP Server      │
   │                   │   (localhost:9911)     │
   └───────────────────┤   + iMouse Hardware    │
                       └───────────────────────┘
```

### Core modules

| Module | Purpose |
|--------|---------|
| `controller/device_controller.py` | **Single SDK entry point** — enumerate, tap, swipe, screenshot, OCR |
| `vision/` | Pluggable vision providers (OpenCV+Tesseract v1, local model v2 stub) |
| `popups/manager.py` | Detect permission/update/login/confirmation dialogs |
| `workflows/engine.py` | YAML-driven screenshot-first automation |
| `actions/engine.py` | Per-device async action queues (20–50 device scale) |
| `devices/manager.py` | Device discovery, reconnect, state tracking |
| `database/` | SQLite persistence for all device state |

## Requirements

- Python 3.12+
- [iMouseXP hardware + server](https://www.iosautot.cn/python-xp/) running locally
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (optional, for OCR)
- Template images in `config/templates/`

## Setup

```bash
# Install the package
pip install -e ".[dev]"

# Install the official iMouseXP Python SDK
pip install imouse-xp

# Install Tesseract (Windows)
# Download from https://github.com/UB-Mannheim/tesseract/wiki
# Then set analysis.tesseract_cmd in config/config.yaml

# Start iMouseXP server, then launch the orchestrator
imouse-farm -c config/config.yaml
```

Dashboard: http://localhost:8080

## Configuration

Main config: `config/config.yaml`

```yaml
imouse:
  host: "localhost"
  port: 9911
  mode: "websocket"

vision:
  provider: "opencv_tesseract"   # or "local_model" (v2 stub)

device_groups:
  default:
    workflow: "warmup"
```

Workflows: `config/workflows/*.yaml` — no code changes needed to add workflows.

Popups: `config/workflows/popups.yaml` — dialog detection rules.

Screen states: `config/workflows/screen_states.yaml` — template + OCR state definitions.

## Workflow example (warmup)

```yaml
name: warmup
loop: true
steps:
  - type: screenshot
    name: capture
  - type: analyze
    name: analyze
  - type: determine_state
    name: set_state
  - type: check_popups
    name: handle_popups
  - type: execute_action
    name: swipe
    requires_analysis: true
    action:
      type: swipe
      direction: up
  - type: wait_random
    name: delay
    min_seconds: 2
    max_seconds: 5
```

### Workflow step types

| Step | Description |
|------|-------------|
| `screenshot` | Capture via SDK |
| `analyze` | Run vision provider |
| `determine_state` | Map analysis → device state |
| `check_popups` | Detect/handle dialogs; pause on unknown |
| `execute_action` | SDK action (requires prior analysis) |
| `verify` | Confirm template/OCR match |
| `wait` / `wait_random` | Timed delay |

### Action types (all via SDK)

- `tap_detection` — tap on vision-detected element (preferred)
- `tap` — coordinate tap on device screen (discouraged without analysis)
- `swipe`, `long_press`, `text_input`
- `home`, `lock`, `unlock`, `launch_app`, `close_app`

## Device states

| State | Meaning |
|-------|---------|
| `IDLE` | Known idle screen (e.g. home) |
| `ACTIVE` | App running / interaction in progress |
| `WAITING` | Lock screen, popup, or blocking dialog |
| `ERROR` | Repeated failures or frozen device |
| `UNKNOWN_SCREEN` | Unrecognized screen — workflow pauses |
| `DISCONNECTED` | Device offline |

## Database schema

SQLite at `data/imouse_farm.db`:

**devices** — `id`, `name`, `current_state`, `last_seen_at`, `last_action`, `workflow_name`, `error_count`, ...

**screenshots** — metadata for captured images

**state_transitions** — full state change history

**action_history** — every SDK action with timing

**error_logs** — popups, failures, escalations

**workflow_runs** — active/completed workflow tracking

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/devices` | List all devices |
| GET | `/api/devices/{id}` | Device detail |
| GET | `/api/devices/{id}/screenshot` | Latest screenshot image |
| POST | `/api/devices/{id}/screenshot` | Capture screenshot |
| POST | `/api/devices/{id}/actions/execute` | Execute SDK action |
| GET | `/api/workflows` | List workflow definitions |
| POST | `/api/workflows/start` | Start workflow on device |
| POST | `/api/workflows/stop` | Stop workflow |
| WS | `/ws` | Real-time event stream |

## Notifications

Discord webhooks and Telegram bots supported. Configure in `config/config.yaml`.

Events: device disconnect, unknown screen, repeated failures, workflow completion, popup detection.

## Testing

```bash
pytest tests/ -v
```

## Project structure

```
automation/
├── config/
│   ├── config.yaml
│   ├── templates/          # Screenshot template images (.png)
│   └── workflows/          # YAML workflow definitions
├── src/imouse_farm/
│   ├── controller/         # DeviceController (SDK layer)
│   ├── vision/             # Pluggable vision providers
│   ├── popups/             # PopupManager
│   ├── workflows/          # Workflow engine
│   ├── actions/            # Per-device action queues
│   ├── devices/            # Device manager
│   ├── screenshots/        # Screenshot service
│   ├── dashboard/          # FastAPI + web UI
│   └── database/           # SQLite repository
└── tests/
```

## Scaling to 20–50 devices

- Each device has an independent async action queue and workflow runner
- One device failure does not stop others
- DeviceController uses `asyncio.to_thread` for non-blocking SDK calls
- SQLite tracks per-device state independently

## License

MIT
