variable "anthropic_api_key" {
  description = "Anthropic API key for Claude"
  type        = string
  sensitive   = true
}

variable "auth_secret" {
  description = "HMAC secret for signing auth tokens"
  type        = string
  sensitive   = true
}

variable "auth_users" {
  description = "JSON map of username -> sha256 password hash"
  type        = string
  sensitive   = true
}

variable "allowed_origin" {
  description = "CORS allowed origin for the frontend"
  type        = string
  default     = "*"
}

variable "frontend_bucket_name" {
  description = "Name for the Object Storage bucket hosting the frontend"
  type        = string
  default     = "candidates-db-frontend"
}
