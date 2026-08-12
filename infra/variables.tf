variable "project_name" {
  description = "Short project name used in resource naming and tags"
  type        = string
  default     = "ops-assistant"
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for all Phase 2 resources"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the two public subnets (different AZs)"
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "map_public_ip_on_launch" {
  description = "Assign a public IP to instances launched in public subnets"
  type        = bool
  default     = true
}

variable "instance_type" {
  description = "EC2 instance type for control-plane and workers (pending EC2 step)"
  type        = string
  default     = "t3.medium"
}

variable "worker_count" {
  description = "Number of worker EC2 instances (pending EC2 step)"
  type        = number
  default     = 1
}

variable "key_name" {
  description = "Existing EC2 key pair name for SSH (pending EC2 step)"
  type        = string
  default     = ""
}

variable "allowed_ssh_cidrs" {
  description = "CIDRs allowed to SSH to nodes (pending security groups)"
  type        = list(string)
  default     = []
}

variable "allowed_api_cidrs" {
  description = "CIDRs allowed to reach the Kubernetes API (port 6443)"
  type        = list(string)
  default     = []
}
