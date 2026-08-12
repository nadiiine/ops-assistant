# Planned module outputs — commented until resources exist.

# output "vpc_id" {
#   description = "VPC ID"
#   value       = aws_vpc.this.id
# }
#
# output "control_plane_public_ip" {
#   description = "Public IP of the control-plane EC2 instance"
#   value       = aws_instance.control_plane.public_ip
# }
#
# output "worker_instance_ids" {
#   description = "IDs of worker EC2 instances (or ASG member IDs once stable)"
#   value       = [for w in aws_instance.workers : w.id]
# }
