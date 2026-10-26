# Hosted-demo image: static frontend plus the local API.
# Build from the repo root: docker build -t qalam .
# The stroke weights are in the image. Whisper downloads on first transcription.

FROM node:22-bookworm-slim AS web
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY --from=web /src/dist /app/frontend/dist
ENV QALAM_STATIC=/app/frontend/dist
WORKDIR /app/backend
EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "qalam.main:app", "--host", "0.0.0.0", "--port", "8000"]
