FROM node:22-bookworm-slim

ENV NODE_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PORT=3000
ENV BACKEND_PORT=8000
ENV API_PROXY_TARGET=http://127.0.0.1:8000
ENV INTERNAL_API_BASE_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_API_BASE_URL=/api

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-venv \
  && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN python3 -m venv /app/.venv \
  && /app/.venv/bin/pip install --upgrade pip \
  && /app/.venv/bin/pip install -r backend/requirements.txt

COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci

COPY backend backend
COPY frontend frontend
COPY docker/start.sh docker/start.sh

RUN chmod +x docker/start.sh \
  && cd frontend \
  && npm run build \
  && npm prune --omit=dev

EXPOSE 3000

CMD ["./docker/start.sh"]
