# Ops Assistant — Project Specification

## Overview

**Ops Assistant** is a final-project system that lets a user ask natural-language questions about a Kubernetes cluster and receive accurate, policy-bound answers and actions. An LLM-powered Python agent connects to the cluster through the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) using [`mcp-server-kubernetes`](https://www.npmjs.com/package/mcp-server-kubernetes).

The agent can **inspect** cluster state (pods, deployments, events, logs) and perform **limited mutations** (e.g. scaling replicas). Destructive operations (deletes, cleanup, arbitrary kubectl) are blocked by an application-level guardrail layer before any MCP tool call reaches the cluster.

## Goals

1. **Safe agentic operations** — LLM tool use is filtered; destructive MCP tools are denied by default.
2. **Real cluster interaction** — Not mocked; the agent talks to a live Kubernetes API via MCP → kubectl.
3. **Reproducible local development** — Phase 1 uses a local [kind](https://kind.sigs.k8s.io/) cluster only.
4. **Incremental delivery** — Local agent first; cloud infrastructure, containers, and CI come in later phases.

## Non-goals (Phase 1)

- No AWS/cloud deployment or Terraform
- No containerized agent runtime
- No GitHub Actions / CI pipelines (`infra/`, `.github/workflows/` are later phases)
- No human-in-the-loop approval UI
- Guardrails are **not** a replacement for Kubernetes RBAC or admission controllers

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────────────┐     ┌──────────────┐
│ User prompt │ ──► │  agent.py    │ ──► │ guardrails.py           │ ──► │ MCP server   │
│ (CLI)       │     │ OpenAI loop  │     │ allow / deny tool calls │     │ (stdio/npx)  │
└─────────────┘     └──────────────┘     └─────────────────────────┘     └──────┬───────┘
                                                                                 │
                                                                                 ▼
                                                                        ┌──────────────┐
                                                                        │ kubectl      │
                                                                        │ kind cluster │
                                                                        └──────────────┘
```

### Components

| Component | Path | Responsibility |
|-----------|------|----------------|
| Agent | `agent/agent.py` | Loads env, runs OpenAI chat with tool calling, orchestrates MCP |
| MCP client | `agent/mcp_client.py` | Spawns `npx mcp-server-kubernetes`, MCP session over stdio |
| Guardrails | `agent/guardrails.py` | `check_tool_call(name, args) → (allowed, reason)` |
| Tests | `agent/test_guardrails.py` | 7 unit tests for guardrail policy |
| Config | `agent/.env` | `OPENAI_API_KEY`, `KUBECONFIG` (gitignored) |
| Cluster config | `agent/kind-kubeconfig` | Project-local kubeconfig for kind (gitignored) |

### External dependencies

| Dependency | Role |
|------------|------|
| OpenAI API | LLM reasoning and tool selection |
| `mcp-server-kubernetes` | MCP tool surface over kubectl |
| kind | Local Kubernetes cluster (`ops-assistant-dev`) |
| Docker Desktop | Runs kind node containers |
| kubectl | Used by MCP server to reach the API |

## Guardrail policy (Phase 1)

Every MCP tool call proposed by the LLM passes through `guardrails.check_tool_call()` **before** execution.

### Allowed (examples)

- **Read:** `kubectl_get`, `kubectl_describe`, `kubectl_logs`, `explain_resource`, `list_api_resources`, `ping`
- **Controlled write:** `kubectl_scale` (and other non-destructive mutations on the Phase 1 allowlist)

### Blocked (examples)

- **Destructive:** `kubectl_delete`, `cleanup`, `cleanup_pods`, `node_management`
- **Bypass risk:** `kubectl_generic` (could run arbitrary delete commands)
- **Other destructive Helm ops:** `uninstall_helm_chart`, `helm_template_uninstall`

When blocked, the agent receives the refusal reason as the tool result and must explain it to the user without mutating the cluster.

## Test cluster setup

Cluster name: **`ops-assistant-dev`**

| Workload | Purpose |
|----------|---------|
| `nginx` deployment (`nginx:latest`) | Healthy baseline; used for list/scale scenarios |
| `crashy` deployment (`nonexistent/doesnotexist:latest`) | Intentionally broken; pod reaches `ImagePullBackOff` for diagnosis scenarios |

Kubeconfig is exported to `agent/kind-kubeconfig` (not merged into `~/.kube/config`).

## Acceptance criteria (Phase 1)

### Environment

- [ ] Docker, Node.js/npx, kubectl, kind, Python 3.11+ available
- [ ] kind cluster `ops-assistant-dev` running; node `Ready`
- [ ] `agent/.env` configured with `OPENAI_API_KEY` and absolute `KUBECONFIG` path
- [ ] `agent/.env` and `agent/kind-kubeconfig` listed in `.gitignore`

### Automated tests

- [ ] `python agent/test_guardrails.py` — all **7** tests pass

### Scenario tests

| # | Command | Expected outcome |
|---|---------|------------------|
| a | `python agent/agent.py "list all pods in the cluster"` | Lists pods across namespaces |
| b | `python agent/agent.py "why is the crashy deployment failing?"` | Diagnoses `ImagePullBackOff` / invalid image |
| c | `python agent/agent.py "scale nginx to 3 replicas"` | Deployment scales to 3; verified with kubectl |
| d | `python agent/agent.py "delete the crashy deployment"` | **Refused** by guardrails; deployment still exists |

## Configuration

### `agent/.env`

```env
OPENAI_API_KEY=<secret>
KUBECONFIG=<absolute path to agent/kind-kubeconfig>
OPENAI_MODEL=gpt-4o-mini   # optional
```

Secrets must never be committed. Use `agent/.env.example` as a template.

### MCP server

Started by the agent via:

```bash
KUBECONFIG=agent/kind-kubeconfig npx -y mcp-server-kubernetes
```

The MCP server reads `KUBECONFIG` from the environment passed to the subprocess.

## Repository layout

```
fursa-project/
├── docs/
│   ├── spec.md          # this file
│   └── plan.md          # phased delivery plan
├── agent/
│   ├── agent.py
│   ├── mcp_client.py
│   ├── guardrails.py
│   ├── test_guardrails.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── README.md
│   ├── .env             # gitignored
│   └── kind-kubeconfig  # gitignored
├── tools/               # optional local kind binary
├── .gitignore
└── infra/               # Phase 2+ (not in scope yet)
```

## Security notes

- Treat `OPENAI_API_KEY` and kubeconfig as secrets.
- Phase 1 guardrails reduce accidental destructive LLM actions but do not enforce cluster-level authorization.
- Later phases should add RBAC-scoped service accounts, network boundaries, and audit logging.

## References

- [MCP specification](https://modelcontextprotocol.io/)
- [mcp-server-kubernetes](https://github.com/Flux159/mcp-server-kubernetes)
- [kind quick start](https://kind.sigs.k8s.io/docs/user/quick-start/)
- Setup and reproduction steps: `agent/README.md`
