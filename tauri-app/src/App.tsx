import { useEffect, useRef, useState } from "react";
import { Clock, History as HistoryIcon, Settings2, Hexagon, Circle } from "lucide-react";
import { api, AppEvent } from "./api";
import History from "./components/History";
import Pending from "./components/Pending";
import Settings from "./components/Settings";
import "./styles/app.css";

type Tab = "pending" | "history" | "settings";

export default function App() {
  const [tab, setTab] = useState<Tab>("pending");
  const [pendingCount, setPendingCount] = useState(0);
  const [watching, setWatching] = useState(false);
  const [toasts, setToasts] = useState<{ id: number; msg: string }[]>([]);
  const toastId = useRef(0);
  const pendingRef = useRef<{ refresh: () => void } | null>(null);
  const historyRef = useRef<{ refresh: () => void } | null>(null);

  const toast = (msg: string) => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, msg }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  };

  useEffect(() => {
    api.watcherStatus().then((s) => setWatching(s.running)).catch(() => {});
    api.getPending().then((p) => setPendingCount(p.length)).catch(() => {});
  }, []);

  useEffect(() => {
    const es = new EventSource("http://localhost:8000/api/events");
    es.onmessage = (e) => {
      const event: AppEvent = JSON.parse(e.data);
      if (event.type === "file_classified") {
        setPendingCount((c) => c + 1);
        toast(`New file: ${event.filename}`);
        pendingRef.current?.refresh();
      } else if (event.type === "file_auto_moved") {
        toast(`Auto-moved: ${event.filename} → ${event.subject}`);
        historyRef.current?.refresh();
      } else if (event.type === "file_status") {
        historyRef.current?.refresh();
      } else if (event.type === "retrain_done") {
        toast("Model retrained");
      }
    };
    return () => es.close();
  }, []);

  const toggleWatcher = async () => {
    if (watching) {
      await api.watcherStop();
      setWatching(false);
    } else {
      await api.watcherStart();
      setWatching(true);
    }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">
          <Hexagon size={18} color="var(--violet)" strokeWidth={1.5} />
          <span className="logo-text">OrgAIzer</span>
        </div>

        <nav className="nav">
          <button
            className={`nav-item ${tab === "pending" ? "active" : ""}`}
            onClick={() => setTab("pending")}
          >
            <Clock size={15} className="nav-icon" />
            <span>Pending</span>
            {pendingCount > 0 && <span className="badge">{pendingCount}</span>}
          </button>
          <button
            className={`nav-item ${tab === "history" ? "active" : ""}`}
            onClick={() => setTab("history")}
          >
            <HistoryIcon size={15} className="nav-icon" />
            <span>History</span>
          </button>
          <button
            className={`nav-item ${tab === "settings" ? "active" : ""}`}
            onClick={() => setTab("settings")}
          >
            <Settings2 size={15} className="nav-icon" />
            <span>Settings</span>
          </button>
        </nav>

        <div className="watcher-toggle">
          <Circle size={7} fill={watching ? "var(--cyan)" : "var(--text-dim)"} color="transparent" style={watching ? {filter:"drop-shadow(0 0 4px var(--cyan))"} : {}} />
          <span>{watching ? "Watching" : "Paused"}</span>
          <button className="watcher-btn" onClick={toggleWatcher}>
            {watching ? "Stop" : "Start"}
          </button>
        </div>
      </aside>

      <main className="content">
        {tab === "pending" && (
          <Pending
            ref={pendingRef}
            onDecided={() => setPendingCount((c) => Math.max(0, c - 1))}
          />
        )}
        {tab === "history" && <History ref={historyRef} />}
        {tab === "settings" && <Settings />}
      </main>

      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className="toast">{t.msg}</div>
        ))}
      </div>
    </div>
  );
}
