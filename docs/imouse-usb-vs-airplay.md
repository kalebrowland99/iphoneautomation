# iMouse USB board vs AirPlay (what works offline)

Quick reference for this farm: what the **USB hardware board** can do without Screen Mirroring, and what still needs **AirPlay cast**.

## Official product / docs

| Source | URL |
|--------|-----|
| iMouse product overview + video tutorials | https://www.iosautot.com/#视频教程 |
| Some3C iMouse XP (install / kernel / console) | https://doc.some3c.com/iphone-farm-setup/imouse-xp-new-version |
| Some3C Python / XP API library | https://doc.some3c.com/iphone-farm-setup/xp-api-documentation/python-library |
| This repo’s SDK wiring notes | [imousexp.md](imousexp.md) |

From the manufacturer ([iosautot.com](https://www.iosautot.com/)):

- iMouse is built on **virtual mouse/keyboard hardware** — you need that board for HID control.
- **Screen transfer** uses **AirPlay mirroring** (no app on the phone).
- Kernel + console talk to hardware and phones over the XP API (HTTP/WebSocket).

So there are always **two paths**: USB (control) and AirPlay (see the screen).

## Split: USB board vs AirPlay

```
┌─────────────────────┐         Wi‑Fi AirPlay          ┌──────────────┐
│  iPhone             │◄────── mirror frames ─────────►│  PC / kernel │
│                     │                                 │  screenshots │
│  Lightning/USB ─────┼── HID mouse + keyboard ────────►│  OCR/vision  │
│  (iMouse board)     │   works even if NOT casting     │  (need cast) │
└─────────────────────┘                                 └──────────────┘
```

### USB board can do (no cast required)

Works while iMouse device `state == 0` (offline / not mirroring), as long as the board is bound and healthy (`code 16` = hardware not working).

| Capability | Typical API / `fn_key` | Used in this farm for |
|------------|------------------------|------------------------|
| Tap / click | `/mouse/click` | UI taps, Screen Mirroring list |
| Swipe / drag | `/mouse/swipe`, down/move/up | Scrolling, gestures |
| Type text | `/key/sendkey` `key=` | Captions, search |
| Home | `fn_key=home` | Wake / dismiss sheets |
| Unlock / lock | `fn_key=unlock` / `lock` | Wake screen before cast |
| App switcher | `fn_key=AppSwitch` | Kill apps |
| Control Bar | `fn_key=ControlBar` | Open Screen Mirroring UI to cast |
| Mouse reset | `/mouse/reset` | Cursor reset |
| USB restart | `/device/usb/restart` | Recover stuck boards |

**Cast bootstrap** in this project (`batch.cast_ui` / `ensure_cast_via_control_bar`) is entirely USB: wake → Control Bar → taps → wait until AirPlay comes online. It does **not** call `/device/airplay/connect`.

### Needs AirPlay cast (USB alone is not enough)

| Capability | Why |
|------------|-----|
| Screenshot (`/pic/screenshot`) | Frame comes from the mirror stream |
| OCR / find-text / find-image | Same — needs a live image |
| Vision (GPT) on phone UI | We only send screenshots; no frame if offline |
| Watching live preview in console | Mirror session |

Disconnect still uses `/device/airplay/disconnect`. Starting cast uses **Control Bar UI**, not `device_airplay_connect`.

## Practical rules for this farm

1. **Offline automation that only taps** (open Control Bar, dismiss dialogs) → USB is enough.
2. **Anything that “looks” at the screen** (workflows, vision, OCR) → cast first, confirm `state == 1`.
3. If USB returns **硬件无法工作 (code 16)** → fix/restart the board; casting won’t help mouse/keys.
4. If USB works but vision fails → phone isn’t mirroring (or mirror is zombie); re-run Control Bar cast.

## Video tutorials (hardware setup)

Manufacturer video list (chip install, init, file/photo transfer):  
https://www.iosautot.com/#视频教程

Some3C setup / kernel notes:  
https://doc.some3c.com/iphone-farm-setup/imouse-xp-new-version
