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

variable "ubuntu_ami_name_filter" {
  description = "AMI name filter for Canonical Ubuntu (amd64)"
  type        = string
  default     = "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"
}

variable "instance_type" {
  description = "EC2 instance type for the control-plane node"
  type        = string
  default     = "t3.medium"
}

variable "worker_instance_type" {
  description = "EC2 instance type for workers. Empty = use instance_type."
  type        = string
  default     = ""
}

variable "worker_min_size" {
  description = "Worker ASG minimum size"
  type        = number
  default     = 1
}

variable "worker_max_size" {
  description = "Worker ASG maximum size"
  type        = number
  default     = 2
}

variable "worker_desired_capacity" {
  description = "Worker ASG desired capacity (Phase 2 default: 1)"
  type        = number
  default     = 1
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size (GiB)"
  type        = number
  default     = 20
}

variable "key_name" {
  description = "Optional existing EC2 key pair for SSH. Empty = SSM-only access."
  type        = string
  default     = ""
}

variable "allowed_ssh_cidrs" {
  description = "CIDRs allowed to SSH (TCP/22) to nodes. Empty = no SSH ingress rules."
  type        = list(string)
  default     = []
}

variable "allowed_api_cidrs" {
  description = "CIDRs allowed to reach Kubernetes API (TCP/6443). Empty = no external API ingress."
  type        = list(string)
  default     = []
}

variable "allowed_nodeport_cidrs" {
  description = "CIDRs allowed to reach NodePort Services (TCP/30000-32767). Empty = no external NodePort ingress."
  type        = list(string)
  default     = []
}

variable "enable_ssm" {
  description = "Attach AmazonSSMManagedInstanceCore to node IAM roles for Session Manager"
  type        = bool
  default     = true
}

variable "kubernetes_version" {
  description = "Kubernetes package version (kubeadm/kubelet/kubectl)"
  type        = string
  default     = "1.31.4"
}

variable "calico_version" {
  description = "Calico release tag for VXLAN manifests"
  type        = string
  default     = "v3.29.1"
}

variable "pod_network_cidr" {
  description = "Pod CIDR for kubeadm init / Calico"
  type        = string
  default     = "192.168.0.0/16"
}

variable "join_token_ttl" {
  description = "TTL for kubeadm tokens stored in SSM"
  type        = string
  default     = "24h0m0s"
}

variable "join_max_attempts" {
  description = "Worker join retry attempts"
  type        = number
  default     = 36
}

variable "join_sleep_seconds" {
  description = "Seconds between worker join retries"
  type        = number
  default     = 20
}

variable "alert_email" {
  description = "Optional email for SNS alert subscriptions. Empty = create topic only (no subscription)."
  type        = string
  default     = ""
}
