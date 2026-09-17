variable "location" {
  description = "My Project Location"
  default     = "US-CENTRAL1"
}

variable "region" {
  description = "My Project Region"
  default     = "us-central1"
}

variable "credentials" {
  description = "Path to credentials"
  default     = "./keys/mycreds.json"
}

variable "project" {
  description = "Project Name"
  default     = "terraformdemotwo"
}

variable "gcs_bucket_name" {
  description = "My storage bucket Name"
  default     = "terraformdemotwo-terra-bucket96"
}

variable "bq_dataset_name" {
  description = "My BigQuery Dataset Name"
  default     = "demo_dataset"
}

variable "gcs_storage_class" {
  description = "Bucket storage class"
  default     = "STANDARD"
}