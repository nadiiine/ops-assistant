# Security groups for self-managed kubeadm nodes (no EC2 yet).
#
# Port selection follows Kubernetes / kubeadm published ports:
# https://kubernetes.io/docs/reference/networking/ports-and-protocols/
#
# CNI: Calico in VXLAN mode (UDP/4789) between cluster node SGs only.
# BGP (TCP/179) and IP-in-IP (protocol 4) are not used in this mode.

################################################################################
# Control-plane security group
################################################################################

resource "aws_security_group" "control_plane" {
  name        = "${local.name_prefix}-control-plane"
  description = "kubeadm control-plane node (API, etcd, control components)"
  vpc_id      = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-control-plane-sg"
    Role = "control-plane"
  })
}

# SSH from trusted operator CIDRs only (never 0.0.0.0/0 by default).
resource "aws_vpc_security_group_ingress_rule" "control_plane_ssh" {
  for_each = toset(var.allowed_ssh_cidrs)

  security_group_id = aws_security_group.control_plane.id
  description       = "SSH from trusted CIDR"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = each.value

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-ssh"
  })
}

# Kubernetes API for the local agent / operators (configurable CIDRs).
resource "aws_vpc_security_group_ingress_rule" "control_plane_api_external" {
  for_each = toset(var.allowed_api_cidrs)

  security_group_id = aws_security_group.control_plane.id
  description       = "Kubernetes API (6443) from trusted external CIDR"
  ip_protocol       = "tcp"
  from_port         = 6443
  to_port           = 6443
  cidr_ipv4         = each.value

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-api-ext"
  })
}

# Workers must reach the API server for kubelet / kube-proxy.
resource "aws_vpc_security_group_ingress_rule" "control_plane_api_from_workers" {
  security_group_id            = aws_security_group.control_plane.id
  description                  = "Kubernetes API (6443) from worker nodes"
  ip_protocol                  = "tcp"
  from_port                    = 6443
  to_port                      = 6443
  referenced_security_group_id = aws_security_group.workers.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-api-workers"
  })
}

# etcd client/peer — control-plane only (required for kubeadm; needed for future HA).
resource "aws_vpc_security_group_ingress_rule" "control_plane_etcd" {
  security_group_id            = aws_security_group.control_plane.id
  description                  = "etcd client/peer (2379-2380) from control-plane"
  ip_protocol                  = "tcp"
  from_port                    = 2379
  to_port                      = 2380
  referenced_security_group_id = aws_security_group.control_plane.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-etcd"
  })
}

# kubelet API on the control-plane node.
resource "aws_vpc_security_group_ingress_rule" "control_plane_kubelet_from_cp" {
  security_group_id            = aws_security_group.control_plane.id
  description                  = "kubelet API (10250) from control-plane"
  ip_protocol                  = "tcp"
  from_port                    = 10250
  to_port                      = 10250
  referenced_security_group_id = aws_security_group.control_plane.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-kubelet-cp"
  })
}

resource "aws_vpc_security_group_ingress_rule" "control_plane_kubelet_from_workers" {
  security_group_id            = aws_security_group.control_plane.id
  description                  = "kubelet API (10250) from workers"
  ip_protocol                  = "tcp"
  from_port                    = 10250
  to_port                      = 10250
  referenced_security_group_id = aws_security_group.workers.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-kubelet-workers"
  })
}

# kube-scheduler and kube-controller-manager secure ports (control-plane only).
resource "aws_vpc_security_group_ingress_rule" "control_plane_scheduler" {
  security_group_id            = aws_security_group.control_plane.id
  description                  = "kube-scheduler (10259) from control-plane"
  ip_protocol                  = "tcp"
  from_port                    = 10259
  to_port                      = 10259
  referenced_security_group_id = aws_security_group.control_plane.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-scheduler"
  })
}

resource "aws_vpc_security_group_ingress_rule" "control_plane_controller_manager" {
  security_group_id            = aws_security_group.control_plane.id
  description                  = "kube-controller-manager (10257) from control-plane"
  ip_protocol                  = "tcp"
  from_port                    = 10257
  to_port                      = 10257
  referenced_security_group_id = aws_security_group.control_plane.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-controller"
  })
}

# Calico VXLAN overlay (UDP/4789) — SG-to-SG only; not exposed publicly.
resource "aws_vpc_security_group_ingress_rule" "control_plane_calico_vxlan_from_workers" {
  security_group_id            = aws_security_group.control_plane.id
  description                  = "Calico VXLAN (UDP/4789) from workers"
  ip_protocol                  = "udp"
  from_port                    = 4789
  to_port                      = 4789
  referenced_security_group_id = aws_security_group.workers.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-calico-vxlan-workers"
  })
}

resource "aws_vpc_security_group_ingress_rule" "control_plane_calico_vxlan_from_self" {
  security_group_id            = aws_security_group.control_plane.id
  description                  = "Calico VXLAN (UDP/4789) within control-plane SG"
  ip_protocol                  = "udp"
  from_port                    = 4789
  to_port                      = 4789
  referenced_security_group_id = aws_security_group.control_plane.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-calico-vxlan-self"
  })
}

resource "aws_vpc_security_group_egress_rule" "control_plane_all" {
  security_group_id = aws_security_group.control_plane.id
  description       = "Allow all egress (package mirrors, container images, AWS APIs)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cp-egress"
  })
}

################################################################################
# Worker security group
################################################################################

resource "aws_security_group" "workers" {
  name        = "${local.name_prefix}-workers"
  description = "kubeadm worker nodes (kubelet, kube-proxy, CNI)"
  vpc_id      = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-workers-sg"
    Role = "worker"
  })
}

resource "aws_vpc_security_group_ingress_rule" "workers_ssh" {
  for_each = toset(var.allowed_ssh_cidrs)

  security_group_id = aws_security_group.workers.id
  description       = "SSH from trusted CIDR"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = each.value

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-worker-ssh"
  })
}

# Control plane must reach kubelet on workers.
resource "aws_vpc_security_group_ingress_rule" "workers_kubelet_from_cp" {
  security_group_id            = aws_security_group.workers.id
  description                  = "kubelet API (10250) from control-plane"
  ip_protocol                  = "tcp"
  from_port                    = 10250
  to_port                      = 10250
  referenced_security_group_id = aws_security_group.control_plane.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-worker-kubelet-cp"
  })
}

resource "aws_vpc_security_group_ingress_rule" "workers_kubelet_from_workers" {
  security_group_id            = aws_security_group.workers.id
  description                  = "kubelet API (10250) from other workers"
  ip_protocol                  = "tcp"
  from_port                    = 10250
  to_port                      = 10250
  referenced_security_group_id = aws_security_group.workers.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-worker-kubelet-workers"
  })
}

# kube-proxy health check port.
resource "aws_vpc_security_group_ingress_rule" "workers_kube_proxy_from_cp" {
  security_group_id            = aws_security_group.workers.id
  description                  = "kube-proxy (10256) from control-plane"
  ip_protocol                  = "tcp"
  from_port                    = 10256
  to_port                      = 10256
  referenced_security_group_id = aws_security_group.control_plane.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-worker-kube-proxy-cp"
  })
}

resource "aws_vpc_security_group_ingress_rule" "workers_kube_proxy_from_workers" {
  security_group_id            = aws_security_group.workers.id
  description                  = "kube-proxy (10256) from other workers"
  ip_protocol                  = "tcp"
  from_port                    = 10256
  to_port                      = 10256
  referenced_security_group_id = aws_security_group.workers.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-worker-kube-proxy-workers"
  })
}

# Optional NodePort exposure — only from explicitly configured CIDRs (not 0.0.0.0/0).
resource "aws_vpc_security_group_ingress_rule" "workers_nodeport" {
  for_each = toset(var.allowed_nodeport_cidrs)

  security_group_id = aws_security_group.workers.id
  description       = "NodePort Services (30000-32767) from trusted CIDR"
  ip_protocol       = "tcp"
  from_port         = 30000
  to_port           = 32767
  cidr_ipv4         = each.value

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-worker-nodeport"
  })
}

# Calico VXLAN overlay (UDP/4789) between workers and from control-plane.
resource "aws_vpc_security_group_ingress_rule" "workers_calico_vxlan_from_cp" {
  security_group_id            = aws_security_group.workers.id
  description                  = "Calico VXLAN (UDP/4789) from control-plane"
  ip_protocol                  = "udp"
  from_port                    = 4789
  to_port                      = 4789
  referenced_security_group_id = aws_security_group.control_plane.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-worker-calico-vxlan-cp"
  })
}

resource "aws_vpc_security_group_ingress_rule" "workers_calico_vxlan_from_workers" {
  security_group_id            = aws_security_group.workers.id
  description                  = "Calico VXLAN (UDP/4789) between workers"
  ip_protocol                  = "udp"
  from_port                    = 4789
  to_port                      = 4789
  referenced_security_group_id = aws_security_group.workers.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-worker-calico-vxlan-workers"
  })
}

resource "aws_vpc_security_group_egress_rule" "workers_all" {
  security_group_id = aws_security_group.workers.id
  description       = "Allow all egress (package mirrors, container images, AWS APIs)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-worker-egress"
  })
}
