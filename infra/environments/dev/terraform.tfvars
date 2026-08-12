# Non-secret defaults for the dev environment.
# Copy/adjust as needed. Do not put AWS keys or private material here.

project_name = "ops-assistant"
environment  = "dev"
aws_region   = "us-east-1"

vpc_cidr      = "10.0.0.0/16"
instance_type = "t3.medium"
worker_count  = 1

# Set before apply (must be an existing EC2 key pair in the target account/region):
key_name = ""

# Restrict these before apply (empty = module should refuse unsafe defaults later):
allowed_ssh_cidrs = []
allowed_api_cidrs = []
