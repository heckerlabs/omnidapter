#!/usr/bin/env bash
# Generate SDKs from openapi/openapi.json using Docker.
# Run from the repo root. To also export the spec first, run:
#   uv run python scripts/export_openapi.py && bash scripts/generate_sdks.sh
#
# Usage: generate_sdks.sh [python|typescript]
#   No argument: generate both SDKs.
set -euo pipefail

TARGET="${1:-all}"
SPEC="$(pwd)/openapi/openapi.json"
PY_OUT="$(pwd)/omnidapter-sdk/omnidapter_sdk"
TS_OUT="$(pwd)/client/packages/sdk/src"
IMAGE="openapitools/openapi-generator-cli:v7.11.0"
USER_ARG="--user $(id -u):$(id -g)"

generate_python() {
  local tmp
  tmp="$(mktemp -d)"
  echo "→ Generating Python SDK..."
  docker run --rm $USER_ARG \
    -v "$SPEC":/spec.json:ro \
    -v "$tmp":/out \
    "$IMAGE" generate \
    -i /spec.json \
    -g python \
    -o /out \
    --skip-validate-spec \
    --additional-properties=packageName=omnidapter_sdk,projectName=omnidapter-sdk,library=urllib3
  rsync -a --delete --exclude=client.py --exclude=api_client.py "$tmp/omnidapter_sdk/" "$PY_OUT/"
  rm -rf "$tmp"
  echo "✓ Python SDK: $PY_OUT"
}

generate_typescript() {
  local tmp
  tmp="$(mktemp -d)"
  echo "→ Generating TypeScript SDK..."
  docker run --rm $USER_ARG \
    -v "$SPEC":/spec.json:ro \
    -v "$tmp":/out \
    "$IMAGE" generate \
    -i /spec.json \
    -g typescript-fetch \
    -o /out \
    --skip-validate-spec \
    --additional-properties=npmName=@omnidapter/sdk,supportsES6=true,withSeparateModelsAndApi=true,apiPackage=apis,modelPackage=models
  mkdir -p "$TS_OUT"
  rsync -a --delete --exclude=/OmnidapterClient.ts --exclude=/index.ts "$tmp/src/" "$TS_OUT/"
  rm -rf "$tmp"
  echo "✓ TypeScript SDK: $TS_OUT"
}

case "$TARGET" in
  python)     generate_python ;;
  typescript) generate_typescript ;;
  all)        generate_python && generate_typescript ;;
  *)          echo "Usage: $0 [python|typescript]" >&2; exit 1 ;;
esac
