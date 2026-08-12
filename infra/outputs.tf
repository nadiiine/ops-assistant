# Outputs will be populated once modules/k8s-cluster is implemented.
#
# Planned outputs (not active yet):
#   - vpc_id
#   - control_plane_public_ip
#   - worker_public_ips / worker_asg_name
#   - kubeconfig retrieval instructions (kubeadm-generated on the CP node)

# output "vpc_id" {
#   description = "ID of the VPC hosting the kubeadm cluster"
#   value       = module.k8s_cluster.vpc_id
# }
#
# output "control_plane_public_ip" {
#   description = "Public IP of the kubeadm control-plane EC2 instance"
#   value       = module.k8s_cluster.control_plane_public_ip
# }
