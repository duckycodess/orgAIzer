import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";
import { api } from "../api";
import "./History.css";

type FileEvent = Record<string, unknown>;

const ACTION_LABELS: Record<string, string> = {
  auto: "Auto-moved",
  accepted: "Accepted",
  corrected: "Corrected",
  corrected_not_school: "Corrected (was Not School)",
  skipped: "Skipped",
  undone: "Undone",
  not_school: "Not school",
  pending: "Pending",
  error: "Error",
};

function confColor(conf: number | undefined | null): string {
  if (conf == null) return "var(--text-muted)";
  if (conf >= 0.75) return "var(--green)";
  if (conf >= 0.5) return "var(--yellow)";
  return "var(--red)";
}

const History = forwardRef<{ refresh: () => void }>((_, ref) => {
  const [events, setEvents] = useState<FileEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState("");
  const [subjects, setSubjects] = useState<string[]>([]);
  const [markingId, setMarkingId] = useState<number | null>(null);
  const [markSubject, setMarkSubject] = useState("");

  const load = async () => {
    try {
      setError(false);
      const [evts, subs] = await Promise.all([api.getHistory(300), api.getSubjects()]);
      setEvents(evts);
      setSubjects(subs);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);
  useImperativeHandle(ref, () => ({ refresh: load }));

  const undo = async (id: number) => {
    await api.undo(id);
    load();
  };

  const doMarkAsSchool = async (id: number) => {
    if (!markSubject.trim()) return;
    await api.markAsSchool(id, markSubject.trim());
    setMarkingId(null);
    setMarkSubject("");
    load();
  };

  const filtered = filter
    ? events.filter((e) => {
        const q = filter.toLowerCase();
        return (
          (e.filename as string)?.toLowerCase().includes(q) ||
          (e.final_course as string)?.toLowerCase().includes(q) ||
          (e.course_predicted as string)?.toLowerCase().includes(q)
        );
      })
    : events;

  if (loading) return <div className="page"><div className="history-loading">Loading…</div></div>;
  if (error) return (
    <div className="page">
      <div className="history-loading" style={{ flexDirection: "column", gap: 10 }}>
        <span style={{ color: "var(--red)" }}>Cannot reach API server</span>
        <span style={{ fontSize: 12 }}>Run: <code style={{ color: "var(--violet-text)" }}>python main_api.py</code></span>
        <button className="btn btn-ghost" onClick={load}>Retry</button>
      </div>
    </div>
  );

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">File History</div>
          <div className="page-sub">{filtered.length} events</div>
        </div>
        <input
          className="search-input"
          placeholder="Filter by filename, subject…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button className="btn btn-ghost" onClick={load}>↻ Refresh</button>
      </div>

      <div className="history-table-wrap">
        <table className="history-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Filename</th>
              <th>Subject</th>
              <th>Confidence</th>
              <th>Action</th>
              <th style={{ width: 160 }}></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((evt) => {
              const id = evt.id as number;
              const ts = (evt.timestamp as string) ?? "";
              const displayTs = ts.includes("T")
                ? ts.replace("T", " ").slice(0, 19)
                : ts;
              const schoolConf = evt.school_confidence as number | undefined;
              const subConf = evt.course_confidence as number | undefined;
              const conf = subConf ? Math.min(schoolConf ?? 0, subConf) : schoolConf;
              const action =
                (evt.user_action as string) || (evt.stage as string) || "—";
              const subject =
                (evt.final_course as string) ||
                (evt.course_predicted as string) ||
                "—";
              const stage = evt.stage as string;
              const canUndo = stage === "moved" && action !== "undone";
              const isNotSchool =
                stage === "not_school" && !evt.user_action;

              return (
                <tr key={id}>
                  <td className="td-time">{displayTs}</td>
                  <td className="td-filename" title={evt.filename as string}>
                    {evt.filename as string}
                  </td>
                  <td>{subject}</td>
                  <td style={{ color: confColor(conf), fontWeight: 600 }}>
                    {conf != null ? `${Math.round(conf * 100)}%` : "—"}
                  </td>
                  <td>
                    <span className={`action-chip action-${action.replace(/_/g, "-")}`}>
                      {ACTION_LABELS[action] ?? action}
                    </span>
                  </td>
                  <td>
                    {canUndo && (
                      <button
                        className="btn btn-danger"
                        style={{ fontSize: 11, padding: "3px 8px" }}
                        onClick={() => undo(id)}
                      >
                        Undo
                      </button>
                    )}
                    {isNotSchool && markingId !== id && (
                      <button
                        className="btn btn-accent"
                        style={{ fontSize: 11, padding: "3px 8px" }}
                        onClick={() => { setMarkingId(id); setMarkSubject(""); }}
                      >
                        Mark as School
                      </button>
                    )}
                    {markingId === id && (
                      <div className="mark-inline">
                        <input
                          className="subject-input"
                          list={`msubs-${id}`}
                          value={markSubject}
                          onChange={(e) => setMarkSubject(e.target.value)}
                          placeholder="Subject…"
                          autoFocus
                        />
                        <datalist id={`msubs-${id}`}>
                          {subjects.map((s) => <option key={s} value={s} />)}
                        </datalist>
                        <button
                          className="btn btn-accent"
                          style={{ fontSize: 11, padding: "3px 8px" }}
                          onClick={() => doMarkAsSchool(id)}
                        >✓</button>
                        <button
                          className="btn btn-ghost"
                          style={{ fontSize: 11, padding: "3px 6px" }}
                          onClick={() => setMarkingId(null)}
                        >✕</button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="td-empty">No events found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
});

History.displayName = "History";
export default History;
