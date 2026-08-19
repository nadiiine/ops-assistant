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

output "control_plane_security_group_id" {
  description = "Security group ID for the kubeadm control-plane node"
  value       = module.k8s_cluster.control_plane_security_group_id
}

output "worker_security_group_id" {
  description = "Security group ID for kubeadm worker nodes"
  value       = module.k8s_cluster.worker_security_group_id
}

output "control_plane_iam_role_name" {
  description = "IAM role name for the control-plane EC2 instance"
  value       = module.k8s_cluster.control_plane_iam_role_name
}

output "control_plane_iam_role_arn" {
  description = "IAM role ARN for the control-plane EC2 instance"
  value       = module.k8s_cluster.control_plane_iam_role_arn
}

output "control_plane_instance_profile_name" {
  description = "Instance profile name for the control-plane EC2 instance"
  value       = module.k8s_cluster.control_plane_instance_profile_name
}

output "worker_iam_role_name" {
  description = "IAM role name for worker EC2 instances"
  value       = module.k8s_cluster.worker_iam_role_name
}

output "worker_iam_role_arn" {
  description = "IAM role ARN for worker EC2 instances"
  value       = module.k8s_cluster.worker_iam_role_arn
}

output "worker_instance_profile_name" {
  description = "Instance profile name for worker EC2 instances"
  value       = module.k8s_cluster.worker_instance_profile_name
}

output "ubuntu_ami_id" {
  description = "Resolved Ubuntu AMI ID used for nodes"
  value       = module.k8s_cluster.ubuntu_ami_id
}

output "control_plane_instance_id" {
  description = "EC2 instance ID of the control-plane node"
  value       = module.k8s_cluster.control_plane_instance_id
}

output "control_plane_private_ip" {
  description = "Private IPv4 of the control-plane node"
  value       = module.k8s_cluster.control_plane_private_ip
}

output "control_plane_public_ip" {
  description = "Public IPv4 of the control-plane node"
  value       = module.k8s_cluster.control_plane_public_ip
}

output "worker_launch_template_id" {
  description = "Worker launch template ID"
  value       = module.k8s_cluster.worker_launch_template_id
}

output "worker_asg_name" {
  description = "Worker Auto Scaling Group name"
  value       = module.k8s_cluster.worker_asg_name
}

output "ssm_join_parameter_name" {
  description = "SSM parameter holding the kubeadm join command"
  value       = module.k8s_cluster.ssm_join_parameter_name
}

output "backend_ecr_repository_url" {
  description = "ECR repository URL for the backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_ecr_repository_url" {
  description = "ECR repository URL for the frontend image"
  value       = aws_ecr_repository.frontend.repository_url
}
