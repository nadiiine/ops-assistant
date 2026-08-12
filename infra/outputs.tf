output "vpc_id" {
  description = "ID of the VPC hosting the future kubeadm cluster"
  value       = module.k8s_cluster.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = module.k8s_cluster.public_subnet_ids
}

output "public_subnet_cidrs" {
  description = "CIDR blocks of the public subnets"
  value       = module.k8s_cluster.public_subnet_cidrs
}

output "public_subnet_azs" {
  description = "Availability Zones of the public subnets"
  value       = module.k8s_cluster.public_subnet_azs
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway attached to the VPC"
  value       = module.k8s_cluster.internet_gateway_id
}

output "public_route_table_id" {
  description = "ID of the public route table"
  value       = module.k8s_cluster.public_route_table_id
}
