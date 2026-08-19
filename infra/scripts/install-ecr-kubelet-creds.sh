#!/usr/bin/env bash
# Live-node / SSM entrypoint. Install logic lives in one place:
#   modules/k8s-cluster/scripts/install-ecr-kubelet-creds.sh
#
# Worker ASG user_data embeds that same file after kubeadm join.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/../modules/k8s-cluster/scripts/install-ecr-kubelet-creds.sh" "$@"
