# API image when Render builds from repository root (Dockerfile also in backend/)
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY scripts/docker-start.sh /docker-start.sh
RUN chmod +x /docker-start.sh

ENV PORT=8000
EXPOSE 8000

CMD ["/docker-start.sh"]
