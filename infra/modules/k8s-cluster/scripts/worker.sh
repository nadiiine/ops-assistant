#!/usr/bin/env bash
# worker.sh — kubeadm join for worker EC2 instances.
#
# STATUS: PLACEHOLDER — not implemented yet. Do not use as user-data.
#
# Intended responsibilities (later):
#   1. Install container runtime (e.g. containerd)
#   2. Install kubelet, kubeadm, kubectl
#   3. Retrieve join token/endpoint from agreed location (TBD)
#   4. kubeadm join <control-plane>:6443 --token ... --discovery-token-ca-cert-hash ...
#
# Terraform will pass this script via EC2 user-data once worker resources exist.
set -euo pipefail

echo "TODO: implement kubeadm worker join"
exit 1
