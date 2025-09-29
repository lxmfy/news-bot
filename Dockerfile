ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-alpine

LABEL org.opencontainers.image.source="https://github.com/lxmfy/news-bot"
LABEL org.opencontainers.image.description="Get your daily RSS full-text feeds."
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.authors="LXMFy"

WORKDIR /app

RUN mkdir -p /app/data /app/backups /root/.reticulum

COPY pyproject.toml poetry.lock /app/
RUN pip install --no-cache-dir poetry && poetry install --no-root
COPY newsbot /app/newsbot
RUN poetry install --no-root

VOLUME ["/app/data", "/app/backups", "/root/.reticulum"]

ENV DATA_DIR=/app/data \
    BACKUP_DIR=/app/backups

WORKDIR /app/data

CMD ["lxmfy-news-bot"]
