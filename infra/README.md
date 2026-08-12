# Phase 2 infrastructure — AWS EC2 + kubeadm (not EKS)

## Status

**Skeleton only.** Terraform files and bootstrap script placeholders exist so the
repository layout matches the Phase 2 plan. **No AWS resources are defined or
created yet.** Do not run `terraform apply`.

| Area | Status |
|------|--------|
| Directory layout / variables / providers | Present (skeleton) |
| VPC / subnets / IGW / routes | Pending |
| Security groups / IAM / EC2 | Pending |
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
| `modules/k8s-cluster/scripts/control-plane.sh` | container runtime, kubeadm/kubelet, `kubeadm init`, CNI, admin kubeconfig |
| `modules/k8s-cluster/scripts/worker.sh` | runtime + kubeadm, `kubeadm join` |

These scripts are **placeholders** today and must not be attached as user-data yet.

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
        ├── main.tf           # no aws_* resources yet
        ├── variables.tf
        ├── outputs.tf
        └── scripts/
            ├── control-plane.sh  # placeholder
            └── worker.sh         # placeholder
```

## Implemented now vs pending

**Now**

- Repository hygiene for Python caches
- `infra/` skeleton and documentation
- Variable surface for future networking/EC2
- Placeholder kubeadm scripts

**Pending (requires explicit approval)**

- VPC, subnets, IGW, routes
- Security groups and IAM
- EC2 instances / optional ASG
- Real bootstrap script contents
- Remote state backend
- `terraform plan` / `apply`
- Staging environment folder
- Agent/MCP/Docker/CI changes (not Phase 2)

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
