terraform {
  backend "s3" {
    bucket   = "terraform-bucket"
    key      = "candidates_database/terraform.tfstate"
    region   = "nl-ams"
    profile  = "scaleway"
    endpoint = "https://s3.nl-ams.scw.cloud"

    skip_credentials_validation = true
    skip_region_validation      = true
    skip_metadata_api_check     = true
    encrypt                     = false
  }
}
