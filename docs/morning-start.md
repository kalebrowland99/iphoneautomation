# Daily 5:00 AM start (Labely + chained ValCoin)

Same pattern as [androidautomationig](https://github.com/kalebrowland99/androidautomationig) morning start:

| androidautomationig (Mac) | This farm (Windows) |
|---------------------------|---------------------|
| `tools/morning_start_bots.sh` | `scripts/morning_start_bots.ps1` |
| `tools/install_morning_start.sh` (LaunchAgent 5:00) | `scripts/install_morning_start.ps1` (Task Scheduler 5:00) |

## Install (once)

```powershell
cd C:\Users\Kaleb\Desktop\automation
powershell -ExecutionPolicy Bypass -File scripts\install_morning_start.ps1
```

Creates task `iMouseFarm\MorningStart` daily at **05:00** local time.

## What it does

1. Ensures `http://127.0.0.1:8080` is healthy (starts `run.ps1` if not)
2. `POST /api/slideshow/generate-and-run` for **labely** with all farm slots
3. Passes the same slots as `valcoin_slots` so ValCoin chains after Labely (`chain_valcoin_after_labely`)

## Test

```powershell
powershell -ExecutionPolicy Bypass -File scripts\morning_start_bots.ps1
# or
schtasks /Run /TN "iMouseFarm\MorningStart"
```

Logs: `%LOCALAPPDATA%\iMouseFarm\logs\morning_start.log`

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_morning_start.ps1 -Uninstall
```

## Telegram (same as androidautomationig)

Android uses `accounts/<name>/telegram.yml` with `telegram-api-token` / `telegram-chat-id`.  
This farm uses one file: `config/telegram.yml` (gitignored).

```powershell
copy config\telegram.yml.example config\telegram.yml
# edit token + chat id, then:
powershell -ExecutionPolicy Bypass -File scripts\install_morning_start.ps1
```

Installer copies creds to `%LOCALAPPDATA%\iMouseFarm\telegram.yml`. Morning start texts you on success/fail. Farm server also picks up the same file for disconnect / workflow alerts.

## Notes

- PC must be on (or wake-capable) at 5 AM.
- Leave iMouseXP kernel running; Control Bar cast needs USB + Wi‑Fi when each phone starts.
- Change time: `install_morning_start.ps1 -Time "05:30"`
