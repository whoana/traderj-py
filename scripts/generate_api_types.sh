#!/usr/bin/env bash
# Generate TypeScript types from OpenAPI schema
# Usage: ./scripts/generate_api_types.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OPENAPI_SOURCE="${PROJECT_ROOT}/api/openapi-draft.yaml"
OUTPUT_FILE="${PROJECT_ROOT}/dashboard/src/types/api.ts"

echo "Generating TypeScript types from OpenAPI schema..."
echo "  Source: ${OPENAPI_SOURCE}"
echo "  Output: ${OUTPUT_FILE}"

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT_FILE")"

# Generate types using openapi-typescript
npx openapi-typescript "$OPENAPI_SOURCE" -o "$OUTPUT_FILE"

echo "Done! Types written to ${OUTPUT_FILE}"
