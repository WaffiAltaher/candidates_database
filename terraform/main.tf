terraform {
  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "2.70.1"
    }
  }
  required_version = "1.5.7"
}

provider "scaleway" {
  region = "nl-ams"
  zone   = "nl-ams-1"
  # access_key, secret_key, project_id read from env:
  #   SCW_ACCESS_KEY, SCW_SECRET_KEY, SCW_DEFAULT_PROJECT_ID
}

# -----------------------------------------------------
# Data: current project
# -----------------------------------------------------
data "scaleway_account_project" "current" {}

# -----------------------------------------------------
# Serverless SQL Database
# -----------------------------------------------------
resource "scaleway_sdb_sql_database" "main" {
  name    = "candidates"
  min_cpu = 0
  max_cpu = 8
  region  = "fr-par" # Serverless SQL only available in fr-par
}

# IAM application + API key for DB access
resource "scaleway_iam_application" "db_app" {
  name = "candidates-db-app"
}

resource "scaleway_iam_api_key" "db_key" {
  application_id = scaleway_iam_application.db_app.id
  expires_at     = "2027-03-14T00:00:00Z"
}

resource "scaleway_iam_policy" "db_access" {
  name           = "candidates-db-access"
  application_id = scaleway_iam_application.db_app.id
  rule {
    project_ids          = [data.scaleway_account_project.current.id]
    permission_set_names = ["ServerlessSQLDatabaseReadWrite"]
  }
}

locals {
  database_url = format("postgres://%s:%s@%s",
    scaleway_iam_application.db_app.id,
    scaleway_iam_api_key.db_key.secret_key,
    trimprefix(scaleway_sdb_sql_database.main.endpoint, "postgres://"),
  )
  database_url_readonly = format("postgres://%s:%s@%s",
    scaleway_iam_application.db_app_readonly.id,
    scaleway_iam_api_key.db_key_readonly.secret_key,
    trimprefix(scaleway_sdb_sql_database.main.endpoint, "postgres://"),
  )
}

# Read-only IAM application + API key for search queries
resource "scaleway_iam_application" "db_app_readonly" {
  name = "candidates-db-app-readonly"
}

resource "scaleway_iam_api_key" "db_key_readonly" {
  application_id = scaleway_iam_application.db_app_readonly.id
  expires_at     = "2027-03-14T00:00:00Z"
}

resource "scaleway_iam_policy" "db_access_readonly" {
  name           = "candidates-db-access-readonly"
  application_id = scaleway_iam_application.db_app_readonly.id
  rule {
    project_ids          = [data.scaleway_account_project.current.id]
    permission_set_names = ["ServerlessSQLDatabaseReadOnly"]
  }
}

# -----------------------------------------------------
# Container Registry
# -----------------------------------------------------
resource "scaleway_registry_namespace" "main" {
  name   = "candidates-db"
  region = "nl-ams"
}

# -----------------------------------------------------
# Serverless Container
# -----------------------------------------------------
resource "scaleway_container_namespace" "main" {
  name        = "candidates-db"
  description = "Candidates Database API"
  region      = "nl-ams"
}

resource "scaleway_container" "api" {
  namespace_id   = scaleway_container_namespace.main.id
  name           = "candidates-api"
  registry_image = "${scaleway_registry_namespace.main.endpoint}/candidates-api:latest"
  port           = 8080
  cpu_limit      = 1120
  memory_limit   = 1120
  min_scale      = 0
  max_scale      = 5
  timeout        = 300
  privacy        = "public"
  http_option    = "redirected"
  deploy         = true

  secret_environment_variables = {
    DATABASE_URL          = local.database_url
    DATABASE_URL_READONLY = local.database_url_readonly
    ANTHROPIC_API_KEY     = var.anthropic_api_key
    AUTH_SECRET           = var.auth_secret
    AUTH_USERS            = var.auth_users
    ALLOWED_ORIGIN        = var.allowed_origin
  }
}

# -----------------------------------------------------
# Object Storage — static frontend
# -----------------------------------------------------
resource "scaleway_object_bucket" "frontend" {
  name          = var.frontend_bucket_name
  force_destroy = true
}


resource "scaleway_object_bucket_website_configuration" "frontend" {
  bucket = scaleway_object_bucket.frontend.name

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}
