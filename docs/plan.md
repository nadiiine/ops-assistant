# Ops Assistant — Delivery Plan

Phased plan for the final project. Each phase builds on the previous one. **Do not modify `infra/` or `.github/workflows/` until the phase that owns them.**

---

## Phase 1 — Local agent + kind cluster ✅

**Status:** Complete (local development)

**Objective:** Prove end-to-end flow: user prompt → OpenAI agent → guardrails → MCP → kind cluster.

### Deliverables

| Item | Location |
|------|----------|
| Python agent with OpenAI tool loop | `agent/agent.py` |
| MCP stdio client | `agent/mcp_client.py` |
| Guardrail allow/deny policy | `agent/guardrails.py` |
| Guardrail unit tests (7) | `agent/test_guardrails.py` |
| Dependencies | `agent/requirements.txt` |
| Env template | `agent/.env.example` |
| Setup & scenario docs | `agent/README.md` |
| Project spec | `docs/spec.md` |
| This plan | `docs/plan.md` |

### Setup checklist

1. Install prerequisites: Docker, Node/npx, kubectl, kind, Python 3.11+
2. Create `agent/.venv` and `pip install -r agent/requirements.txt`
3. Create kind cluster: `kind create cluster --name ops-assistant-dev`
4. Export kubeconfig: `kind get kubeconfig --name ops-assistant-dev > agent/kind-kubeconfig`
5. Deploy test workloads: `nginx` (healthy), `crashy` (bad image)
6. Configure `agent/.env` (`OPENAI_API_KEY`, absolute `KUBECONFIG`)
7. Sanity-check MCP: `KUBECONFIG=agent/kind-kubeconfig npx -y mcp-server-kubernetes`
8. Run unit tests and four scenario tests (see `docs/spec.md`)

### Exit criteria

- All 7 guardrail tests pass
- All 4 scenario tests pass with real command output
- Delete requests are refused; scale and read operations work

### Known limitations

- Local kind only; no cloud
- Agent runs as a host process, not in a container
- Guardrails are application-level only

---

## Phase 2 — Infrastructure as code

**Status:** Not started

**Objective:** Define cloud/cluster infrastructure in `infra/` (e.g. Terraform or equivalent) for a non-local deployment target.

### Planned work

- [ ] Choose target environment (e.g. EKS, GKE, or managed k8s)
- [ ] Add `infra/` modules: VPC/networking, cluster, IAM/RBAC
- [ ] Remote state and environment separation (dev/staging)
- [ ] Document apply/destroy workflow in `infra/README.md`
- [ ] **No AWS credentials or Terraform in Phase 1** — this phase introduces them

### Out of scope for Phase 2

- CI/CD pipelines (Phase 3)
- Containerized agent (Phase 4 or combined with Phase 3)

---

## Phase 3 — CI/CD and automation

**Status:** Not started

**Objective:** Automate test and deployment workflows via `.github/workflows/`.

### Planned work

- [ ] GitHub repository initialization and branch protection
- [ ] Workflow: lint/test on PR (`agent/test_guardrails.py`, optional integration job)
- [ ] Workflow: infra plan/apply (manual approval for apply)
- [ ] Secrets management in GitHub Actions (OpenAI key, cloud credentials)

---

## Phase 4 — Containerized agent (optional / TBD)

**Status:** Not started

**Objective:** Run the agent as a Kubernetes workload with a scoped ServiceAccount instead of a developer kubeconfig on the laptop.

### Planned work

- [ ] Dockerfile for `agent/`
- [ ] Deployment manifest with read/scoped-write RBAC
- [ ] In-cluster MCP sidecar or gateway pattern
- [ ] Stronger guardrails + audit logging

---

## Phase 5 — Production hardening (optional / TBD)

**Status:** Not started

### Planned work

- [ ] Human approval for mutations beyond scale
- [ ] Structured audit trail (who/what/when)
- [ ] Rate limits and cost controls on LLM usage
- [ ] Observability (traces/metrics for MCP tool calls)

---

## Current priorities

| Priority | Task |
|----------|------|
| **Now** | Phase 1 complete — maintain docs and reproduce scenarios locally |
| **Next** | Initialize GitHub repo; commit `agent/`, `docs/`, `.gitignore` (exclude secrets) |
| **Then** | Phase 2 — `infra/` skeleton and target cluster design |

---

## Reproduce Phase 1 from a clean clone

See **`agent/README.md`** for full commands. Short version:

```powershell
# Prerequisites + venv + kind cluster + workloads + .env
# Then:
agent\.venv\Scripts\python.exe agent\test_guardrails.py -v
agent\.venv\Scripts\python.exe agent\agent.py "list all pods in the cluster"
agent\.venv\Scripts\python.exe agent\agent.py "why is the crashy deployment failing?"
agent\.venv\Scripts\python.exe agent\agent.py "scale nginx to 3 replicas"
agent\.venv\Scripts\python.exe agent\agent.py "delete the crashy deployment"
```

---

## Document map

| File | Purpose |
|------|---------|
| `docs/spec.md` | What we're building, architecture, acceptance criteria |
| `docs/plan.md` | Phased delivery timeline (this file) |
| `agent/README.md` | Hands-on setup and scenario reproduction |
