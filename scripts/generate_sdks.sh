#!/usr/bin/env bash
# Generate TypeScript and Python SDKs from the OpenAPI spec.
# Requires Docker. Run from the repo root.
set -euo pipefail

SPEC="$(pwd)/openapi/openapi.json"
PY_OUT="$(pwd)/omnidapter-sdk/omnidapter_sdk"
TS_OUT="$(pwd)/client/packages/sdk/src"
IMAGE="openapitools/openapi-generator-cli:v7.11.0"
USER_ARG="--user $(id -u):$(id -g)"
PY_TMP="$(mktemp -d)"
TS_TMP="$(mktemp -d)"

echo "→ Exporting OpenAPI spec from omnidapter-server..."
uv run python scripts/export_openapi.py

echo "→ Generating Python SDK..."
docker run --rm $USER_ARG \
  -v "$SPEC":/spec.json:ro \
  -v "$PY_TMP":/out \
  "$IMAGE" generate \
  -i /spec.json \
  -g python \
  -o /out \
  --skip-validate-spec \
  --additional-properties=packageName=omnidapter_sdk,projectName=omnidapter-sdk,library=urllib3

# Sync generated source into place, preserving handwritten client.py.
rsync -a --delete --exclude=client.py --exclude=api_client.py "$PY_TMP/omnidapter_sdk/" "$PY_OUT/"
rm -rf "$PY_TMP"

echo "→ Generating TypeScript SDK..."
docker run --rm $USER_ARG \
  -v "$SPEC":/spec.json:ro \
  -v "$TS_TMP":/out \
  "$IMAGE" generate \
  -i /spec.json \
  -g typescript-fetch \
  -o /out \
  --skip-validate-spec \
  --additional-properties=npmName=@omnidapter/sdk,supportsES6=true,withSeparateModelsAndApi=true,apiPackage=apis,modelPackage=models

# Sync generated source into place, preserving handwritten files.
mkdir -p "$TS_OUT"
rsync -a --delete --exclude=OmnidapterClient.ts --exclude=index.ts "$TS_TMP/src/" "$TS_OUT/"
rm -rf "$TS_TMP"

echo "✓ SDKs generated."
echo "  Python: $PY_OUT"
echo "  TypeScript: $TS_OUT"
