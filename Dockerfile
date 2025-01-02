FROM python:3.13-slim

WORKDIR /app

RUN mkdir -p /app/data /app/backups

RUN pip install lxmfy-news-bot

VOLUME ["/app/data", "/app/backups"]

WORKDIR /app/data

CMD ["lxmfy-news-bot"]