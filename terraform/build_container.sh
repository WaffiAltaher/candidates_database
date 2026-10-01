#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_TAG="${1:-latest}"

cd "$SCRIPT_DIR"

# Step 1: Ensure registry namespace exists
echo "==> Creating container registry (if needed)..."
terraform apply -target=scaleway_registry_namespace.main -auto-approve

REGISTRY_ENDPOINT=$(terraform output -raw container_registry_endpoint)
REGISTRY_HOST=$(echo "$REGISTRY_ENDPOINT" | cut -d'/' -f1)
IMAGE_NAME="${REGISTRY_ENDPOINT}/candidates-api:${IMAGE_TAG}"

# Step 2: Docker login to Scaleway registry
echo "==> Logging in to registry: ${REGISTRY_HOST}..."
scw registry login

# Step 3: Build image (build context = project root, Dockerfile in container/)
echo "==> Building Docker image: ${IMAGE_NAME}..."
docker build --platform linux/amd64 \
    -t "$IMAGE_NAME" \
    -f "$PROJECT_DIR/container/Dockerfile" \
    "$PROJECT_DIR"

# Step 4: Push image
echo "==> Pushing image..."
docker push "$IMAGE_NAME"

# Step 5: Deploy everything
echo "==> Deploying infrastructure..."
terraform apply -auto-approve

# Step 6: Show the container URL
CONTAINER_URL=$(terraform output -raw container_url)
echo ""
echo "==> Container deployed at: https://${CONTAINER_URL}"
echo ""
echo "Update frontend/app.js API_BASE to: https://${CONTAINER_URL}"
echo "Then upload frontend:  s3cmd put frontend/*.html frontend/*.js s3://candidates.ittopia.nl/ --acl-public"
