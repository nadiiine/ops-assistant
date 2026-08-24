import { useEffect, useState } from "react";
import ClusterHealth from "./ClusterHealth.jsx";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export default function App() {
  const [tab, setTab] = useState("chat");
  const [status, setStatus] = useState({ connected: false, ready_nodes: 0, total_nodes: 0 });
  const [obs, setObs] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pendingDiagnose, setPendingDiagnose] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/cluster/status`)
      .then((res) => {
        if (!res.ok) throw new Error(`status ${res.status}`);
        return res.json();
      })
      .then(setStatus)
      .catch((err) => setError(`Cluster status unavailable: ${err.message}`));

    fetch(`${API_BASE}/observability/summary`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setObs(data))
      .catch(() => {});
  }, []);

  async function sendMessage(text) {
    const trimmed = (text || "").trim();
    if (!trimmed || loading) return;
    setInput("");
    setError("");
    setMessages((prev) => [...prev, { role: "user", text: trimmed }]);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || `chat failed (${res.status})`);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: body.answer,
          tools: body.tools_used || [],
          blocked: body.blocked_tools || [],
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function send() {
    sendMessage(input);
  }

  function handleDiagnose(prompt) {
    setTab("chat");
    setPendingDiagnose(prompt);
  }

  useEffect(() => {
    if (tab !== "chat" || !pendingDiagnose) return;
    const prompt = pendingDiagnose;
    setPendingDiagnose(null);
    void (async () => {
      await sendMessage(prompt);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot handoff from Cluster Health
  }, [tab, pendingDiagnose]);

  const clusterLabel = status.connected
    ? `AWS Dev Cluster: Connected  |  Nodes: ${status.ready_nodes}/${status.total_nodes} Ready`
    : "AWS Dev Cluster: Disconnected";

  const obsLabel = obs
    ? `Health: ${String(obs.status).toUpperCase()}  |  Nodes ${obs.nodes_ready}/${obs.nodes_total}  |  Unhealthy pods: ${obs.unhealthy_pods}  |  Alerts: ${obs.recent_alerts}`
    : null;

  return (
    <div className={`page ${tab === "health" ? "page-wide" : ""}`}>
      <header>
        <h1>Kubernetes Ops Assistant</h1>
        <p className={status.connected ? "ok" : "bad"}>{clusterLabel}</p>
        {obsLabel && <p className={obs.status === "healthy" ? "ok" : "bad"}>{obsLabel}</p>}
        <nav className="tabs" aria-label="Main">
          <button
            type="button"
            className={tab === "chat" ? "tab active" : "tab"}
            onClick={() => setTab("chat")}
          >
            Chat
          </button>
          <button
            type="button"
            className={tab === "health" ? "tab active" : "tab"}
            onClick={() => setTab("health")}
          >
            Cluster Health
          </button>
        </nav>
      </header>

      {tab === "chat" ? (
        <>
          <main>
            {messages.length === 0 && (
              <p className="hint">Ask about nodes, pods, logs, scaling, or cluster health diagnosis.</p>
            )}
            {messages.map((msg, idx) => (
              <section key={idx} className={msg.role}>
                <strong>{msg.role === "user" ? "You" : "Assistant"}</strong>
                <pre>{msg.text}</pre>
                {msg.role === "assistant" && msg.tools?.length > 0 && (
                  <p className="tools">Tools used: {msg.tools.join(", ")}</p>
                )}
                {msg.role === "assistant" && msg.blocked?.length > 0 && (
                  <p className="blocked">Blocked: {msg.blocked.join(", ")}</p>
                )}
              </section>
            ))}
            {loading && <p className="hint">Thinking…</p>}
            {error && <p className="error">{error}</p>}
          </main>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask something..."
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()}>
              Send
            </button>
          </form>
        </>
      ) : (
        <main className="health-main">
          <ClusterHealth onDiagnose={handleDiagnose} />
        </main>
      )}
    </div>
  );
}
