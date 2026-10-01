#!/usr/bin/env bash
# Build and push the API image. This script does not run Terraform.
# Infrastructure applies go through GitHub Actions (.github/workflows/deploy.yml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_TAG="${1:-latest}"
IMAGE_NAME="rg.nl-ams.scw.cloud/candidates-db/candidates-api:${IMAGE_TAG}"

echo "==> Logging in to Scaleway Container Registry..."
scw registry login

echo "==> Building ${IMAGE_NAME}..."
docker build --platform linux/amd64 \
    -t "$IMAGE_NAME" \
    -f "$PROJECT_DIR/container/Dockerfile" \
    "$PROJECT_DIR"

echo "==> Pushing ${IMAGE_NAME}..."
docker push "$IMAGE_NAME"

echo ""
echo "Image pushed. The running container keeps its current image until a"
echo "GitHub Actions deploy replaces scaleway_container.api."
