# Non-secret defaults for the dev environment.
# Do not put AWS keys or private material here.

project_name = "ops-assistant"
environment  = "dev"
aws_region   = "us-east-1"

vpc_cidr                = "10.0.0.0/16"
public_subnet_cidrs     = ["10.0.0.0/24", "10.0.1.0/24"]
map_public_ip_on_launch = true

# Security group CIDRs — set before EC2/SSH/API access is needed.
# Example: ["203.0.113.10/32"]  (your public IP /32). Do NOT use 0.0.0.0/0.
# Leave empty for now: SSH / external API / NodePort ingress rules are omitted.
allowed_ssh_cidrs      = []
allowed_api_cidrs      = []
allowed_nodeport_cidrs = []

# Reserved for later Phase 2 steps (not used by networking/SGs yet):
instance_type = "t3.medium"
worker_count  = 1
key_name      = ""
