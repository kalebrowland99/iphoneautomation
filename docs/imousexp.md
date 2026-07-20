# iMouseXP reference (read before changing SDK integration)

Use this doc when editing device control, actions, album/keyboard/mouse APIs, or anything that calls `imouse_xp`.

## Official documentation (check first)

| Topic | URL |
|-------|-----|
| Python library overview | https://doc.some3c.com/iphone-farm-setup/xp-api-documentation/python-library |
| Python library (`.md` for agents) | https://doc.some3c.com/iphone-farm-setup/xp-api-documentation/python-library.md |
| iMouse XP product / kernel | https://doc.some3c.com/iphone-farm-setup/imouse-xp-new-version |

When unsure about parameters, behavior, or error codes: **fetch the relevant doc page** (or use `?ask=` on `.md` URLs) before guessing.

## Installed SDK source (ground truth)

Package: `imouse_xp` in `.venv/Lib/site-packages/imouse_xp/`

| API area | File |
|----------|------|
| Mouse / swipe / keys | `api/mouse_api.py` |
| Screenshots / OCR / find-text | `api/pic_api.py` |
| Album upload/clear | `api/shortcut_api.py` |
| Devices / AirPlay | `api/device_api.py` |
| Endpoint constants | `models/model_utils.py` → `FunConstants` |
| Success check | `api/imouse_api.py` → `is_success()` |

Read method docstrings and **required positional args** before wrapping an API in our code.

## This project's wrapper layer

| Layer | Path |
|-------|------|
| Primary SDK wrapper | `src/imouse_farm/controller/device_controller.py` |
| Action types | `src/imouse_farm/actions/engine.py` |
| Device discovery / AirPlay | `src/imouse_farm/devices/manager.py` |

New iMouse features should be added to `DeviceController` first, then exposed via `ActionType` in the action engine.

## Known iMouseXP constraints (from production use)

- **`mouse_swipe`**: `direction` is **required** (positional), even when using `sx/sy/ex/ey` coordinates.
- **Drag while held**: use `mouse_down` → stepped `mouse_move` → `mouse_up`. Do not call `mouse_swipe` after `mouse_down`; swipe is its own full gesture and releases at the start.
- **`shortcut_album_upload`**: `files` must be **absolute Windows paths** the iMouse kernel can read.
- **`pic_find_text`**: on-device OCR for tapping UI labels (preferred over PC-side Tesseract for live taps).
- **`key_sendkey`** (`/key/sendkey`): `key=` for text; `fn_key=` for hotkeys. iMouseXP console buttons map to `fn_key` strings — **App** = `AppSwitch`, **Home** = `WIN+h` (this project also accepts `home`).
- **Responses**: check `response.status == 200` and `response.data.code == 0` via `is_success()`.
- **`kill_app`**: `fn_key=AppSwitch`, then swipe up **5 times** from center card `(301, 703)` → `(301, 100)` (~406×720).
- **AirPlay / cast**: start mirroring via Control Bar UI (`batch.cast_ui` / `ensure_cast_via_control_bar`). Do **not** use `device_airplay_connect` for casting. Disconnect still uses `device_airplay_disconnect`.

## Change checklist

Before merging iMouse-related changes:

1. Read the matching method in `imouse_xp/api/*.py`.
2. Cross-check with Some3C docs if behavior is non-obvious.
3. Wire through `DeviceController` with logging and `_error_message()` on failure.
4. Add or update a **Debug** test in `src/imouse_farm/dashboard/test_actions.py` when adding user-visible behavior.
