# Stage 1: Build connect-ui
FROM node:20-alpine AS connect-ui-builder
WORKDIR /build

# Copy workspace manifests (all members needed for npm workspace resolution)
COPY client/package.json client/package-lock.json client/tsconfig.base.json ./
COPY client/apps/connect-ui/package.json apps/connect-ui/package.json
COPY client/apps/connect-demo/package.json apps/connect-demo/package.json
COPY client/packages/connect-sdk/package.json packages/connect-sdk/package.json

RUN npm ci --workspace=@heckerlabs/omnidapter-connect-ui

COPY client/apps/connect-ui/ apps/connect-ui/
RUN npm run build -w @heckerlabs/omnidapter-connect-ui

# Stage 2: Server
FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy workspace definition and source
COPY pyproject.toml uv.lock ./
COPY omnidapter-core/ omnidapter-core/
COPY ./omnidapter-server/ ./omnidapter-server/
COPY ./omnidapter-hosted/ ./omnidapter-hosted/

# Install production dependencies for hosted package and set up non-root user
RUN uv sync --frozen --no-dev --package omnidapter-hosted \
 && useradd --system --create-home --home-dir /home/appuser --shell /bin/false appuser \
 && mkdir -p /home/appuser/.cache/uv \
 && chown -R appuser:appuser /app /home/appuser

# Copy connect-ui static files (world-readable, appuser can serve them)
COPY --from=connect-ui-builder /build/apps/connect-ui/dist /app/connect-ui-dist

ENV HOME=/home/appuser
ENV UV_CACHE_DIR=/home/appuser/.cache/uv

# Run as non-root user
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn omnidapter_hosted.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"]
