FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy workspace definition and source
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/omnidapter-server/ apps/omnidapter-server/

# Install production dependencies and set up non-root user
RUN uv sync --frozen --no-dev \
 && useradd --system --no-create-home --shell /bin/false appuser \
 && chown -R appuser:appuser /app

USER appuser

# Cloud Run and standard deployments both respect PORT
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "omnidapter_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
