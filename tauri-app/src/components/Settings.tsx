import { useEffect, useState } from "react";
import { api, AppSettings } from "../api";
import "./Settings.css";

export default function Settings() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [warmup, setWarmup] = useState<{ labeled: number; required: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [scanPath, setScanPath] = useState("");
  const [seedFolder, setSeedFolder] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState(false);

  const load = async () => {
    try {
      setError(false);
      const [s, w] = await Promise.all([api.getSettings(), api.getWarmupStatus()]);
      setSettings(s);
      setWarmup(w);
    } catch {
      setError(true);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await api.updateSettings({
        downloads_path: settings.downloads_path,
        school_root: settings.school_root,
        watch_folder_override: settings.watch_folder_override,
        threshold_high: settings.threshold_high,
        threshold_medium: settings.threshold_medium,
        warmup_active: settings.warmup_active,
      });
      flash("Settings saved");
    } finally {
      setSaving(false);
    }
  };

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(""), 2500);
  };

  const scanSubjects = async () => {
    if (!scanPath.trim()) return;
    const { count } = await api.scanSubjects(scanPath.trim()) as { count: number };
    flash(`Found ${count} subject folders`);
    load();
  };

  const seedTraining = async () => {
    if (!seedFolder.trim()) return;
    const { count } = await api.seed(seedFolder.trim()) as { count: number };
    flash(`Seeded ${count} training samples`);
  };

  const retrain = async () => {
    await api.retrain();
    flash("Retrain triggered");
  };

  const clearTraining = async () => {
    await api.clearTraining();
    flash("Training samples cleared");
  };

  if (error) return (
    <div className="page">
      <div className="settings-loading" style={{ flexDirection: "column", gap: 12 }}>
        <span style={{ color: "var(--red)" }}>Cannot reach API server</span>
        <span style={{ fontSize: 12 }}>Run: <code style={{ color: "var(--violet-text)" }}>python main_api.py</code></span>
        <button className="btn btn-ghost" style={{ marginTop: 4 }} onClick={load}>Retry</button>
      </div>
    </div>
  );
  if (!settings) return <div className="page"><div className="settings-loading">Loading…</div></div>;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Settings</div>
          <div className="page-sub">Configure paths, thresholds, and training</div>
        </div>
        {msg && <span className="flash-msg">{msg}</span>}
        <button className="btn btn-accent" style={{ marginLeft: "auto" }} onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>

      <div className="settings-body">
        <section className="settings-section">
          <div className="section-title">Paths</div>
          <div className="field">
            <label>Downloads folder</label>
            <input
              className="text-input"
              value={settings.downloads_path}
              onChange={(e) => setSettings({ ...settings, downloads_path: e.target.value })}
              placeholder="/home/user/Downloads"
            />
          </div>
          <div className="field">
            <label>School root</label>
            <input
              className="text-input"
              value={settings.school_root}
              onChange={(e) => setSettings({ ...settings, school_root: e.target.value })}
              placeholder="/home/user/School"
            />
          </div>
          <div className="field">
            <label>Watch folder override</label>
            <input
              className="text-input"
              value={settings.watch_folder_override}
              onChange={(e) => setSettings({ ...settings, watch_folder_override: e.target.value })}
              placeholder="Leave blank to use downloads folder"
            />
            <span className="field-hint">Active: {settings.effective_watch_folder || "—"}</span>
          </div>
        </section>

        <section className="settings-section">
          <div className="section-title">Confidence thresholds</div>
          <div className="threshold-row">
            <div className="field">
              <label>Auto-move (high)</label>
              <div className="slider-row">
                <input
                  type="range" min={0.5} max={1} step={0.01}
                  value={settings.threshold_high}
                  onChange={(e) => setSettings({ ...settings, threshold_high: parseFloat(e.target.value) })}
                />
                <span className="threshold-val">{Math.round(settings.threshold_high * 100)}%</span>
              </div>
            </div>
            <div className="field">
              <label>Review (low)</label>
              <div className="slider-row">
                <input
                  type="range" min={0} max={0.7} step={0.01}
                  value={settings.threshold_medium}
                  onChange={(e) => setSettings({ ...settings, threshold_medium: parseFloat(e.target.value) })}
                />
                <span className="threshold-val">{Math.round(settings.threshold_medium * 100)}%</span>
              </div>
            </div>
          </div>
        </section>

        <section className="settings-section">
          <div className="section-title">Warmup mode</div>
          <div className="warmup-row">
            <label className="toggle">
              <input
                type="checkbox"
                checked={settings.warmup_active}
                onChange={(e) => setSettings({ ...settings, warmup_active: e.target.checked })}
              />
              <span className="toggle-track" />
              <span className="toggle-label">
                {settings.warmup_active ? "Active — all files sent to review" : "Off — auto-move enabled"}
              </span>
            </label>
            {warmup && (
              <div className="warmup-progress">
                <div className="warmup-bar-bg">
                  <div
                    className="warmup-bar-fill"
                    style={{ width: `${Math.min(100, (warmup.labeled / warmup.required) * 100)}%` }}
                  />
                </div>
                <span className="warmup-label">
                  {warmup.labeled}/{warmup.required} labeled
                </span>
              </div>
            )}
          </div>
        </section>

        <section className="settings-section">
          <div className="section-title">Subject folders</div>
          <div className="field">
            <label>Scan from path</label>
            <div className="input-action-row">
              <input
                className="text-input"
                value={scanPath}
                onChange={(e) => setScanPath(e.target.value)}
                placeholder="Path to school root to scan…"
              />
              <button className="btn btn-ghost" onClick={scanSubjects}>Scan</button>
            </div>
          </div>
        </section>

        <section className="settings-section">
          <div className="section-title">Training</div>
          <div className="field">
            <label>Seed from organized folder</label>
            <div className="input-action-row">
              <input
                className="text-input"
                value={seedFolder}
                onChange={(e) => setSeedFolder(e.target.value)}
                placeholder="Folder with Subject/file.pdf structure…"
              />
              <button className="btn btn-ghost" onClick={seedTraining}>Seed</button>
            </div>
          </div>
          <div className="action-row">
            <button className="btn btn-accent" onClick={retrain}>↺ Retrain now</button>
            <button className="btn btn-danger" onClick={clearTraining}>Clear training data</button>
          </div>
        </section>
      </div>
    </div>
  );
}
