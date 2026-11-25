#!/usr/bin/env bash
# Local builds and testing only. Builds the API image and pushes it as
# :latest (or the tag you pass). It does not deploy anything and does not run
# Terraform. Production runs the tag in terraform/production.auto.tfvars.
# Releases go through the Build image workflow (docs/deployment.md), which is
# the only thing that pushes commit-SHA tags.
# Infrastructure applies go through GitHub Actions (.github/workflows/deploy.yml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_TAG="${1:-latest}"
if [[ "$IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Commit-SHA tags are pushed only by the Build image workflow (see docs/deployment.md)." >&2
    exit 1
fi
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
echo "Image pushed. This script is for local builds and testing; it does not deploy."
echo "Production runs the tag in terraform/production.auto.tfvars."
echo "To release, use the Build image workflow (docs/deployment.md)."
