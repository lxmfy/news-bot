# news-bot

A LXMFy News Bot for the [Reticulum Network](https://github.com/markqvist/Reticulum). Get your daily RSS full-text feeds. 

## Installation

```bash
pip install lxmfy-news-bot
```

or

```bash
pipx install lxmfy-news-bot
```

The bot will store its data in `~/.local/share/lxmfy-news-bot/` 


## Usage

```bash
lxmfy-news-bot
```

## Docker

```bash
docker run -d \
  -v /path/to/data:/app/data \
  -v /path/to/backups:/app/backups \
  -v /path/to/.reticulum:/root/.reticulum \
  -e BOT_NAME="My News Bot" \
  -e BOT_ADMINS="admin1hash,admin2hash" \
  ghcr.io/lxmfy/news-bot:latest
```


