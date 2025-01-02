# news-bot

Get your daily RSS full-text feeds. 

## Installation

```bash
pip install lxmfy-news-bot
```

or

```bash
pipx install lxmfy-news-bot
```

## Usage

```bash
lxmfy-news-bot
```

## Docker

```bash
docker run -d \
  -v /path/to/data:/app/data \
  -v /path/to/backups:/app/backups \
  -e BOT_NAME="My News Bot" \
  -e BOT_ADMINS="admin1hash,admin2hash" \
  lxmfy-news-bot
```




