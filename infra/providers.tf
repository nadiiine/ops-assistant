# AWS provider configuration — skeleton.
#
# Credentials are expected via the standard AWS chain (env vars, shared
# config, or CI role). Do not hard-code secrets here.

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Phase       = "2"
    }
  }
}
