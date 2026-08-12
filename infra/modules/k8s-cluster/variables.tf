variable "project_name" {
  description = "Short project name used in resource naming and tags"
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging)"
  type        = string
}

variable "aws_region" {
  description = "AWS region (informational; provider is configured at the root)"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (exactly two, one per AZ)"
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) == 2
    error_message = "Exactly two public subnet CIDRs are required (one per Availability Zone)."
  }
}

variable "map_public_ip_on_launch" {
  description = "Assign a public IP to instances launched in the public subnets"
  type        = bool
  default     = true
}

variable "allowed_ssh_cidrs" {
  description = "CIDRs allowed to SSH (TCP/22) to control-plane and worker nodes. Empty = no SSH ingress."
  type        = list(string)
  default     = []
}

variable "allowed_api_cidrs" {
  description = "CIDRs allowed to reach the Kubernetes API (TCP/6443) on the control-plane. Empty = no external API ingress (workers still allowed via SG)."
  type        = list(string)
  default     = []
}

variable "allowed_nodeport_cidrs" {
  description = "CIDRs allowed to reach NodePort Services (TCP/30000-32767) on workers. Empty = no external NodePort ingress."
  type        = list(string)
  default     = []
}

variable "enable_ssm" {
  description = "Attach AmazonSSMManagedInstanceCore to node roles for Session Manager (no SSH required)."
  type        = bool
  default     = true
}

# Reserved for later Phase 2 steps (EC2). Kept for a stable root→module interface.

variable "instance_type" {
  description = "EC2 instance type for control-plane and workers (unused until EC2 step)"
  type        = string
  default     = "t3.medium"
}

variable "worker_count" {
  description = "Number of worker EC2 instances (unused until EC2 step)"
  type        = number
  default     = 1
}

variable "key_name" {
  description = "EC2 key pair name for SSH access (unused until EC2 step)"
  type        = string
  default     = ""
}
