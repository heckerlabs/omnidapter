FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy workspace definition and source
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/omnidapter-server/ apps/omnidapter-server/

# Install production dependencies for server package and set up non-root user
RUN uv sync --frozen --no-dev --package omnidapter-server \
 && useradd --system --create-home --home-dir /home/appuser --shell /bin/false appuser \
 && mkdir -p /home/appuser/.cache/uv \
 && chown -R appuser:appuser /app /home/appuser

ENV HOME=/home/appuser
ENV UV_CACHE_DIR=/home/appuser/.cache/uv

USER appuser

# Allow runtime host/port override via HOST and PORT
EXPOSE 8000

CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn omnidapter_server.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"]
