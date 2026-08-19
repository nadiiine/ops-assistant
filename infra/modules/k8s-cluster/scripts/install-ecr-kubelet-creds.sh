#!/usr/bin/env bash
# Canonical kubelet ECR credential-provider installer.
#
# Used by:
#   - worker user_data (modules/k8s-cluster/scripts/worker.sh) after kubeadm join
#   - live-node SSM via infra/scripts/install-ecr-kubelet-creds.sh
#
# Uses the instance IAM role (AmazonEC2ContainerRegistryReadOnly).
# Idempotent: safe to re-run. Requires kubeadm-flags.env (after kubeadm join).
set -euo pipefail

BIN=/usr/local/bin/ecr-credential-provider
CFG=/etc/kubernetes/credential-provider-config.yaml
FLAGS=/var/lib/kubelet/kubeadm-flags.env

curl -fsSL -o "$BIN" \
  https://artifacts.k8s.io/binaries/cloud-provider-aws/v1.29.0/linux/amd64/ecr-credential-provider-linux-amd64
chmod +x "$BIN"

mkdir -p /etc/kubernetes
cat > "$CFG" <<'EOF'
apiVersion: kubelet.config.k8s.io/v1
kind: CredentialProviderConfig
providers:
  - name: ecr-credential-provider
    matchImages:
      - "*.dkr.ecr.*.amazonaws.com"
      - "*.dkr.ecr.*.amazonaws.com.cn"
      - "public.ecr.aws"
    defaultCacheDuration: "12h"
    apiVersion: credentialprovider.kubelet.k8s.io/v1
EOF

if [[ ! -f "$FLAGS" ]]; then
  echo "missing $FLAGS (run after kubeadm join)" >&2
  exit 1
fi

if ! grep -q "image-credential-provider-config" "$FLAGS"; then
  sed -i 's|KUBELET_KUBEADM_ARGS="\(.*\)"|KUBELET_KUBEADM_ARGS="\1 --image-credential-provider-bin-dir=/usr/local/bin --image-credential-provider-config=/etc/kubernetes/credential-provider-config.yaml"|' "$FLAGS"
fi

systemctl daemon-reload
systemctl restart kubelet
echo "ecr credential provider installed"
