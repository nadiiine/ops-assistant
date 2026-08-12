#!/usr/bin/env bash
# control-plane.sh — rendered by Terraform templatefile().
# Installs containerd + kubeadm, runs kubeadm init, applies Calico VXLAN,
# and publishes a fresh join command to SSM Parameter Store (SecureString).
#
# Terraform interpolations use dollar-brace names (aws_region, etc.).
# Bash expansions are written as dollar-dollar-brace so templatefile emits a single dollar.
set -euo pipefail

exec > >(tee -a /var/log/k8s-bootstrap.log) 2>&1
echo "==== control-plane bootstrap start $$(date -u +%Y-%m-%dT%H:%M:%SZ) ===="

readonly AWS_REGION='${aws_region}'
readonly SSM_JOIN_PARAM='${ssm_join_parameter_name}'
readonly K8S_VERSION='${kubernetes_version}'
readonly CALICO_VERSION='${calico_version}'
readonly POD_CIDR='${pod_network_cidr}'
readonly JOIN_TOKEN_TTL='${join_token_ttl}'

export DEBIAN_FRONTEND=noninteractive
export PATH="/usr/local/bin:$${PATH}"

log() { echo "[control-plane] $*"; }

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
  # containerd is the CRI for kubeadm. SystemdCgroup=true matches kubelet's
  # default systemd cgroup driver on Ubuntu.
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
  local major_minor
  major_minor="$$(echo "$${K8S_VERSION}" | cut -d. -f1,2)"

  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://pkgs.k8s.io/core:/stable:/v$${major_minor}/deb/Release.key" \
    | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
  echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v$${major_minor}/deb/ /" \
    >/etc/apt/sources.list.d/kubernetes.list

  apt-get update -y
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

private_ipv4() {
  local token
  token="$$(curl -fsS -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")"
  curl -fsS -H "X-aws-ec2-metadata-token: $${token}" \
    http://169.254.169.254/latest/meta-data/local-ipv4
}

configure_admin_kubeconfig() {
  mkdir -p /root/.kube
  cp -f /etc/kubernetes/admin.conf /root/.kube/config
  chmod 600 /root/.kube/config

  if id ubuntu >/dev/null 2>&1; then
    mkdir -p /home/ubuntu/.kube
    cp -f /etc/kubernetes/admin.conf /home/ubuntu/.kube/config
    chown -R ubuntu:ubuntu /home/ubuntu/.kube
    chmod 600 /home/ubuntu/.kube/config
  fi
}

publish_join_command() {
  local join_cmd
  join_cmd="$$(kubeadm token create --ttl "$${JOIN_TOKEN_TTL}" --print-join-command)"
  aws ssm put-parameter \
    --region "$${AWS_REGION}" \
    --name "$${SSM_JOIN_PARAM}" \
    --type SecureString \
    --value "$${join_cmd}" \
    --overwrite >/dev/null
  log "Published join command to $${SSM_JOIN_PARAM} (value not logged)"
}

setup_join_refresh_timer() {
  # ASG replacements may launch after the initial token TTL; refresh SSM every 12h.
  cat >/usr/local/sbin/k8s-refresh-join.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
JOIN_CMD="\$(kubeadm token create --ttl ${join_token_ttl} --print-join-command)"
aws ssm put-parameter --region ${aws_region} --name '${ssm_join_parameter_name}' \
  --type SecureString --value "\$JOIN_CMD" --overwrite >/dev/null
logger -t k8s-refresh-join "Updated SSM join parameter"
EOF
  chmod 0755 /usr/local/sbin/k8s-refresh-join.sh

  cat >/etc/systemd/system/k8s-refresh-join.service <<'EOF'
[Unit]
Description=Refresh kubeadm join command in SSM Parameter Store
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/k8s-refresh-join.sh
EOF

  cat >/etc/systemd/system/k8s-refresh-join.timer <<'EOF'
[Unit]
Description=Refresh kubeadm join command every 12 hours

[Timer]
OnBootSec=15min
OnUnitActiveSec=12h
Persistent=true

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now k8s-refresh-join.timer
}

install_calico_vxlan() {
  local manifest="/tmp/calico-$${CALICO_VERSION}.yaml"
  curl -fsSL -o "$${manifest}" \
    "https://raw.githubusercontent.com/projectcalico/calico/$${CALICO_VERSION}/manifests/calico.yaml"

  sed -i \
    -e '/name: CALICO_IPV4POOL_IPIP/{n;s/value: ".*"/value: "Never"/}' \
    -e '/name: CALICO_IPV4POOL_VXLAN/{n;s/value: ".*"/value: "Always"/}' \
    "$${manifest}"

  kubectl --kubeconfig=/etc/kubernetes/admin.conf apply -f "$${manifest}"
  log "Applied Calico $${CALICO_VERSION} (VXLAN Always, IPIP Never)"
}

run_kubeadm_init() {
  if [[ -f /etc/kubernetes/admin.conf ]]; then
    log "Cluster already initialized; refreshing join command"
    publish_join_command
    setup_join_refresh_timer
    return 0
  fi

  local advertise
  advertise="$$(private_ipv4)"
  log "kubeadm init apiserver-advertise-address=$${advertise} pod-network-cidr=$${POD_CIDR}"

  kubeadm init \
    --apiserver-advertise-address="$${advertise}" \
    --pod-network-cidr="$${POD_CIDR}" \
    --cri-socket=unix:///run/containerd/containerd.sock

  configure_admin_kubeconfig
  install_calico_vxlan
  publish_join_command
  setup_join_refresh_timer
}

main() {
  if [[ -f /var/lib/k8s-bootstrap.control-plane.done && -f /etc/kubernetes/admin.conf ]]; then
    log "Marker present; refreshing join command only"
    publish_join_command || true
    exit 0
  fi

  disable_swap
  load_kernel_modules
  install_containerd
  install_kubernetes
  install_awscli
  run_kubeadm_init
  touch /var/lib/k8s-bootstrap.control-plane.done
  log "==== control-plane bootstrap complete $$(date -u +%Y-%m-%dT%H:%M:%SZ) ===="
}

main "$@"

