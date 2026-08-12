output "vpc_id" {
  description = "ID of the VPC hosting the future kubeadm cluster"
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets (ordered to match public_subnet_cidrs)"
  value       = aws_subnet.public[*].id
}

output "public_subnet_cidrs" {
  description = "CIDR blocks of the public subnets"
  value       = aws_subnet.public[*].cidr_block
}

output "public_subnet_azs" {
  description = "Availability Zones of the public subnets"
  value       = aws_subnet.public[*].availability_zone
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway attached to the VPC"
  value       = aws_internet_gateway.this.id
}

output "public_route_table_id" {
  description = "ID of the public route table (0.0.0.0/0 → IGW)"
  value       = aws_route_table.public.id
}

output "control_plane_security_group_id" {
  description = "Security group ID for the kubeadm control-plane node"
  value       = aws_security_group.control_plane.id
}

output "worker_security_group_id" {
  description = "Security group ID for kubeadm worker nodes"
  value       = aws_security_group.workers.id
}

output "control_plane_iam_role_name" {
  description = "IAM role name for the control-plane EC2 instance"
  value       = aws_iam_role.control_plane.name
}

output "control_plane_iam_role_arn" {
  description = "IAM role ARN for the control-plane EC2 instance"
  value       = aws_iam_role.control_plane.arn
}

output "control_plane_instance_profile_name" {
  description = "Instance profile name for the control-plane EC2 instance"
  value       = aws_iam_instance_profile.control_plane.name
}

output "control_plane_instance_profile_arn" {
  description = "Instance profile ARN for the control-plane EC2 instance"
  value       = aws_iam_instance_profile.control_plane.arn
}

output "worker_iam_role_name" {
  description = "IAM role name for worker EC2 instances"
  value       = aws_iam_role.workers.name
}

output "worker_iam_role_arn" {
  description = "IAM role ARN for worker EC2 instances"
  value       = aws_iam_role.workers.arn
}

output "worker_instance_profile_name" {
  description = "Instance profile name for worker EC2 instances"
  value       = aws_iam_instance_profile.workers.name
}

output "worker_instance_profile_arn" {
  description = "Instance profile ARN for worker EC2 instances"
  value       = aws_iam_instance_profile.workers.arn
}
