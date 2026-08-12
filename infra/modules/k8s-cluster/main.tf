# Reusable kubeadm-on-EC2 cluster module — SKELETON ONLY.
#
# This module will eventually create:
#   - VPC, public subnets, Internet Gateway, route tables
#   - Security groups (SSH, K8s API 6443, node-to-node)
#   - IAM roles/instance profiles for EC2 nodes
#   - EC2 control-plane instance (user-data → scripts/control-plane.sh)
#   - EC2 worker instances or an Auto Scaling Group (user-data → scripts/worker.sh)
#
# Explicitly NOT in scope: EKS, ECS, Fargate, or any managed Kubernetes control plane.

# PENDING: networking, security groups, IAM, EC2, user-data.
# No aws_* resources are declared in this skeleton.
