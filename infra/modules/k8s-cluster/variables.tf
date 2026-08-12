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

variable "ubuntu_ami_name_filter" {
  description = "AMI name filter for Canonical Ubuntu (amd64). Default: Ubuntu 22.04 LTS Jammy."
  type        = string
  default     = "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"
}

variable "instance_type" {
  description = "EC2 instance type for the control-plane node"
  type        = string
  default     = "t3.medium"
}

variable "worker_instance_type" {
  description = "EC2 instance type for worker nodes. Empty = use instance_type."
  type        = string
  default     = ""
}

variable "worker_min_size" {
  description = "Auto Scaling Group minimum worker count"
  type        = number
  default     = 1
}

variable "worker_max_size" {
  description = "Auto Scaling Group maximum worker count"
  type        = number
  default     = 2
}

variable "worker_desired_capacity" {
  description = "Auto Scaling Group desired worker count (Phase 2 default: 1)"
  type        = number
  default     = 1
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size (GiB) for control-plane and workers"
  type        = number
  default     = 20
}

variable "key_name" {
  description = "Optional existing EC2 key pair name for SSH. Leave empty to rely on SSM only (recommended when enable_ssm = true)."
  type        = string
  default     = ""
}

variable "kubernetes_version" {
  description = "Kubernetes package version (kubeadm/kubelet/kubectl), e.g. 1.31.4"
  type        = string
  default     = "1.31.4"
}

variable "calico_version" {
  description = "Calico manifest tag (VXLAN mode), e.g. v3.29.1"
  type        = string
  default     = "v3.29.1"
}

variable "pod_network_cidr" {
  description = "Pod network CIDR passed to kubeadm init (must match Calico IP pool)"
  type        = string
  default     = "192.168.0.0/16"
}

variable "join_token_ttl" {
  description = "TTL for kubeadm bootstrap tokens written to SSM (refreshed by CP timer)"
  type        = string
  default     = "24h0m0s"
}

variable "join_max_attempts" {
  description = "Worker: max attempts to read SSM join parameter / run kubeadm join"
  type        = number
  default     = 36
}

variable "join_sleep_seconds" {
  description = "Worker: sleep between join attempts (seconds)"
  type        = number
  default     = 20
}
