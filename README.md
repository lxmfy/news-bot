# news-bot

[![DeepSource](https://app.deepsource.com/gh/lxmfy/news-bot.svg/?label=active+issues&show_trend=true&token=TmzSjR084Xg7-r03jSZ2WniW)](https://app.deepsource.com/gh/lxmfy/news-bot/)
[![Docker Build and Publish](https://github.com/lxmfy/news-bot/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/lxmfy/news-bot/actions/workflows/docker-publish.yml)

A LXMFy News Bot for the [Reticulum Network](https://github.com/markqvist/Reticulum). Get your daily RSS full-text feeds with instant news access and optional cryptographic signature verification.

## Features

- **Instant News**: Type `news` to get the latest headlines from default feeds immediately
- **RSS Feed Subscriptions**: Subscribe to any RSS feed with full-text extraction
- **Scheduled Updates**: Automatic delivery based on your timezone and preferred schedule
- **Feed Categories**: Pre-configured categories like news, military, cybersecurity, and science
- **Admin Commands**: Database backup/restore, statistics, and user management

## Installation

```bash
pip install lxmfy-news-bot

pipx install lxmfy-news-bot
```

Git:

```bash
pipx install git+https://github.com/lxmfy/news-bot.git
```

The bot will store its data in `~/.local/share/lxmfy-news-bot/` 

## Usage

```bash
lxmfy-news-bot
```

## Configuration

The bot supports various environment variables for customization. See `.env-example` for a complete list of all available configuration options.

### Basic Configuration
- `BOT_NAME`: Bot display name (default: "LXMFy News Bot")
- `BOT_ANNOUNCE`: Announcement interval in seconds (default: 600)
- `BOT_PREFIX`: Command prefix (default: "")
- `BOT_ADMINS`: Comma-separated list of admin hashes

### Security & Signatures
- `BOT_SIGNATURE_VERIFICATION_ENABLED`: Enable cryptographic signature verification (default: false)
- `BOT_REQUIRE_MESSAGE_SIGNATURES`: Reject unsigned messages when verification is enabled (default: false)

### Performance & Limits
- `BOT_RATE_LIMIT`: Messages per minute limit (default: 8)
- `BOT_COOLDOWN`: Cooldown period in seconds (default: 1)
- `BOT_MAX_WARNINGS`: Max warnings before timeout (default: 3)
- `BOT_WARNING_TIMEOUT`: Warning timeout in seconds (default: 300)

### Storage & Data
- `DATA_DIR`: Data directory path (default: platform-specific)
- `BACKUP_DIR`: Backup directory path (default: data/backups)
- `CONFIG_DIR`: Configuration directory path (default: newsbot/)
- `FEEDS_CONFIG`: Custom feeds YAML file path

## Docker

```bash
docker run -d \
  -v /path/to/data:/app/data \
  -v /path/to/backups:/app/backups \
  -v /path/to/.reticulum:/root/.reticulum \
  -e BOT_NAME="My News Bot" \
  -e BOT_ADMINS="admin1hash,admin2hash" \
  -e BOT_SIGNATURE_VERIFICATION_ENABLED="true" \
  ghcr.io/lxmfy/news-bot:latest
```


