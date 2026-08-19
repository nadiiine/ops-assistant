# Ops Assistant

A usable Kubernetes operations assistant. You ask questions in natural language; the app inspects a live cluster and answers with facts. Destructive actions are blocked by application guardrails **and** Kubernetes RBAC.

This repository includes:

- a Python agent with OpenAI + MCP (`agent/`)
- a FastAPI backend (`backend/`)
- a simple React + Vite frontend (`frontend/`)
- a self-managed AWS kubeadm cluster (`infra/`, not EKS)
- Kubernetes manifests for in-cluster deployment (`k8s/`)

## What this project solves

Operators can ask questions such as “show me the nodes” or “why is this pod failing?” and get answers from the real cluster API. The assistant may scale workloads when asked. It cannot delete resources.

## Architecture

```
Browser
  → Frontend (nginx)
    → FastAPI backend
      → OpenAI agent (agent/agent.py)
        → Guardrails (agent/guardrails.py)
          → KubernetesMCPClient (agent/mcp_client.py)
            → mcp-server-kubernetes
              → in-cluster ServiceAccount (or local KUBECONFIG)
                → Kubernetes API
```

The frontend never talks to MCP or Kubernetes directly.

## Security model

Two independent layers:

1. **LLM guardrails** — every MCP tool the model requests is checked by `check_tool_call()` before execution. `kubectl_delete` and other destructive tools are refused.
2. **Kubernetes RBAC** — the in-cluster backend uses ServiceAccount `ops-assistant-backend` with get/list/watch (and scale patch only on `*/scale`). It is **not** `cluster-admin`. There is no delete verb.

Do not copy the admin kubeconfig into the backend pod. In the cluster, kubectl/MCP use the mounted ServiceAccount token.

## Allowed tools

- `ping`
- `kubectl_get`
- `kubectl_describe`
- `kubectl_logs`
- `explain_resource`
- `list_api_resources`
- `kubectl_context`
- `kubectl_scale`

Blocked examples: `kubectl_delete`, `cleanup`, `cleanup_pods`, `kubectl_generic`, Helm uninstall tools, and node management.

## Configuration

Copy `agent/.env.example` to `agent/.env` (gitignored). Do not commit it.

```text
OPENAI_API_KEY=your-openai-api-key-here
KUBECONFIG=C:\absolute\path\to\.kube\aws-dev-config
OPENAI_MODEL=gpt-4o-mini
```

Save the file as UTF-8 **without BOM**. ChatGPT Plus is not API billing; the key needs prepaid OpenAI API credits.

### KUBECONFIG

- **AWS cluster (local laptop):** `.kube/aws-dev-config` (gitignored). Point `server` at the control-plane public IP on port 6443 and set `tls-server-name` to the control-plane private IP.
- **Local kind:** `agent/kind-kubeconfig` (gitignored). See `agent/README.md`.
- **In-cluster backend:** leave `KUBECONFIG` unset so the ServiceAccount is used.

## Local run

### CLI agent

```powershell
cd agent
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe agent.py "Show me the Kubernetes nodes."
```

### Backend

```powershell
.\agent\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:PYTHONPATH = (Resolve-Path agent).Path
.\agent\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

- `GET /health`
- `GET /cluster/status`
- `POST /chat` with `{"message":"Show me the Kubernetes nodes."}`

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Vite proxies `/health`, `/cluster`, and `/chat` to `http://127.0.0.1:8000`. Open http://127.0.0.1:5173.

## Docker

Build from the repository root. Do **not** bake `OPENAI_API_KEY` into an image.

```powershell
docker build -f backend/Dockerfile -t ops-assistant-backend:local .
docker build -f frontend/Dockerfile -t ops-assistant-frontend:local .
```

The backend image includes Python, Node/npx, kubectl, and `mcp-server-kubernetes`.

## AWS Kubernetes (not EKS)

Terraform in `infra/` provisions:

- VPC, two public subnets, Internet Gateway, public route table
- one control-plane EC2 instance
- worker nodes via Launch Template + Auto Scaling Group
- Ubuntu 22.04, containerd, Kubernetes 1.31.x
- Calico CNI in **VXLAN** mode (UDP 4789)
- SSM Parameter Store join command for workers
- ECR repositories for the backend and frontend images
- worker IAM: SSM + least-privilege join parameter + ECR pull

There is no AWS cloud controller, so `Service type: LoadBalancer` will stay Pending. External access uses **NodePort** plus `allowed_nodeport_cidrs` in `infra/environments/dev/terraform.tfvars`.

```powershell
cd infra
..\tools\terraform.exe init
..\tools\terraform.exe plan -var-file="environments/dev/terraform.tfvars"
```

A full untargeted apply can still change the worker launch template (new user_data for future ASG instances). The live control-plane instance ignores `ami` / `user_data` so bootstrap-script drift does not replace it. See `infra/README.md`.

## Kubernetes deployment

Images:

- `228281126655.dkr.ecr.us-east-1.amazonaws.com/ops-assistant-dev-backend:latest`
- `228281126655.dkr.ecr.us-east-1.amazonaws.com/ops-assistant-dev-frontend:latest`

```powershell
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 228281126655.dkr.ecr.us-east-1.amazonaws.com
docker tag ops-assistant-backend:local 228281126655.dkr.ecr.us-east-1.amazonaws.com/ops-assistant-dev-backend:latest
docker tag ops-assistant-frontend:local 228281126655.dkr.ecr.us-east-1.amazonaws.com/ops-assistant-dev-frontend:latest
docker push 228281126655.dkr.ecr.us-east-1.amazonaws.com/ops-assistant-dev-backend:latest
docker push 228281126655.dkr.ecr.us-east-1.amazonaws.com/ops-assistant-dev-frontend:latest

$env:KUBECONFIG = (Resolve-Path .kube\aws-dev-config).Path
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/configmap.yaml
kubectl -n ops-assistant create secret generic ops-assistant --from-literal=OPENAI_API_KEY="$env:OPENAI_API_KEY"
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/backend-service.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/frontend-service.yaml
```

Do not apply `k8s/secret-example.yaml` with a real key. `k8s/ingress.yaml` is optional; this cluster has no ingress controller.

Frontend NodePort is **30080**. Current worker public IP:

```text
http://54.92.213.194:30080
```

Get a current worker IP with:

```powershell
aws ec2 describe-instances --filters "Name=tag:aws:autoscaling:groupName,Values=ops-assistant-dev-workers" "Name=instance-state-name,Values=running" --query "Reservations[].Instances[].PublicIpAddress" --output text
```

The backend Service stays ClusterIP. The browser talks only to the frontend; nginx proxies API calls to the backend.

kubeadm kubelet does not use the instance IAM role for ECR by default. Workers have `AmazonEC2ContainerRegistryReadOnly` (pull/auth only, not ECR admin). The kubelet ECR credential provider is installed automatically after `kubeadm join` in worker user_data (`modules/k8s-cluster/scripts/install-ecr-kubelet-creds.sh`), so ASG replacements can pull private images. The same installer can be re-run on a live node via `infra/scripts/install-ecr-kubelet-creds.sh`.

## Tests

```powershell
agent\.venv\Scripts\python.exe agent\test_guardrails.py -v
agent\.venv\Scripts\python.exe -m pytest backend\test_app.py -q
cd frontend; npm run build
```

GitHub Actions (`.github/workflows/ci.yml`) runs those tests and builds both Docker images. It does not deploy.

## Local kind development

Kind remains supported for the CLI agent. Follow `agent/README.md` to create `ops-assistant-dev` and point `KUBECONFIG` at `agent/kind-kubeconfig`.

## Out of scope

EKS, Argo CD, Helm charts, TLS/DNS, and extra observability stacks are not part of this delivery.
