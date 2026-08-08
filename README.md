# Yahoo Mass Dork Parser Telegram Bot

High-throughput Telegram bot that accepts mass dork queries via `.txt` file upload,
scrapes URLs from Yahoo search results at **1,000+ URLs/sec**, filters out
professional/major websites, and returns clean URLs as messages + downloadable `.txt` file.

## Features

- 📁 **Mass dork processing** — upload `.txt` file with one dork per line (up to 500 dorks)
- ⚡ **1k URLs/sec target** — no rate limiter, 300 concurrent requests, 50 parallel dorks
- 🔒 **TLS fingerprint rotation** — `curl_cffi` impersonates 15+ browser profiles (Chrome, Firefox, Safari, Edge)
- 🔄 **Weighted proxy pool** — health-scored, auto-evict dead proxies, background re-probing
- 🎭 **User-Agent rotation** — 50+ realistic browser UAs
- 🚫 **Block detection** — instant retry on 429/403/503 with new identity (no backoff)
- 📄 **Page selection** — `--pages N` (1-60) for both single and mass mode
- 📊 **Live throughput metrics** — URLs/sec, req/sec, success rate during batch
- 📥 **Results as file** — full results sent as downloadable `.txt` Telegram document
- 🧹 **URL filter pipeline** — 200+ domain blocklist + subdomain matching + path filter

## Quick Start

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Set bot token
cp .env.example .env
# Edit .env: TELEGRAM_BOT_TOKEN=your_token_here

# 3. (Optional) Add proxies
echo "ip:port:user:pass" >> data/proxies.txt

# 4. Run
python -m src.main
```

## Usage

### Single Dork Search
```
/dork site:example.com "gift card" --pages 30
/dork inurl:login --pages 60
```

### Mass Dork Mode
1. Create a `.txt` file with one dork per line:
```
site:example.com "gift card"
inurl:login site:*.com
intitle:"index of" "parent directory"
```
2. Upload it to the bot chat
3. Optional: add caption `--pages 45` to set pages per dork
4. Bot processes all dorks in parallel and returns results + `.txt` file

### Commands
| Command | Description |
|---------|-------------|
| `/dork <query> [--pages N]` | Single dork search (N=1-60, default 10) |
| `/mass` | Mass mode instructions |
| `/status` | Bot + proxy health + throughput config |
| `/help` | Help message |

## Configuration

Edit `config.yaml` for concurrency, proxy, and throughput settings.

## Requirements
- Python 3.11+
- 500+ working proxies for full 1k URLs/sec throughput
- Telegram bot token from @BotFather

## License
MIT
