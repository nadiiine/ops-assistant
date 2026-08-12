#!/usr/bin/env bash
# control-plane.sh — kubeadm bootstrap for the control-plane EC2 instance.
#
# STATUS: PLACEHOLDER — not implemented yet. Do not use as user-data.
#
# Intended responsibilities (later):
#   1. Install container runtime (e.g. containerd)
#   2. Install kubelet, kubeadm, kubectl
#   3. kubeadm init (advertise address = instance private/public IP as designed)
#   4. Install CNI (e.g. Flannel/Calico — choice TBD)
#   5. Persist admin kubeconfig for retrieval by operators
#   6. Emit join command/token for workers (SSM Parameter Store or similar — TBD)
#
# Terraform will pass this script via EC2 user-data once EC2 resources exist.
set -euo pipefail

echo "TODO: implement kubeadm control-plane bootstrap"
exit 1
