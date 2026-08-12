# Phase 2 — AWS infrastructure (EC2 + kubeadm)
#
# Status: SKELETON ONLY — no resources are defined yet.
# Do not run `terraform apply` until networking/EC2 modules are implemented
# and explicitly approved.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state backend — pending (S3 + DynamoDB lock, or equivalent).
  # backend "s3" {}
}
