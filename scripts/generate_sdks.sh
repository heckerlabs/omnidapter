#!/usr/bin/env bash
# Generate TypeScript and Python SDKs from the OpenAPI spec.
# Requires Docker. Run from the repo root.
set -euo pipefail

SPEC="$(pwd)/openapi/openapi.json"
PY_OUT="$(pwd)/omnidapter-sdk/omnidapter_sdk"
TS_OUT="$(pwd)/client/packages/sdk/src"
IMAGE="openapitools/openapi-generator-cli:latest"

echo "→ Exporting OpenAPI spec from omnidapter-server..."
uv run python scripts/export_openapi.py

echo "→ Generating Python SDK..."
docker run --rm \
  -v "$SPEC":/spec.json:ro \
  -v /tmp/oag-python:/out \
  "$IMAGE" generate \
  -i /spec.json \
  -g python \
  -o /out \
  --skip-validate-spec \
  --additional-properties=packageName=omnidapter_sdk,projectName=omnidapter-sdk,library=urllib3

# Copy only the package source, not setup.py/README/etc.
rm -rf "$PY_OUT"
cp -r /tmp/oag-python/omnidapter_sdk "$PY_OUT"
sudo rm -rf /tmp/oag-python

echo "→ Generating TypeScript SDK..."
docker run --rm \
  -v "$SPEC":/spec.json:ro \
  -v /tmp/oag-typescript:/out \
  "$IMAGE" generate \
  -i /spec.json \
  -g typescript-fetch \
  -o /out \
  --skip-validate-spec \
  --additional-properties=npmName=@omnidapter/sdk,supportsES6=true,withSeparateModelsAndApi=true,apiPackage=apis,modelPackage=models

# Copy only the generated source, not package.json/tsconfig/etc.
rm -rf "$TS_OUT"
cp -r /tmp/oag-typescript/src "$TS_OUT"
sudo rm -rf /tmp/oag-typescript

echo "✓ SDKs generated."
echo "  Python: $PY_OUT"
echo "  TypeScript: $TS_OUT"
