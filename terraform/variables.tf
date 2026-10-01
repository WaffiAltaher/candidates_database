variable "anthropic_api_key" {
  description = "Anthropic API key for Claude"
  type        = string
  sensitive   = true
}

variable "auth_secret" {
  description = "HMAC secret for signing auth tokens"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.auth_secret) >= 24 && var.auth_secret != "dev-secret-change-me"
    error_message = "auth_secret must be at least 24 characters and must not be the local default."
  }
}

variable "auth_users" {
  description = "JSON map of username -> sha256 password hash"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.auth_users) > 0 && can(jsondecode(var.auth_users))
    error_message = "auth_users must be non-empty valid JSON."
  }
}

variable "allowed_origin" {
  description = "CORS allowed origin for the frontend"
  type        = string

  validation {
    condition     = length(var.allowed_origin) > 0 && var.allowed_origin != "*"
    error_message = "allowed_origin must be set and must not be *."
  }
}

variable "frontend_bucket_name" {
  description = "Name for the Object Storage bucket hosting the frontend"
  type        = string
  default     = "candidates-db-frontend"
}
