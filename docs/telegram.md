# Telegram alerts (androidautomationig-style)

Same pattern as [androidautomationig](https://github.com/kalebrowland99/androidautomationig):

| androidautomationig | This farm |
|---------------------|-----------|
| `accounts/<name>/telegram.yml` | `config/telegram.yml` |
| Copied to `~/Library/Application Support/GramAddict/telegram/` | Copied to `%LOCALAPPDATA%\iMouseFarm\telegram.yml` |
| Morning script `send_telegram` | `scripts/morning_start_bots.ps1` → `Send-Telegram` |

## Keys (compatible)

```yaml
telegram-api-token: '123456:ABC-DEF...'
telegram-chat-id: '5965301633'
telegram-alerts: true
```

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) → copy token  
2. Message the bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy your chat id  
3. Or reuse the token/chat from an android `accounts/*/telegram.yml`  

```powershell
cd C:\Users\Kaleb\Desktop\automation
copy config\telegram.yml.example config\telegram.yml
# edit config\telegram.yml with real token + chat id
powershell -ExecutionPolicy Bypass -File scripts\install_morning_start.ps1
```

`config/telegram.yml` is gitignored. After install, the farm server loads it automatically (disconnect / workflow notifications) and morning start texts you on success or failure.

Optional env fallback: `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.
