# Reusable kubeadm-on-EC2 cluster module.
#
# Current scope:
#   - Networking: VPC, public subnets, IGW, routes
#   - Security groups: control-plane + workers (see security_groups.tf)
#   - IAM: control-plane + worker roles/instance profiles (see iam.tf)
#   - EC2: control-plane instance + worker LT/ASG with kubeadm user_data (see ec2.tf)
# Pending: first terraform apply + validation on live AWS.
# Explicitly NOT in scope: EKS or any managed Kubernetes control plane.

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  # Use the first two AZs in the region (stable enough for a two-subnet design).
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  # Exact SSM parameter path for the kubeadm join command (SecureString at runtime).
  ssm_join_parameter_name = "/${var.project_name}/${var.environment}/k8s/worker-join-command"

  # Strip the patch segment once in Terraform (e.g. "1.31.4" -> "1.31").
  # This avoids mixing bash command substitution with templatefile escaping in the
  # Kubernetes repo URL construction.
  k8s_major_minor = join(".", slice(split(".", var.kubernetes_version), 0, 2))

  bootstrap_template_vars = {
    aws_region              = var.aws_region
    ssm_join_parameter_name = local.ssm_join_parameter_name
    kubernetes_version      = var.kubernetes_version
    k8s_major_minor         = local.k8s_major_minor
    calico_version          = var.calico_version
    pod_network_cidr        = var.pod_network_cidr
    join_token_ttl          = var.join_token_ttl
    join_max_attempts       = var.join_max_attempts
    join_sleep_seconds      = var.join_sleep_seconds
  }

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Phase       = "2"
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-igw"
  })
}

resource "aws_subnet" "public" {
  count = length(var.public_subnet_cidrs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = var.map_public_ip_on_launch

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-${local.azs[count.index]}"
    Tier = "public"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-rt"
  })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
