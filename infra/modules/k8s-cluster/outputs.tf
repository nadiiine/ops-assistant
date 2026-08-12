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
