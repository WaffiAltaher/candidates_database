output "container_url" {
  value = scaleway_container.api.domain_name
}

output "container_registry_endpoint" {
  value = scaleway_registry_namespace.main.endpoint
}

output "frontend_website_url" {
  value = scaleway_object_bucket_website_configuration.frontend.website_endpoint
}

output "database_endpoint" {
  value     = scaleway_sdb_sql_database.main.endpoint
  sensitive = true
}
