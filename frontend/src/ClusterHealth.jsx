import { useCallback, useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const NAMESPACES = [
  { value: "ops-assistant", label: "ops-assistant" },
  { value: "ops-assistant-demo", label: "ops-assistant-demo" },
  { value: "monitoring", label: "monitoring" },
  { value: "kube-system", label: "kube-system" },
  { value: "all", label: "All" },
];

function healthIcon(health) {
  switch (health) {
    case "healthy":
      return "●";
    case "degraded":
      return "▲";
    case "critical":
      return "■";
    default:
      return "○";
  }
}

function formatTime(iso) {
  if (!iso) return "--:--:--";
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return "--:--:--";
  }
}

function MetricBar({ label, percent }) {
  const value = typeof percent === "number" ? Math.max(0, Math.min(100, percent)) : null;
  return (
    <div className="metric-bar">
      <div className="metric-bar-label">
        <span>{label}</span>
        <span>{value == null ? "n/a" : `${value.toFixed(0)}%`}</span>
      </div>
      <div className="metric-bar-track" role="progressbar" aria-valuenow={value ?? 0} aria-valuemin={0} aria-valuemax={100}>
        <div
          className={`metric-bar-fill ${value != null && value >= 90 ? "hot" : ""}`}
          style={{ width: `${value ?? 0}%` }}
        />
      </div>
    </div>
  );
}

function StatusBadge({ health, text }) {
  return (
    <span className={`status-badge health-${health || "unknown"}`} title={text || health}>
      <span aria-hidden="true">{healthIcon(health)}</span> {text || String(health || "unknown").toUpperCase()}
    </span>
  );
}

function PodCard({ pod, selected, onSelect }) {
  return (
    <button
      type="button"
      className={`topo-card pod-card health-${pod.health} ${selected ? "selected" : ""}`}
      onClick={() => onSelect(pod)}
    >
      <div className="card-title-row">
        <strong className="card-name">{pod.name}</strong>
        <StatusBadge health={pod.health} text={pod.status} />
      </div>
      <div className="card-meta">
        Ready {pod.ready} · Restarts {pod.restarts} · Age {pod.age}
      </div>
      <div className="card-meta">
        Node: {pod.node || "—"} · CPU: {pod.cpu || "n/a"} · Mem: {pod.memory || "n/a"}
      </div>
      {pod.crash_loop && <div className="card-flag critical-flag">CrashLoopBackOff</div>}
      {pod.oom_killed && <div className="card-flag critical-flag">OOMKilled</div>}
    </button>
  );
}

function WorkloadChain({ workload, expanded, onToggle, selectedPod, onSelectPod }) {
  const dep = workload.deployment || workload.controller;
  const showPods = expanded || !workload.compact;

  return (
    <article className={`workload-chain health-${workload.health}`}>
      {workload.service && (
        <>
          <button
            type="button"
            className={`topo-card service-card health-${workload.health}`}
            onClick={() => onToggle(workload.id)}
          >
            <span className="card-kind">Service</span>
            <strong>{workload.service.name}</strong>
            <span className="card-meta">{workload.service.type}</span>
            <StatusBadge health={workload.health} />
          </button>
          <div className="topo-arrow" aria-hidden="true">
            ↓
          </div>
        </>
      )}

      {dep && (
        <>
          <button
            type="button"
            className={`topo-card deploy-card health-${dep.health || workload.health}`}
            onClick={() => onToggle(workload.id)}
          >
            <span className="card-kind">{dep.kind || "Deployment"}</span>
            <strong>{dep.name}</strong>
            <span className="card-meta">
              {dep.available ?? 0}/{dep.desired ?? 0} available
              {workload.compact ? ` · ${workload.pod_count} pods` : ""}
            </span>
            <StatusBadge health={dep.health || workload.health} />
          </button>
          <div className="topo-arrow" aria-hidden="true">
            ↓
          </div>
        </>
      )}

      {!workload.service && !dep && (
        <div className="topo-card">
          <span className="card-kind">{workload.kind}</span>
          <strong>{workload.name}</strong>
        </div>
      )}

      {showPods ? (
        <div className="pod-stack">
          {(workload.pods || []).map((pod) => (
            <PodCard
              key={`${pod.namespace}/${pod.name}`}
              pod={pod}
              selected={selectedPod?.name === pod.name && selectedPod?.namespace === pod.namespace}
              onSelect={onSelectPod}
            />
          ))}
          {workload.compact && workload.pod_count > (workload.pods || []).length && (
            <p className="card-meta">+{workload.pod_count - workload.pods.length} more pods</p>
          )}
        </div>
      ) : (
        <button type="button" className="topo-card pod-summary" onClick={() => onToggle(workload.id)}>
          <StatusBadge health={workload.health} />
          <span>
            {workload.pod_count} pod(s) — click to expand
          </span>
        </button>
      )}
    </article>
  );
}

function DetailPanel({ pod, events, onClose, onDiagnose }) {
  if (!pod) return null;
  const related = (events || []).filter(
    (e) => e.object_name === pod.name || (e.message || "").includes(pod.name)
  );

  return (
    <aside className="detail-panel" aria-label="Pod details">
      <div className="detail-header">
        <h3>{pod.name}</h3>
        <button type="button" className="ghost-btn" onClick={onClose} aria-label="Close details">
          Close
        </button>
      </div>
      <StatusBadge health={pod.health} text={pod.status} />
      <dl className="detail-grid">
        <div>
          <dt>Namespace</dt>
          <dd>{pod.namespace}</dd>
        </div>
        <div>
          <dt>Ready</dt>
          <dd>{pod.ready}</dd>
        </div>
        <div>
          <dt>Restarts</dt>
          <dd>{pod.restarts}</dd>
        </div>
        <div>
          <dt>Node</dt>
          <dd>{pod.node || "—"}</dd>
        </div>
        <div>
          <dt>Age</dt>
          <dd>{pod.age}</dd>
        </div>
        <div>
          <dt>CPU</dt>
          <dd>{pod.cpu || "n/a"}</dd>
        </div>
        <div>
          <dt>Memory</dt>
          <dd>{pod.memory || "n/a"}</dd>
        </div>
        <div>
          <dt>Last termination</dt>
          <dd>{pod.last_termination_reason || "—"}</dd>
        </div>
      </dl>

      <h4>Containers</h4>
      <ul className="container-list">
        {(pod.containers || []).map((c) => (
          <li key={c.name}>
            <StatusBadge
              health={c.ready ? "healthy" : c.reason === "CrashLoopBackOff" ? "critical" : "degraded"}
              text={c.reason || c.state}
            />{" "}
            {c.name} · restarts {c.restarts}
          </li>
        ))}
      </ul>

      <h4>Recent events</h4>
      {related.length === 0 ? (
        <p className="hint">No recent events for this pod in the current snapshot.</p>
      ) : (
        <ul className="event-list">
          {related.slice(0, 8).map((e, idx) => (
            <li key={idx}>
              <strong>{e.reason}</strong> ({e.type}) — {e.message}
            </li>
          ))}
        </ul>
      )}

      <button type="button" className="diagnose-btn" onClick={() => onDiagnose(pod)}>
        Ask AI to diagnose
      </button>
    </aside>
  );
}

export default function ClusterHealth({ onDiagnose }) {
  const [namespace, setNamespace] = useState("ops-assistant");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState({});
  const [selectedPod, setSelectedPod] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `${API_BASE}/observability/topology?namespace=${encodeURIComponent(namespace)}`
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `topology ${res.status}`);
      }
      const body = await res.json();
      setData(body);
      if (body.bedrock_used) {
        setError("Unexpected: topology used Bedrock");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [namespace]);

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    setSelectedPod(null);
    setExpanded({});
  }, [namespace]);

  function toggleWorkload(id) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  function diagnose(pod) {
    const prompt = [
      `Diagnose Kubernetes workload problems for pod ${pod.namespace}/${pod.name}.`,
      `Status: ${pod.status}. Ready: ${pod.ready}. Restarts: ${pod.restarts}.`,
      pod.node ? `Node: ${pod.node}.` : "",
      pod.last_termination_reason ? `Last termination: ${pod.last_termination_reason}.` : "",
      pod.crash_loop ? "CrashLoopBackOff detected." : "",
      pod.oom_killed ? "OOMKilled detected." : "",
      "Correlate pods, events, and metrics. Summarize likely cause and next action.",
    ]
      .filter(Boolean)
      .join(" ");
    onDiagnose?.(prompt);
  }

  const cluster = data?.cluster;
  const nodes = data?.nodes || [];
  const workloads = data?.workloads || [];

  return (
    <div className="cluster-health">
      <div className="dash-toolbar">
        <label>
          Namespace{" "}
          <select value={namespace} onChange={(e) => setNamespace(e.target.value)}>
            {NAMESPACES.map((ns) => (
              <option key={ns.value} value={ns.value}>
                {ns.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={load} disabled={loading}>
          Refresh
        </button>
        <span className="last-updated">
          Last updated: {formatTime(data?.updated_at)}
          {loading ? " · refreshing…" : ""}
        </span>
      </div>

      {error && <p className="error">{error}</p>}

      {cluster && (
        <section className="summary-strip" aria-label="Cluster summary">
          <div className={`summary-card health-${cluster.status}`}>
            <span className="summary-label">Cluster Health</span>
            <StatusBadge health={cluster.status} text={String(cluster.status).toUpperCase()} />
          </div>
          <div className="summary-card">
            <span className="summary-label">Nodes</span>
            <strong>
              {cluster.nodes_ready} / {cluster.nodes_total} Ready
            </strong>
          </div>
          <div className="summary-card">
            <span className="summary-label">Pods</span>
            <strong>
              {cluster.pods_running} / {cluster.pods_total} Running
            </strong>
          </div>
          <div className={`summary-card ${cluster.unhealthy_pods ? "health-degraded" : ""}`}>
            <span className="summary-label">Unhealthy</span>
            <strong>{cluster.unhealthy_pods}</strong>
          </div>
          <div className={`summary-card ${cluster.alerts ? "health-degraded" : ""}`}>
            <span className="summary-label">Alerts</span>
            <strong>{cluster.alerts}</strong>
          </div>
        </section>
      )}

      <section aria-label="Nodes">
        <h2 className="section-title">Nodes</h2>
        <div className="node-grid">
          {nodes.map((node) => (
            <div key={node.name} className={`topo-card node-card health-${node.health}`}>
              <div className="card-title-row">
                <span className="card-kind">{node.role === "control-plane" ? "Control Plane" : "Worker"}</span>
                <StatusBadge health={node.health} text={node.status} />
              </div>
              <strong className="card-name">{node.name}</strong>
              <MetricBar label="CPU" percent={node.cpu_percent} />
              <MetricBar label="Memory" percent={node.memory_percent} />
              <div className="card-meta">Pods: {node.pod_count}</div>
            </div>
          ))}
          {nodes.length === 0 && !loading && <p className="hint">No node data.</p>}
        </div>
      </section>

      <section aria-label="Workload topology" className="topology-section">
        <h2 className="section-title">
          Workload topology
          <span className="section-sub">Service → Deployment → Pods</span>
        </h2>
        <div className="workload-grid">
          {workloads.map((w) => (
            <WorkloadChain
              key={w.id}
              workload={w}
              expanded={!!expanded[w.id] || !w.compact}
              onToggle={toggleWorkload}
              selectedPod={selectedPod}
              onSelectPod={setSelectedPod}
            />
          ))}
          {workloads.length === 0 && !loading && (
            <p className="hint">No workloads in this namespace filter.</p>
          )}
        </div>
      </section>

      <DetailPanel
        pod={selectedPod}
        events={data?.events}
        onClose={() => setSelectedPod(null)}
        onDiagnose={diagnose}
      />
    </div>
  );
}
