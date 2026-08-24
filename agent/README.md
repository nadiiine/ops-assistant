# Agent: Kubernetes Ops Assistant

A local Python agent that talks to a Kubernetes cluster through the
[`mcp-server-kubernetes`](https://www.npmjs.com/package/mcp-server-kubernetes) MCP server.
It supports a local **kind** cluster and the Phase 2 **AWS kubeadm** cluster via `KUBECONFIG`.
Read operations plus controlled mutations (scale) are allowed; guardrails block destructive
actions such as deletes.

See the repository root `README.md` for the full architecture and AWS usage.

## Prerequisites

| Tool | Purpose | Verified version (this setup) |
|------|---------|----------------------------------|
| Docker Desktop | Runs kind nodes | 28.3.2 (daemon running) |
| Node.js / npx | MCP Kubernetes server | v22.16.0 / 10.9.2 |
| kubectl | Cluster CLI | v1.32.2 |
| kind | Local Kubernetes cluster | v0.27.0 (project-local binary) |
| Python | Agent runtime | 3.11+ (used 3.11.9) |

On Windows, if `kind` is not on PATH, this repo includes a local binary at
`../tools/kind.exe`. Add that directory to PATH or call it explicitly.

## One-time setup

Run these from the repository root (`fursa-project/`).

### 1. Python virtual environment

```powershell
cd agent
py -3.11 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 2. kind cluster + kubeconfig

```powershell
# From repo root; ensure tools/kind.exe is on PATH or use full path
$env:PATH = "$PWD\tools;$env:PATH"
kind create cluster --name ops-assistant-dev
kind get kubeconfig --name ops-assistant-dev | Out-File -FilePath agent\kind-kubeconfig -Encoding utf8
```

Verify the node is Ready:

```powershell
$env:KUBECONFIG = "$PWD\agent\kind-kubeconfig"
kubectl get nodes
```

### 3. Test workloads

```powershell
$env:KUBECONFIG = "$PWD\agent\kind-kubeconfig"
kubectl create deployment nginx --image=nginx:latest
kubectl create deployment crashy --image=nonexistent/doesnotexist:latest
kubectl get deployments,pods -A
```

Expect `nginx` pods Running and `crashy` in `ImagePullBackOff` / `ErrImagePull`.

### 4. MCP server sanity check

```powershell
$env:KUBECONFIG = "$PWD\agent\kind-kubeconfig"
# Starts stdio server; stop with Ctrl+C after it prints startup lines
npx -y mcp-server-kubernetes
```

You should see lines like `Starting Kubernetes MCP server v4.0.9, handling commands...`.

### 5. Environment file

Copy the example and configure Bedrock (do not commit `.env`):

```powershell
copy agent\.env.example agent\.env
# Edit agent\.env:
#   LLM_PROVIDER=bedrock
#   AWS_REGION=us-east-1
#   BEDROCK_MODEL=amazon.nova-2-lite-v1:0
#   KUBECONFIG=<absolute path to agent\kind-kubeconfig>
```

Use UTF-8 **without BOM** on Windows. AWS credentials come from the default chain (profile / env / instance role), not an API key.

Root `.gitignore` excludes `agent/.env`, kubeconfig files, `.kube/`, and `agent/.venv/`.

To use the AWS cluster instead of kind, set `KUBECONFIG` in `agent/.env` to the
absolute path of `.kube/aws-dev-config` (created from the control-plane admin.conf;
see the root README). Kind remains available by pointing `KUBECONFIG` at
`agent/kind-kubeconfig`.

## Unit tests

From repo root:

```powershell
agent\.venv\Scripts\python.exe agent\test_guardrails.py -v
agent\.venv\Scripts\python.exe -m pytest agent\test_agent_namespace.py agent\test_agent_loop.py agent\test_prometheus_query.py agent\test_observability_config.py -q
```

All **7** guardrail tests must pass.

## Scenario tests (end-to-end)

With `agent/.env` configured:

```powershell
agent\.venv\Scripts\python.exe agent\agent.py "list all pods in the cluster"

agent\.venv\Scripts\python.exe agent\agent.py "why is the crashy deployment failing?"
# Expect ImagePullBackOff / bad image diagnosis

agent\.venv\Scripts\python.exe agent\agent.py "scale nginx to 3 replicas"
$env:KUBECONFIG = "$PWD\agent\kind-kubeconfig"
kubectl get deployment nginx
# Expect 3/3 replicas

agent\.venv\Scripts\python.exe agent\agent.py "delete the crashy deployment"
# Expect guardrail refusal (not deleted)
kubectl get deployment crashy
# Expect crashy still present
```

## Architecture (Phase 1)

```
User prompt → agent.py (Bedrock Converse tool loop)
                 ↓ guardrails.py (allow/deny MCP tools)
                 ↓ mcp_client.py (stdio → npx mcp-server-kubernetes)
                 ↓ kubectl → kind cluster (ops-assistant-dev)
```

Allowed mutations in Phase 1 include `kubectl_scale`. Observability uses local
`prometheus_query` (predefined query types only). Blocked tools include
`kubectl_delete`, `cleanup_pods`, `kubectl_generic`, and other destructive MCP tools.

## Known limitations

- **Phase 1 only** — local development workflow; no production hardening.
- **kind cluster only** — no EKS/GKE/AKS; no cloud credentials or Terraform in this phase.
- **No containerized agent** — runs as a local Python process invoking `npx` for MCP.
- **Guardrails are application-level** — not a substitute for Kubernetes RBAC or admission control.
- **Windows note** — MCP client uses `npx.cmd`; clear `%LOCALAPPDATA%\npm-cache\_npx` if npx package cache is corrupted.

## Cleanup

```powershell
$env:PATH = "$PWD\tools;$env:PATH"
kind delete cluster --name ops-assistant-dev
Remove-Item agent\kind-kubeconfig -ErrorAction SilentlyContinue
```
