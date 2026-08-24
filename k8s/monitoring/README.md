# Monitoring stack (metrics-server + kube-prometheus-stack)

## Components

- **metrics-server** — enables `kubectl top nodes` / `kubectl top pods -A`
- **kube-prometheus-stack** (Helm release `ops-monitor`) — Prometheus, Grafana, Alertmanager, kube-state-metrics, node-exporter

Namespace: `monitoring`

Grafana stays ClusterIP-only. Do **not** open it with an unrestricted Security Group or NodePort.

## metrics-server (kubeadm)

Upstream metrics-server fails TLS verification against kubeadm kubelet certs
(no IP SANs). The safest minimal workaround for this cluster is `--kubelet-insecure-tls`
(does not disable Kubernetes API authn/RBAC).

```powershell
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json --patch-file k8s/monitoring/metrics-server-json-patch.json
```

Verify:

```powershell
kubectl top nodes
kubectl top pods -A
```

NotReady / dead nodes show `<unknown>` for `kubectl top`; that is expected.

## Install Prometheus stack

```powershell
$helm = ".\tools\helm.exe"   # or helm on PATH
& $helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
& $helm repo update
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# After Terraform creates the SNS topic, set the ARN (or keep the account ARN in values.yaml).
& $helm upgrade --install ops-monitor prometheus-community/kube-prometheus-stack `
  -n monitoring -f k8s/monitoring/values.yaml
```

Do **not** use `--wait` if stale NotReady nodes exist: node-exporter DaemonSet pods
stay Pending there and Helm `--wait` never completes. Prometheus/Grafana/Alertmanager
can still be Ready on live nodes.

## Grafana (port-forward only)

```powershell
kubectl -n monitoring port-forward svc/ops-monitor-grafana 3000:80
```

Open http://127.0.0.1:3000 — user `admin`, password `ops-assistant-demo` (change after first login).

Useful dashboards: Kubernetes / Compute Resources / Node and Pod; kube-state-metrics
for restarts, pod phase, and deployment replicas.

## Prometheus service (in-cluster)

Helm truncates the Prometheus service name:

`http://ops-monitor-kube-prometheu-prometheus.monitoring.svc.cluster.local:9090`

Set `PROMETHEUS_URL` on the backend (see `k8s/configmap.yaml`). From a laptop:

```powershell
kubectl -n monitoring port-forward svc/ops-monitor-kube-prometheu-prometheus 9090:9090
# then PROMETHEUS_URL=http://127.0.0.1:9090
```

## Alert rules

Defined in `values.yaml` (`additionalPrometheusRulesMap`):

| Alert | Condition | For |
|-------|-----------|-----|
| NodeNotReady | node Ready condition false | 5m |
| PodCrashLooping | restart increase + CrashLoopBackOff | 5m |
| PodHighRestartRate | >5 restarts/hour on Running pods | 10m |
| DeploymentReplicasUnavailable | available < desired | 5m |
| HighNodeCPU | CPU > 90% | 10m |
| HighNodeMemory | memory > 90% | 10m |

Watchdog is routed to a null receiver (no SNS). Completed jobs and short rollouts
are excluded by `for:` windows / Running-phase matching.

## Alertmanager → SNS

Alertmanager uses the native SNS receiver with SigV4 (`us-east-1`).

Authentication: **worker EC2 instance role** via IMDSv2 (`http_tokens=required`, hop limit **2**
so pods can reach IMDS). No static AWS keys. IAM: `sns:Publish` only on
`arn:aws:sns:us-east-1:<account>:ops-assistant-dev-alerts`.

Tradeoff: any pod on the worker that can reach IMDS could theoretically call STS as
the instance role. Hop limit 2 is required for in-pod AWS SDK; it is not a public
credential leak. Do not log temporary credentials.

1. Apply Terraform SNS/IAM (additive; see root README).
2. Set `alert_email` in `infra/environments/dev/terraform.tfvars` or leave empty.
3. Confirm the SNS subscription email from AWS.
4. Helm-upgrade if the topic ARN in `values.yaml` needs updating.

Until the topic and IAM exist, SNS publishes fail; Alertmanager still evaluates rules.

## Resource profile (demo, 1 worker)

| Component | Requests | Limits |
|-----------|----------|--------|
| Prometheus | 100m / 512Mi | 500m / 1Gi |
| Grafana | 50m / 128Mi | 300m / 512Mi |
| Alertmanager | 20m / 64Mi | 200m / 256Mi |
| kube-state-metrics | 20m / 64Mi | 100m / 128Mi |
| node-exporter | 20m / 32Mi | 100m / 64Mi |
| prometheus-operator | 50m / 128Mi | 200m / 256Mi |

Prometheus retention **3 days**. No persistent volumes by default (data is lost on pod restart).

## Safe failure demo

See root README. Manifest: `k8s/demo/crashloop-demo.yaml`. Cleanup:

```powershell
kubectl delete -f k8s/demo/crashloop-demo.yaml
```
