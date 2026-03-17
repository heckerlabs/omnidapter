FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml .

# Install dependencies (excluding local dev sources — use published packages)
RUN uv pip install --system .

# Copy source
COPY src/ src/

# Cloud Run listens on PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

CMD uvicorn omnidapter_hosted.main:app --host 0.0.0.0 --port $PORT
