# Ops Assistant

A usable Kubernetes operations assistant. You ask questions in natural language; the app inspects a live cluster and answers with facts. Destructive actions are blocked by application guardrails **and** Kubernetes RBAC.

This repository includes:

- a Python agent with Amazon Bedrock + MCP (`agent/`)
- a FastAPI backend (`backend/`)
- a simple React + Vite frontend (`frontend/`)
- a self-managed AWS kubeadm cluster (`infra/`, not EKS)
- Kubernetes manifests for in-cluster deployment (`k8s/`)
- Observability: metrics-server + Prometheus/Grafana/Alertmanager (`k8s/monitoring/`)
- SNS alerts topic (Terraform) for Alertmanager notifications

## What this project solves

Operators can ask questions such as “show me the nodes”, “why is this pod failing?”, or “analyze the health of my cluster?” and get answers from Kubernetes state plus Prometheus metrics. The assistant may scale workloads when asked. It cannot delete resources. Alertmanager can notify via SNS for meaningful failures.

## Architecture

```
User
  → React frontend
    → FastAPI backend
      → Amazon Bedrock agent
        → Guardrails
          → MCP (kubectl_*) + prometheus_query
            → Kubernetes API / Prometheus
              → Kubernetes RBAC / worker IAM (Bedrock + sns:Publish)

Observability side:
Kubernetes
  → metrics-server
  → Prometheus
  → Alertmanager
  → SNS (ops-assistant-dev-alerts)

Prometheus
  → Ops Assistant prometheus_query
  → AI diagnosis
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
- `prometheus_query` (predefined PromQL query types only)

Blocked examples: `kubectl_delete`, `cleanup`, `cleanup_pods`, `kubectl_generic`, Helm uninstall tools, and node management.

## Configuration

Copy `agent/.env.example` to `agent/.env` (gitignored). Do not commit it.

```text
LLM_PROVIDER=bedrock
AWS_REGION=us-east-1
BEDROCK_MODEL=us.amazon.nova-2-lite-v1:0
KUBECONFIG=C:\absolute\path\to\.kube\aws-dev-config
PROMETHEUS_URL=http://127.0.0.1:9090
```

Save the file as UTF-8 **without BOM**. Bedrock uses the default AWS credential chain (local profile / instance role). No Bedrock API key is used.

Nova 2 Lite in `us-east-1` requires the US geo inference profile ID (`us.amazon.nova-2-lite-v1:0`); the bare foundation model ID is not supported for on-demand Converse.

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
- `GET /observability/summary`
- `GET /observability/topology?namespace=ops-assistant` (visual Cluster Health dashboard; no Bedrock)
- `POST /chat` with `{"message":"Show me the Kubernetes nodes."}`

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Vite proxies `/health`, `/cluster`, `/observability`, and `/chat` to `http://127.0.0.1:8000`. Open http://127.0.0.1:5173.

## Observability (metrics-server + Prometheus)

See `k8s/monitoring/README.md` for full install steps.

Quick path:

```powershell
# metrics-server (kubeadm needs --kubelet-insecure-tls)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json --patch-file k8s/monitoring/metrics-server-json-patch.json
kubectl top nodes
kubectl top pods -A

# Prometheus stack (modest resources, Grafana ClusterIP only)
.\tools\helm.exe repo add prometheus-community https://prometheus-community.github.io/helm-charts
.\tools\helm.exe repo update
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
.\tools\helm.exe upgrade --install ops-monitor prometheus-community/kube-prometheus-stack `
  -n monitoring -f k8s/monitoring/values.yaml

# Grafana via port-forward (do not open unrestricted NodePort)
kubectl -n monitoring port-forward svc/ops-monitor-grafana 3000:80
```

### prometheus_query types

`top_pod_cpu`, `top_pod_memory`, `node_cpu_usage`, `node_memory_usage`, `pod_restarts_1h`, `pods_crashloop`, `deployment_unavailable_replicas`, `node_not_ready`, `pod_phase_not_running`, `cluster_cpu_summary`, `cluster_memory_summary`.

### Health diagnosis examples

```text
Analyze the health of my Kubernetes cluster.
Why is my cluster unhealthy?
Diagnose current workload problems.
Which pod is using the most memory?
```

### SNS alerts

Terraform creates topic `ops-assistant-dev-alerts` and optional email subscription via `alert_email` in `infra/environments/dev/terraform.tfvars`.

1. Set `alert_email` (or leave empty for topic-only).
2. When approved, apply **only** SNS/IAM targets (see below). Do not untargeted-apply if the plan replaces the control plane.
3. Confirm the SNS subscription email.
4. Alertmanager publishes with SigV4 using the **worker EC2 instance role** (`sns:Publish` on that topic only). IMDSv2 remains `http_tokens=required` with hop limit 2.

```powershell
cd infra
..\tools\terraform.exe plan -var-file="environments/dev/terraform.tfvars" `
  -target=aws_sns_topic.alerts `
  -target=aws_iam_role_policy.workers_sns_alerts
# apply the same -target list only after approval
```

Alert rules: `NodeNotReady`, `PodCrashLooping`, `PodHighRestartRate`, `DeploymentReplicasUnavailable`, `HighNodeCPU`, `HighNodeMemory`.

### Safe failure demo

```powershell
kubectl apply -f k8s/demo/crashloop-demo.yaml
kubectl -n ops-assistant-demo get pods -w
# Expect CrashLoopBackOff; Prometheus/Alertmanager should notice; ask the assistant to diagnose.
# Cleanup:
kubectl delete -f k8s/demo/crashloop-demo.yaml
```

Does **not** modify CoreDNS or system components.

## Docker

Build from the repository root. Do **not** bake AWS credentials into an image.

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

A full untargeted apply can still change IAM/SNS. Worker launch-template `user_data` is ignored to avoid CRLF drift replacing future ASG instances. The live control-plane instance ignores `ami` / `user_data` so bootstrap-script drift does not replace it. See `infra/README.md`.

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
# Bedrock uses the worker instance IAM role; no LLM API-key secret is required.
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
agent\.venv\Scripts\python.exe -m pytest agent\test_agent_namespace.py agent\test_agent_loop.py agent\test_prometheus_query.py agent\test_observability_config.py agent\test_bedrock_smoke.py backend\test_app.py backend\test_observability.py backend\test_topology.py -q
cd frontend; npm run build
```

GitHub Actions (`.github/workflows/ci.yml`) runs those tests and builds both Docker images. It does not deploy.

## Local kind development

Kind remains supported for the CLI agent. Follow `agent/README.md` to create `ops-assistant-dev` and point `KUBECONFIG` at `agent/kind-kubeconfig`.

## Out of scope

EKS, Argo CD, Grafana public exposure, and extra observability stacks beyond metrics-server + kube-prometheus-stack are not part of this delivery.
