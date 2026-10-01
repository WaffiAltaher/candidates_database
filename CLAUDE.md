# CLAUDE.md

## Project Overview

Candidates Database - A CV management and search system deployed as a Scaleway Serverless Container (FastAPI) with a static JS frontend and PostgreSQL database.

## Architecture

```
Route 53 (cv.yourdomain.com) --CNAME--> Scaleway Object Storage (static frontend)
Frontend JS calls a single Scaleway Serverless Container:
  - POST /login         (authentication)
  - GET/POST/PUT/DELETE  (candidates, interviews, verdicts, customers)
  - POST /search        (AI-powered natural language search)
  - POST /upload        (CV PDF upload and processing)
The container connects to Scaleway Serverless SQL Database (PostgreSQL)
```

## Project Structure

```
candidates_database/
├── candidates/              # Core Python package
│   ├── __init__.py
│   ├── helpers.py           # CORS, auth, routing, DB singleton
│   ├── database.py          # Dual SQLite/PostgreSQL support
│   ├── config.py            # Env-var based config
│   ├── llm_client.py        # AISuite wrapper
│   ├── search_engine.py     # NL -> SQL -> results
│   ├── cv_extractor.py      # PDF -> structured data -> DB
│   └── document_processor.py # PDF text extraction
├── container/               # Serverless container (FastAPI)
│   ├── main.py              # FastAPI app — all API routes
│   ├── Dockerfile           # Docker image (python:3.11-slim + uvicorn)
│   └── requirements.txt     # pip dependencies
├── frontend/                # Static HTML + vanilla JS
│   ├── app.js
│   ├── login.html
│   ├── index.html
│   ├── candidate.html
│   ├── search.html
│   └── upload.html
├── terraform/               # Infrastructure as code
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── backend.tf
│   ├── terraform.tfvars     # Secrets (gitignored)
│   ├── terraform.tfvars.example
│   └── build_container.sh   # Build, push, and deploy container
├── dev_server.py            # Local dev server (uvicorn + static files, port 8080)
├── pyproject.toml
└── CLAUDE.md
```

## Development Commands

### Local Development
```bash
# Install dependencies with Poetry
poetry install

# Run local dev server (uses SQLite, no PostgreSQL needed)
poetry run python dev_server.py

# Default login password: admin
# Server runs at http://localhost:8080
```

### Running Tests
```bash
poetry run pytest
```

### Environment Variables

| Variable | Description | Required |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Production only |
| `DATABASE_URL_READONLY` | Read-only PostgreSQL connection string (for search queries) | Production only |
| `DATABASE_PATH` | SQLite file path (default: cvs.db) | Local dev |
| `ANTHROPIC_API_KEY` | API key for the Anthropics provider used by AISuite | Yes |
| `LLM_MODEL` | AISuite model string | No (default: anthropic:claude-sonnet-4-20250514) |
| `LLM_MODEL_FAST` | AISuite model string for faster/cheaper SQL generation | No (default: anthropic:claude-haiku-4-5-20251001) |
| `AUTH_SECRET` | HMAC signing secret for tokens | Yes |
| `AUTH_USERS` | JSON map of username -> SHA-256(password) hash | Yes |
| `ALLOWED_ORIGIN` | CORS allowed origin | Production |
| `LOG_LEVEL` | Logging level | No (default: INFO) |

### Deployment

Infrastructure is managed with Terraform in the `terraform/` directory. The backend runs as a single Scaleway Serverless Container (FastAPI + uvicorn).

**Prerequisites:**
- Terraform >= 0.13
- Docker (for building the container image)
- `scw` CLI installed and configured (`scw init`) — needed for registry login
- **Scaleway provider credentials:** Same as the `scw` CLI — usually `~/.config/scw/config.yaml` (or `SCW_CONFIG_PATH`), or env vars `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, `SCW_DEFAULT_PROJECT_ID`.
- `terraform/terraform.tfvars` configured (copy from `terraform.tfvars.example`)
- **Remote state (S3 backend):** Uses the **AWS** credential chain, not `config.yaml`. `terraform/backend.tf` includes `profile = "scaleway"` — put your Scaleway access key + secret (S3-compatible API) under `[scaleway]` in `~/.aws/credentials`, or change the `profile` value in `backend.tf` to match your profile name. Bucket: `terraform-bucket` — see `terraform/backend.tf`.

#### Deploy everything (one command)

The `build_container.sh` script handles the full flow: create registry, login, build, push, and deploy.

```bash
bash terraform/build_container.sh
```

#### Step-by-step deployment

If you prefer to run each step manually:

**1. Initialize Terraform (first time only):**
```bash
cd terraform
terraform init    # use -migrate-state if moving local state to remote
```

**2. Create the container registry (first time only):**
```bash
terraform apply -target=scaleway_registry_namespace.main
```

**3. Log in to Scaleway Container Registry:**
```bash
scw registry login
```
This authenticates Docker with the Scaleway registry using the credentials from your `scw` CLI profile (`~/.config/scw/config.yaml`). The `scw` CLI must be configured first via `scw init`.

**4. Build the Docker image:**
```bash
# From the project root:
docker build --platform linux/amd64 \
    -t rg.nl-ams.scw.cloud/candidates-db/candidates-api:latest \
    -f container/Dockerfile .
```
The `--platform linux/amd64` flag is required when building on Apple Silicon (M1/M2/M3) to ensure the image runs on Scaleway's x86 infrastructure.

**5. Push the image to the registry:**
```bash
docker push rg.nl-ams.scw.cloud/candidates-db/candidates-api:latest
```

**6. Deploy the container:**
```bash
cd terraform
terraform apply
```
On first deploy this creates the container. On subsequent deploys, force replacement to pick up the new image:
```bash
terraform apply -replace=scaleway_container.api
```

#### Deploy frontend only (no Terraform needed)

```bash
s3cmd put frontend/*.html frontend/*.js s3://candidates.ittopia.nl/ --acl-public
```

#### Registry credentials

To push images to the Scaleway Container Registry you need:

1. **`scw` CLI configured** — run `scw init` and provide your Scaleway access key, secret key, and default project ID. This creates `~/.config/scw/config.yaml`.
2. **`scw registry login`** — this command reads credentials from the `scw` config and runs `docker login rg.nl-ams.scw.cloud` on your behalf. It must be re-run if your credentials change or your Docker auth expires.
3. **IAM permissions** — the Scaleway API key used must have `ContainerRegistryFullAccess` (or at minimum `ContainerRegistryReadWrite`) permission on the project. The default "Owner" or "ProjectManager" roles include this.

If you cannot use the `scw` CLI, you can log in to the registry directly:
```bash
docker login rg.nl-ams.scw.cloud -u <SCW_ACCESS_KEY> -p <SCW_SECRET_KEY>
```

**What Terraform manages:**
- Scaleway Serverless SQL Database (PostgreSQL)
- IAM application + API keys for DB access (read-write and read-only)
- Container Registry namespace (`rg.nl-ams.scw.cloud/candidates-db`)
- Container namespace + 1 serverless container (all API routes)
- Object Storage bucket for frontend hosting

**Notes:**
- The container image is built from `container/Dockerfile` with the project root as build context
- It copies the `candidates/` package (including `helpers.py`) into the image
- The container listens on port 8080 (uvicorn) — Scaleway proxies HTTPS to it
- `min_scale=0`: the container scales to zero when idle (no cost), but has a cold start on first request
- Static frontend is hosted on Scaleway Object Storage with website hosting enabled
- DNS: Route 53 CNAME `cv.yourdomain.com` -> Object Storage endpoint

### Reverting to serverless functions

The previous serverless functions setup is preserved at git tag `v1-serverless-functions`.

```bash
# Restore all files from the functions version
git checkout v1-serverless-functions -- .

# Rebuild function zips and deploy
bash terraform/build_zips.sh
cd terraform && terraform apply
```

## Database

Dual backend support:
- **SQLite** for local development (default)
- **PostgreSQL** for production (Scaleway Serverless SQL)

All SQL uses parameterized queries. `execute_query()` restricts LLM-generated queries to SELECT only.

## Auth

HMAC-SHA256 signed tokens with 24h expiry. All endpoints except `/login` require `Authorization: Bearer <token>` header.

### Managing Users

Users are stored as a JSON map of `username -> SHA-256(password)` in the `AUTH_USERS` env var, configured in `terraform/terraform.tfvars`.

**To add a new user:**

1. Generate the SHA-256 hash of the password:
```bash
echo -n "the_password" | shasum -a 256 | awk '{print $1}'
```

2. Add the username and hash to `auth_users` in `terraform/terraform.tfvars`:
```
auth_users = "{\"existing_user\":\"existing_hash\",\"new_user\":\"new_hash\"}"
```

3. Deploy the change:
```bash
cd terraform
terraform apply
```

This updates the `AUTH_USERS` secret env var on the container. No image rebuild needed — only env vars change.

**To remove a user:** Delete their entry from the JSON map in `terraform.tfvars` and run `terraform apply`.
