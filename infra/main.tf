# Root module — wires reusable modules once they are implemented.
#
# PENDING (do not implement until approved):
#   - modules/k8s-cluster (VPC, subnets, IGW, routes, SGs, IAM, EC2, user-data)

# Example wiring (commented until the module has real resources):
#
# module "k8s_cluster" {
#   source = "./modules/k8s-cluster"
#
#   project_name       = var.project_name
#   environment        = var.environment
#   aws_region         = var.aws_region
#   vpc_cidr           = var.vpc_cidr
#   instance_type      = var.instance_type
#   worker_count       = var.worker_count
#   key_name           = var.key_name
#   allowed_ssh_cidrs  = var.allowed_ssh_cidrs
#   allowed_api_cidrs  = var.allowed_api_cidrs
# }
