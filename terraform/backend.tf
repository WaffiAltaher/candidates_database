# State credentials come from the environment, not from this file.
# Locally: AWS_PROFILE=scaleway
# GitHub Actions: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
terraform {
  backend "s3" {
    bucket   = "terraform-bucket"
    key      = "candidates_database/terraform.tfstate"
    region   = "nl-ams"
    endpoint = "https://s3.nl-ams.scw.cloud"

    skip_credentials_validation = true
    skip_region_validation      = true
    skip_metadata_api_check     = true
    encrypt                     = false
  }
}
