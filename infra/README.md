# Phase 2 infrastructure — AWS EC2 + kubeadm (not EKS)

## Status

**Networking + security groups implemented in code; nothing applied to AWS yet.**
Do not run `terraform apply` until explicitly approved.

| Area | Status |
|------|--------|
| Directory layout / variables / providers | Present |
| VPC / public subnets / IGW / routes | **Implemented** (not applied yet) |
| Security groups (control-plane + workers) | **Implemented** (not applied yet) |
| IAM roles / instance profiles | **Implemented** (not applied yet) |
| EC2 control-plane + worker LT/ASG | **Implemented** (not applied yet) |
| kubeadm / Calico VXLAN bootstrap user_data | **Implemented** (not applied yet) |
| Live `terraform apply` | Pending approval |
| kubeadm user-data scripts | Placeholders only (`exit 1`) |
| Remote state backend | Pending |
| Docker / CI / agent container | Out of scope (Phases 3–4) |

## Architecture

```
[Laptop — Phase 1 unchanged]
  agent.py → guardrails → MCP (npx) → kubectl
                 │
                 │  KUBECONFIG switch
                 ▼
[AWS — Phase 2 target]
  VPC + public subnets + IGW + routes
       │
       ├── EC2 control-plane  (kubeadm init via user-data)
       └── EC2 worker(s)      (kubeadm join via user-data)
```

- **Terraform** provisions AWS networking, IAM, security groups, and EC2.
- **kubeadm bootstrap scripts** (later) install the Kubernetes control plane
  and join workers on those EC2 instances.
- The **agent stays local**; MCP stays local via `npx`.
- **kind** remains the local development cluster (see below).

## Why EC2 + kubeadm (not EKS)

Phase 2 deliberately uses self-managed Kubernetes on EC2:

1. Clear separation between **cloud infrastructure** (Terraform) and
   **Kubernetes bootstrap** (kubeadm scripts).
2. Full visibility into control-plane components for learning/demo purposes.
3. Avoids EKS-specific control plane, addons, and IAM authenticator coupling.
4. Matches the project decision: managed VMs + manual Kubernetes, not EKS.

## What Terraform will provision (when implemented)

- VPC and public subnet(s)
- Internet Gateway and route tables
- Security groups (SSH, Kubernetes API `6443`, node communication)
- IAM roles / instance profiles for EC2 nodes
- One EC2 **control-plane** instance
- One or more EC2 **worker** instances (fixed count first; ASG optional later)

Terraform will **not** create an EKS cluster.

## What kubeadm / bootstrap will configure (when implemented)

| Script | Role |
|--------|------|
| `modules/k8s-cluster/scripts/control-plane.sh` | container runtime, kubeadm/kubelet, `kubeadm init`, **Calico VXLAN**, admin kubeconfig |
| `modules/k8s-cluster/scripts/worker.sh` | runtime + kubeadm, `kubeadm join` |

These scripts are **placeholders** today and must not be attached as user-data yet.

## CNI decision: Calico VXLAN

This cluster will use **Calico** as the Kubernetes CNI, in **VXLAN** encapsulation mode
(not BGP peering, not IP-in-IP).

| Item | Choice |
|------|--------|
| CNI | Calico |
| Dataplane / encapsulation | VXLAN |
| Node overlay port | **UDP 4789** (SG-to-SG between control-plane and workers only) |
| BGP TCP 179 | **Not opened** (not required for VXLAN mode) |
| IP-in-IP (protocol 4) | **Not opened** (not required for VXLAN mode) |

Security groups no longer allow “all protocols” between nodes for CNI. Overlay traffic
is limited to UDP/4789 via security-group references. Kubernetes control-plane ports
(API 6443, etcd, kubelet, scheduler, controller-manager) remain as dedicated rules.

Bootstrap scripts will install Calico in VXLAN mode later; they are still placeholders.

## Control-plane / worker layout

- **1× control-plane** EC2 node (single CP for Phase 2 simplicity; no HA etcd yet)
- **N× workers** (dev default: 1), sized via `worker_count`
- Nodes intended to be reachable for admin SSH and for the laptop to use the
  API server (exact SG CIDRs TBD before networking implementation)

## How the local agent will connect

1. After the cluster is bootstrapped, copy the admin kubeconfig from the
   control-plane (path TBD: `/etc/kubernetes/admin.conf` or equivalent).
2. Save it locally as something like `agent/aws-kubeconfig` (**gitignored**).
3. Point `KUBECONFIG` in `agent/.env` at that file (or export it in the shell).
4. Run the existing agent unchanged:

   ```powershell
   agent\.venv\Scripts\python.exe agent\agent.py "list all pods in the cluster"
   ```

MCP continues to spawn `npx mcp-server-kubernetes` with that `KUBECONFIG`.

## kind remains for local development

Phase 1 workflow is unchanged:

```powershell
kind create cluster --name ops-assistant-dev
# KUBECONFIG=agent/kind-kubeconfig
```

Use **kind** for day-to-day offline work; use the **AWS kubeadm cluster** when
validating Phase 2 networking/compute. Do not remove kind docs or scripts.

## Layout

```text
infra/
├── main.tf                 # root module wiring (commented until ready)
├── variables.tf
├── outputs.tf
├── providers.tf
├── versions.tf
├── README.md               # this file
├── environments/
│   └── dev/
│       └── terraform.tfvars
└── modules/
    └── k8s-cluster/
        ├── main.tf              # VPC, subnets, IGW, routes
        ├── security_groups.tf   # control-plane + worker SGs
        ├── iam.tf               # control-plane + worker roles/profiles
        ├── ec2.tf               # control-plane instance + worker LT/ASG
        ├── variables.tf
        ├── outputs.tf
        └── scripts/
            ├── control-plane.sh  # placeholder (not wired as user_data yet)
            └── worker.sh         # placeholder (not wired as user_data yet)
```

## EC2 layout

| Component | Resource | Notes |
|-----------|----------|-------|
| AMI | `data.aws_ami.ubuntu` | Canonical Ubuntu 22.04 Jammy amd64 (dynamic) |
| Control-plane | `aws_instance` | Public subnet[0], CP SG, CP instance profile, public IP |
| Workers | `aws_launch_template` + `aws_autoscaling_group` | Across both public subnets; desired=1 by default |
| SSH key | optional `key_name` | Empty = SSM-only (recommended) |
| user_data | `scripts/control-plane.sh` / `worker.sh` | kubeadm + Calico VXLAN + SSM join |

## Bootstrap / join flow

```
control-plane EC2 (user_data)
  → install containerd (SystemdCgroup=true) + kubeadm/kubelet/kubectl
  → kubeadm init (advertise = IMDS private IPv4)
  → apply Calico VXLAN (pinned version)
  → kubeadm token create --print-join-command
  → SSM PutParameter SecureString  /ops-assistant/dev/k8s/worker-join-command
  → systemd timer refreshes the parameter every 12h

worker EC2 (ASG / user_data)
  → same runtime + kube packages
  → retry SSM GetParameter --with-decryption
  → kubeadm join …
  → skip if /etc/kubernetes/kubelet.conf already exists
```

**ASG replacement:** a new worker boots with the same LT user_data, reads the
latest join command from SSM (kept fresh by the control-plane timer), and joins.

**Runtime:** containerd (kubeadm default CRI). `SystemdCgroup = true` in
`/etc/containerd/config.toml` so kubelet’s systemd cgroup driver matches.

**Versions (defaults):** Kubernetes `1.31.4`, Calico `v3.29.1`, pod CIDR `192.168.0.0/16`.

## IAM design (nodes)

Separate roles for control-plane and workers, each with an EC2 instance profile.

| Role | Trust | Attached policy (default) |
|------|-------|---------------------------|
| `ops-assistant-dev-control-plane` | `ec2.amazonaws.com` | `AmazonSSMManagedInstanceCore` (optional) + **inline** `ssm:PutParameter`/`GetParameter` on join param only |
| `ops-assistant-dev-workers` | `ec2.amazonaws.com` | `AmazonSSMManagedInstanceCore` (optional) + **inline** `ssm:GetParameter` on join param only |

**SSM join parameter:** `/ops-assistant/dev/k8s/worker-join-command` (SecureString at runtime; not created by Terraform, so the token is not stored in TF state).

**Why SSM:** AWS-native, encrypted SecureString, least-privilege IAM by parameter ARN, works for ASG replacements without baking tokens into AMIs/user_data.

**Intentionally not attached:** EKS managed policies, ECR pull, cloud-provider-aws/CCM,
S3, autoscaling, or AdministratorAccess. IMDS does not need IAM permissions.
## Implemented now vs pending

**Now**

- Repository hygiene for Python caches
- `infra/` skeleton and documentation
- **AWS networking**: VPC, 2 public subnets (2 AZs), IGW, public route table
- **Security groups**: control-plane + workers (kubeadm ports; Calico VXLAN UDP/4789; CIDRs via tfvars)
- **CNI decision**: Calico in **VXLAN** mode (not BGP, not IP-in-IP)
- **IAM**: separate control-plane/worker roles + instance profiles; optional SSM core policy
- **EC2**: 1 control-plane instance + worker launch template/ASG
- **Bootstrap**: kubeadm init/join user_data, Calico VXLAN, SSM join parameter

**Pending (requires explicit approval)**

- `terraform apply`
- Set `allowed_api_cidrs` (laptop /32) so kubectl/agent can reach API :6443
- Retrieve admin kubeconfig from the control-plane (SSM Session Manager)
- Remote state backend
- Staging environment folder
- Agent/MCP/Docker/CI changes (not Phase 2)

Optional later hardening (not blocking):

- Narrow egress from `0.0.0.0/0` once package/registry sources are known
- Add IAM only when features need it (ECR, AWS cloud-provider/CCM, etc.)
- Revisit VXLAN rules if Calico is switched to BGP or IP-in-IP (would need different ports)

## Prerequisites (for a future apply)

- Terraform `>= 1.5`
- AWS credentials with permission to create VPC/EC2/IAM
- An EC2 key pair in the target region (`key_name`)
- Non-empty `allowed_ssh_cidrs` / `allowed_api_cidrs` (your IP, not `0.0.0.0/0`
  unless you consciously accept that risk)

## Commands (do not apply yet)

```bash
cd infra
# terraform init          # OK later for provider download; no backend yet
# terraform plan -var-file=environments/dev/terraform.tfvars
# terraform apply ...     # FORBIDDEN until networking/EC2 implementation is approved
```
