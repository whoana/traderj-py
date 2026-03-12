#!/usr/bin/env bash
# Generate TypeScript types from FastAPI OpenAPI schema.
#
# Usage:
#   ./scripts/generate-types.sh [API_URL]
#
# Default API_URL: http://localhost:8000
# Output: dashboard/src/types/api-generated.ts

set -euo pipefail

API_URL="${1:-http://localhost:8000}"
OPENAPI_URL="${API_URL}/openapi.json"
OUTPUT="dashboard/src/types/api-generated.ts"

echo "Fetching OpenAPI schema from ${OPENAPI_URL}..."
curl -sf "${OPENAPI_URL}" -o /tmp/traderj-openapi.json

if [ ! -s /tmp/traderj-openapi.json ]; then
    echo "Error: Failed to fetch OpenAPI schema. Is the API running?"
    exit 1
fi

echo "Generating TypeScript types..."
npx openapi-typescript /tmp/traderj-openapi.json -o "${OUTPUT}"

echo "Types generated: ${OUTPUT}"
echo "Done."
