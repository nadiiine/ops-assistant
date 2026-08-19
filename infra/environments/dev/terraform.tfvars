# Non-secret defaults for the dev environment.
# Do not put AWS keys or private key material here.

project_name = "ops-assistant"
environment  = "dev"
aws_region   = "us-east-1"

vpc_cidr                = "10.0.0.0/16"
public_subnet_cidrs     = ["10.0.0.0/24", "10.0.1.0/24"]
map_public_ip_on_launch = true

# Security group CIDRs — set before SSH/API from your laptop is needed.
# Example: ["203.0.113.10/32"]  Do NOT use 0.0.0.0/0.
allowed_ssh_cidrs      = []
allowed_api_cidrs      = ["79.177.159.83/32"]
allowed_nodeport_cidrs = ["79.177.159.83/32"]

enable_ssm = true

# EC2 — Ubuntu 22.04 AMI resolved via data source (see ubuntu_ami_name_filter default).
instance_type           = "t3.medium"
worker_instance_type    = "" # empty = same as instance_type
worker_min_size         = 1
worker_max_size         = 2
worker_desired_capacity = 1
root_volume_size_gb     = 20

# Optional SSH key pair name (must already exist in the account/region).
# Leave empty to use SSM Session Manager only (recommended with enable_ssm = true).
key_name = ""

# Kubernetes bootstrap pins
kubernetes_version = "1.31.4"
calico_version     = "v3.29.1"
pod_network_cidr   = "192.168.0.0/16"
join_token_ttl     = "24h0m0s"
join_max_attempts  = 36
join_sleep_seconds = 20
