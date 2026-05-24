import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";
import { CheckCheck, Pencil, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import { api } from "../api";
import "./Pending.css";

type FileEvent = Record<string, unknown>;
type CardAction = "correct" | "details" | null;

function confColor(conf: number | undefined): string {
  if (conf == null) return "var(--text-muted)";
  if (conf >= 0.75) return "var(--green)";
  if (conf >= 0.5) return "var(--yellow)";
  return "var(--red)";
}

function confLabel(conf: number | undefined): string {
  if (conf == null) return "—";
  return `${Math.round((conf as number) * 100)}%`;
}

interface Props {
  onDecided: () => void;
}

const Pending = forwardRef<{ refresh: () => void }, Props>(({ onDecided }, ref) => {
  const [events, setEvents] = useState<FileEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [subjects, setSubjects] = useState<string[]>([]);
  const [editSubject, setEditSubject] = useState<Record<number, string>>({});
  const [activePanel, setActivePanel] = useState<Record<number, CardAction>>({});

  const load = async () => {
    try {
      setError(false);
      const [evts, subs] = await Promise.all([api.getPending(), api.getSubjects()]);
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

  const decide = async (id: number, action: string, subject: string) => {
    await api.decide(id, action, subject);
    setEvents((prev) => prev.filter((e) => (e.id as number) !== id));
    onDecided();
  };

  const togglePanel = (id: number, panel: CardAction) => {
    setActivePanel((prev) => ({ ...prev, [id]: prev[id] === panel ? null : panel }));
  };

  const getSubject = (evt: FileEvent) =>
    editSubject[evt.id as number] ?? (evt.course_predicted as string) ?? "";

  if (loading) return <div className="page"><div className="empty-state">Loading…</div></div>;
  if (error) return (
    <div className="page">
      <div className="empty-state" style={{ flexDirection: "column", gap: 10 }}>
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
          <div className="page-title">Pending Review</div>
          <div className="page-sub">{events.length} file{events.length !== 1 ? "s" : ""} awaiting decision</div>
        </div>
        <button className="btn btn-ghost" style={{ marginLeft: "auto" }} onClick={load}>↻ Refresh</button>
      </div>

      <div className="pending-list">
        {events.length === 0 && (
          <div className="empty-state">No pending files. You're all caught up.</div>
        )}

        {events.map((evt) => {
          const id = evt.id as number;
          const conf = evt.school_confidence as number | undefined;
          const subConf = evt.course_confidence as number | undefined;
          const overall = subConf ? Math.min(conf ?? 0, subConf) : conf;
          const panel = activePanel[id] ?? null;
          const subject = getSubject(evt);

          return (
            <div key={id} className={`pending-card ${panel ? "has-panel" : ""}`}>

              {/* ── Top row ── */}
              <div className="card-top">
                <div className="card-conf" style={{ color: confColor(overall) }}>
                  {confLabel(overall)}
                </div>
                <div className="card-info">
                  <div className="card-filename">{evt.filename as string}</div>
                  <div className="card-subject">
                    → <strong>{evt.course_predicted as string || "Unknown"}</strong>
                  </div>
                </div>
              </div>

              {/* ── Action buttons ── */}
              <div className="card-actions">
                <button
                  className="btn btn-cyan"
                  onClick={() => decide(id, "accepted", subject)}
                >
                  <CheckCheck size={13} /> Accept
                </button>
                <button
                  className={`btn btn-violet ${panel === "correct" ? "active" : ""}`}
                  onClick={() => togglePanel(id, "correct")}
                >
                  <Pencil size={13} /> Correct
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => decide(id, "skipped", "")}
                >
                  <XCircle size={13} /> Not School
                </button>
                <button
                  className="btn btn-ghost details-btn"
                  onClick={() => togglePanel(id, "details")}
                >
                  {panel === "details" ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  Details
                </button>
              </div>

              {/* ── Correct panel ── */}
              {panel === "correct" && (
                <div className="card-panel">
                  <div className="panel-label">Choose subject to move to:</div>
                  <div className="subject-chips">
                    {subjects.map((s) => (
                      <button
                        key={s}
                        className={`subject-chip ${subject === s ? "active" : ""}`}
                        onClick={() => setEditSubject((p) => ({ ...p, [id]: s }))}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                  <div className="correct-footer">
                    <input
                      className="subject-input"
                      value={subject}
                      onChange={(e) => setEditSubject((p) => ({ ...p, [id]: e.target.value }))}
                      placeholder="Or type a new subject…"
                      onKeyDown={(e) => e.key === "Enter" && decide(id, "corrected", subject)}
                    />
                    <button
                      className="btn btn-accent"
                      onClick={() => decide(id, "corrected", subject)}
                      disabled={!subject.trim()}
                    >
                      <CheckCheck size={13} /> Move
                    </button>
                  </div>
                </div>
              )}

              {/* ── Details panel ── */}
              {panel === "details" && (
                <div className="card-panel">
                  <div className="detail-row">
                    <span className="detail-label">Path</span>
                    <span className="detail-val mono">{evt.original_path as string}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">School</span>
                    <span className="detail-val" style={{ color: confColor(conf) }}>{confLabel(conf)}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Subject</span>
                    <span className="detail-val" style={{ color: confColor(subConf) }}>{confLabel(subConf)}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Reason</span>
                    <span className="detail-val">{evt.prediction_reason as string}</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
});

Pending.displayName = "Pending";
export default Pending;
