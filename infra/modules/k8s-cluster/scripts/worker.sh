#!/usr/bin/env bash
# worker.sh — rendered by Terraform templatefile().
# Installs containerd + kubeadm, waits for the control-plane join command in SSM,
# then runs kubeadm join. Safe for ASG instance replacement.
#
# Terraform interpolations use dollar-brace names (aws_region, etc.).
# Escape bash parameter expansion with double-dollar-brace so templatefile emits
# a literal bash variable reference.
# Normal bash command and arithmetic substitution should stay unescaped.
set -euo pipefail

exec > >(tee -a /var/log/k8s-bootstrap.log) 2>&1
echo "==== worker bootstrap start $(date -u +%Y-%m-%dT%H:%M:%SZ) ===="

readonly AWS_REGION='${aws_region}'
readonly SSM_JOIN_PARAM='${ssm_join_parameter_name}'
readonly K8S_VERSION='${kubernetes_version}'
readonly JOIN_MAX_ATTEMPTS='${join_max_attempts}'
readonly JOIN_SLEEP_SECONDS='${join_sleep_seconds}'

export DEBIAN_FRONTEND=noninteractive
export PATH="/usr/local/bin:$${PATH}"

log() { echo "[worker] $*"; }

disable_swap() {
  swapoff -a || true
  if [[ -f /etc/fstab ]]; then
    sed -i.bak '/[[:space:]]swap[[:space:]]/s/^/#/' /etc/fstab || true
  fi
}

load_kernel_modules() {
  cat >/etc/modules-load.d/k8s.conf <<'EOF'
overlay
br_netfilter
EOF
  modprobe overlay
  modprobe br_netfilter

  cat >/etc/sysctl.d/99-kubernetes-cri.conf <<'EOF'
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
  sysctl --system >/dev/null
}

install_containerd() {
  apt-get update -y
  apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release jq unzip
  apt-get install -y containerd

  mkdir -p /etc/containerd
  containerd config default >/etc/containerd/config.toml
  sed -i 's/SystemdCgroup *= *false/SystemdCgroup = true/' /etc/containerd/config.toml

  systemctl enable containerd
  systemctl restart containerd
}

install_kubernetes() {
  # k8s_major_minor is rendered by Terraform templatefile (e.g. "1.31").
  # Keep the repo version prefix as a Terraform-provided value so the final script
  # can use normal bash expansion without mixing in command substitution here.
  local major_minor="${k8s_major_minor}"

  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://pkgs.k8s.io/core:/stable:/v$${major_minor}/deb/Release.key" \
    | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
  echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v$${major_minor}/deb/ /" \
    >/etc/apt/sources.list.d/kubernetes.list

  apt-get update -y
  # Workers need kubeadm + kubelet; kubectl is optional but useful for debugging.
  apt-get install -y \
    "kubelet=$${K8S_VERSION}-*" \
    "kubeadm=$${K8S_VERSION}-*" \
    "kubectl=$${K8S_VERSION}-*"
  apt-mark hold kubelet kubeadm kubectl
  systemctl enable --now kubelet
}

install_awscli() {
  if command -v aws >/dev/null 2>&1; then
    return 0
  fi
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  /tmp/aws/install
  rm -rf /tmp/aws /tmp/awscliv2.zip
}

fetch_join_command() {
  aws ssm get-parameter \
    --region "$${AWS_REGION}" \
    --name "$${SSM_JOIN_PARAM}" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text 2>/dev/null
}

wait_and_join() {
  local attempt=1
  local join_cmd=""

  while (( attempt <= JOIN_MAX_ATTEMPTS )); do
    log "Join attempt $${attempt}/$${JOIN_MAX_ATTEMPTS}: reading SSM parameter"

    if join_cmd="$(fetch_join_command)" && [[ -n "$${join_cmd}" && "$${join_cmd}" != "None" ]]; then
      log "Retrieved join command from SSM (not logging secret contents)"
      # Join command is produced by kubeadm; run via bash -c (no eval).
      if bash -c "$${join_cmd}"; then
        log "kubeadm join succeeded"
        return 0
      fi
      log "kubeadm join failed; will retry"
    else
      log "Join parameter not ready yet"
    fi

    sleep "$${JOIN_SLEEP_SECONDS}"
    attempt=$((attempt + 1))
  done

  log "ERROR: exhausted join attempts"
  return 1
}

main() {
  if [[ -f /etc/kubernetes/kubelet.conf ]]; then
    log "Node already joined (kubelet.conf present); nothing to do"
    touch /var/lib/k8s-bootstrap.worker.done
    exit 0
  fi

  if [[ -f /var/lib/k8s-bootstrap.worker.done ]]; then
    log "Worker bootstrap marker present but kubelet.conf missing; continuing join"
  fi

  disable_swap
  load_kernel_modules
  install_containerd
  install_kubernetes
  install_awscli
  wait_and_join
  touch /var/lib/k8s-bootstrap.worker.done
  log "==== worker bootstrap complete $(date -u +%Y-%m-%dT%H:%M:%SZ) ===="
}

main "$@"

