# Root module — wires the k8s-cluster module.
# Scope: networking + security groups + IAM + EC2 (no kubeadm user_data yet).

module "k8s_cluster" {
  source = "./modules/k8s-cluster"

  project_name            = var.project_name
  environment             = var.environment
  aws_region              = var.aws_region
  vpc_cidr                = var.vpc_cidr
  public_subnet_cidrs     = var.public_subnet_cidrs
  map_public_ip_on_launch = var.map_public_ip_on_launch

  allowed_ssh_cidrs      = var.allowed_ssh_cidrs
  allowed_api_cidrs      = var.allowed_api_cidrs
  allowed_nodeport_cidrs = var.allowed_nodeport_cidrs
  enable_ssm             = var.enable_ssm

  ubuntu_ami_name_filter  = var.ubuntu_ami_name_filter
  instance_type           = var.instance_type
  worker_instance_type    = var.worker_instance_type
  worker_min_size         = var.worker_min_size
  worker_max_size         = var.worker_max_size
  worker_desired_capacity = var.worker_desired_capacity
  root_volume_size_gb     = var.root_volume_size_gb
  key_name                = var.key_name
}
