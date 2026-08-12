# Root module — wires the k8s-cluster module.
# Current module scope: networking only (VPC, public subnets, IGW, routes).

module "k8s_cluster" {
  source = "./modules/k8s-cluster"

  project_name            = var.project_name
  environment             = var.environment
  aws_region              = var.aws_region
  vpc_cidr                = var.vpc_cidr
  public_subnet_cidrs     = var.public_subnet_cidrs
  map_public_ip_on_launch = var.map_public_ip_on_launch

  # Passed through for a stable module interface; unused until later steps.
  instance_type     = var.instance_type
  worker_count      = var.worker_count
  key_name          = var.key_name
  allowed_ssh_cidrs = var.allowed_ssh_cidrs
  allowed_api_cidrs = var.allowed_api_cidrs
}
