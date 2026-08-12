variable "project_name" {
  description = "Short project name used in resource naming and tags"
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging)"
  type        = string
}

variable "aws_region" {
  description = "AWS region (informational / for AZs lookup later)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type for control-plane and workers"
  type        = string
}

variable "worker_count" {
  description = "Number of worker EC2 instances (fixed count or ASG desired capacity)"
  type        = number
}

variable "key_name" {
  description = "EC2 key pair name for SSH access"
  type        = string
}

variable "allowed_ssh_cidrs" {
  description = "CIDRs allowed to SSH to nodes"
  type        = list(string)
}

variable "allowed_api_cidrs" {
  description = "CIDRs allowed to reach the Kubernetes API server (6443)"
  type        = list(string)
}
