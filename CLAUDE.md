# CLAUDE.md

## Project Overview

Candidates Database - A CV management and search system deployed as a Scaleway Serverless Container (FastAPI) with a static JS frontend and PostgreSQL database.

## Architecture

```
candidates.ittopia.nl (object storage website) serves the static frontend
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
├── .github/workflows/       # deploy.yml applies Terraform on push to main
├── terraform/               # Infrastructure as code
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── backend.tf
│   ├── production.auto.tfvars  # Bucket name and CORS origin (not secrets)
│   ├── terraform.tfvars     # Local secrets only (gitignored, not used by CI)
│   ├── terraform.tfvars.example
│   └── build_container.sh   # Build and push the container image only
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
| `LLM_MODEL` | AISuite model string | No (default: anthropic:claude-sonnet-5-5) |
| `LLM_MODEL_FAST` | AISuite model string for faster/cheaper SQL generation | No (default: anthropic:claude-haiku-4-5-20251001) |
| `AUTH_SECRET` | HMAC signing secret for tokens | Yes |
| `AUTH_USERS` | JSON map of username -> SHA-256(password) hash | Yes |
| `ALLOWED_ORIGIN` | CORS allowed origin | Production |
| `LOG_LEVEL` | Logging level | No (default: INFO) |

### Deployment

The public repository is `https://github.com/WaffiAltaher/candidates_database`.

Infrastructure changes are applied by GitHub Actions, not by a local `terraform apply`. The workflow file is `.github/workflows/deploy.yml`.

- It runs on a push to `main`, and when someone starts it manually with `workflow_dispatch`.
- The job uses the GitHub environment `production` and waits for approval from `WaffiAltaher` before Terraform runs.
- It plans, stops if that plan deletes any resource, then applies the saved plan. It does not upload the plan file.
- It does not build or push the container image.
- Runner is `ubuntu-latest`. Terraform is pinned to `1.5.7`. The Scaleway provider is pinned to `2.70.1` in `terraform/main.tf` and `.terraform.lock.hcl`.

`gh` commands for this repository must run from `/Users/waffi/rnd/ittopia/candidates_database`. direnv in that directory selects the personal GitHub account `WaffiAltaher`. Outside `/Users/waffi/rnd/ittopia`, the CLI uses a different account.

#### GitHub environment `production`

Secrets are stored on that environment only. There are no repository-level Actions secrets. Names:

| Secret | Purpose |
|---|---|
| `SCW_ACCESS_KEY` | Scaleway Terraform provider |
| `SCW_SECRET_KEY` | Scaleway Terraform provider |
| `SCW_DEFAULT_PROJECT_ID` | Scaleway project |
| `AWS_ACCESS_KEY_ID` | State bucket credentials (Scaleway object storage) |
| `AWS_SECRET_ACCESS_KEY` | State bucket credentials |
| `TF_VAR_anthropic_api_key` | Anthropic API key |
| `TF_VAR_auth_secret` | HMAC signing secret |
| `TF_VAR_auth_users` | Raw JSON map of username to SHA-256 password hash |

`terraform/production.auto.tfvars` is committed and holds only the frontend bucket name (`candidates.ittopia.nl`) and the CORS origin (`http://candidates.ittopia.nl`). Do not put secrets in that file.

#### Local Terraform

Use this to inspect a plan. Do not apply locally. A local apply races the GitHub job and skips the approval check.

```bash
cd terraform
export AWS_PROFILE=scaleway
terraform init -reconfigure
terraform plan
```

State is in the private bucket `terraform-bucket` (`candidates_database/terraform.tfstate` on `https://s3.nl-ams.scw.cloud`). Do not commit state files or plan files. `backend.tf` does not name a credentials profile. Locally, `AWS_PROFILE=scaleway` points at `~/.aws/credentials`. In GitHub Actions the same keys are the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` secrets.

Scaleway provider credentials for a local plan come from `~/.config/scw/config.yaml`, or from `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, and `SCW_DEFAULT_PROJECT_ID`.

#### Container image

`bash terraform/build_container.sh` builds and pushes `rg.nl-ams.scw.cloud/candidates-db/candidates-api:latest`. It requires the `scw` CLI (`scw init`, then `scw registry login`). The `--platform linux/amd64` build is required on Apple Silicon.

Pushing an image does not restart the running container. The next approved GitHub Actions deploy replaces `scaleway_container.api` only when that resource changes. This workflow does not build images, so an image-only push does not roll out a new container by itself.

#### Frontend files

```bash
s3cmd put frontend/*.html frontend/*.js s3://candidates.ittopia.nl/ --acl-public
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
- The container listens on port 8080 (uvicorn). Scaleway proxies HTTPS to it
- `min_scale=0`: the container scales to zero when idle, with a cold start on the next request
- The app refuses to start if `AUTH_SECRET` is missing, shorter than 24 characters, or equal to `dev-secret-change-me`, or if `ALLOWED_ORIGIN` is empty
- `terraform/terraform.tfvars` is for local experiments only. CI does not read it

## Database

Dual backend support:
- **SQLite** for local development (default)
- **PostgreSQL** for production (Scaleway Serverless SQL)

All SQL uses parameterized queries. `execute_query()` restricts LLM-generated queries to SELECT only.

## Auth

HMAC-SHA256 signed tokens with 24h expiry. All endpoints except `/login` require `Authorization: Bearer <token>` header.

### Managing Users

Users are a JSON map of `username -> SHA-256(password)` in the `TF_VAR_auth_users` secret on the GitHub environment `production`. The value is raw JSON, not an HCL string.

**To add a new user:**

1. Generate the SHA-256 hash of the password:
```bash
echo -n "the_password" | shasum -a 256 | awk '{print $1}'
```

2. Update the `TF_VAR_auth_users` environment secret with the full JSON object, including existing users. Run `gh` from this repository's directory so the personal GitHub account is selected:
```bash
printf '%s' '{"existing_user":"<existing_hash>","new_user":"<new_hash>"}' \
  | gh secret set TF_VAR_auth_users --env production --repo WaffiAltaher/candidates_database
```

3. Run the deploy workflow and approve it. No image rebuild is required. The workflow updates the container environment variable.

**To remove a user:** Set the secret to the JSON object without that user, then run and approve the workflow again.
