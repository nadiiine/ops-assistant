# Non-secret defaults for the dev environment.
# Do not put AWS keys or private material here.

project_name = "ops-assistant"
environment  = "dev"
aws_region   = "us-east-1"

vpc_cidr                = "10.0.0.0/16"
public_subnet_cidrs     = ["10.0.0.0/24", "10.0.1.0/24"]
map_public_ip_on_launch = true

# Reserved for later Phase 2 steps (not used by networking):
instance_type = "t3.medium"
worker_count  = 1
key_name      = ""

allowed_ssh_cidrs = []
allowed_api_cidrs = []
