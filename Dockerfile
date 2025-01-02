FROM python:3.13-slim

WORKDIR /app

# Create directories for data persistence
RUN mkdir -p /app/data /app/backups /root/.reticulum

# Install the package
RUN pip install lxmfy-news-bot

# Set volumes for data persistence
VOLUME ["/app/data", "/app/backups", "/root/.reticulum"]

# Set environment variables
ENV DATA_DIR=/app/data \
    BACKUP_DIR=/app/backups

WORKDIR /app/data

CMD ["lxmfy-news-bot"]