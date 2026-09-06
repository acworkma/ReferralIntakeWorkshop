import {
  Check,
  ChevronRight,
  FileCheck2,
  FileUp,
  Inbox,
  LoaderCircle,
  Moon,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { applyTheme, initialTheme, type Theme } from "./theme";
import type { Identity, Referral, Status } from "./types";

const statusLabel: Record<Status, string> = {
  queued: "Queued",
  processing: "Extracting",
  needs_review: "Needs review",
  approved: "Approved",
  rejected: "Rejected",
  failed: "Failed",
};

function formatField(value: string) {
  return value.replace(/([A-Z])/g, " $1").replace(/^./, (letter) => letter.toUpperCase());
}

// A thrown Error with an empty message would render as no banner at all,
// leaving a failed action looking like nothing happened.
function toMessage(reason: unknown, fallback: string) {
  const message = reason instanceof Error ? reason.message.trim() : "";
  return message || fallback;
}

function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const rows = await api.list();
      setReferrals(rows);
      setSelectedId((current) => current ?? rows[0]?.id ?? null);
      setError("");
    } catch (reason) {
      setError(toMessage(reason, "Unable to load the queue."));
    }
  }, []);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    Promise.all([api.me(), api.list()])
      .then(([user, rows]) => {
        setIdentity(user);
        setReferrals(rows);
        setSelectedId(rows[0]?.id ?? null);
      })
      .catch((reason: unknown) => setError(toMessage(reason, "Unable to load the workspace.")));
  }, []);

  useEffect(() => {
    if (!referrals.some((row) => row.status === "queued" || row.status === "processing")) return;
    const timer = window.setInterval(refresh, 1500);
    return () => window.clearInterval(timer);
  }, [referrals, refresh]);

  const selected = referrals.find((row) => row.id === selectedId) ?? null;

  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.upload(file);
      setReferrals((rows) => [created, ...rows]);
      setSelectedId(created.id);
    } catch (reason) {
      setError(toMessage(reason, "Upload failed."));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function decide(approved: boolean) {
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await api.review(selected.id, approved, note);
      setReferrals((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
      setNote("");
    } catch (reason) {
      setError(toMessage(reason, "Review could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(referral: Referral) {
    if (!window.confirm(`Delete "${referral.filename}"? This also frees the document for re-upload.`)) {
      return;
    }
    setBusy(true);
    try {
      await api.remove(referral.id);
      setReferrals((rows) => {
        const remaining = rows.filter((row) => row.id !== referral.id);
        setSelectedId((current) => (current === referral.id ? remaining[0]?.id ?? null : current));
        return remaining;
      });
      setError("");
    } catch (reason) {
      setError(toMessage(reason, "The referral could not be deleted."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="rail" aria-label="Primary navigation">
        <div className="mark" aria-label="Referral Intake Reference">
          RI
        </div>
        <nav>
          <a className="nav-item active" href="#queue" aria-current="page">
            <Inbox size={19} />
            <span>Queue</span>
          </a>
          <a className="nav-item" href="#review">
            <FileCheck2 size={19} />
            <span>Review</span>
          </a>
        </nav>
        <div className="rail-bottom">
          <label className="theme-label" htmlFor="theme">
            Theme
          </label>
          <select
            id="theme"
            value={theme}
            onChange={(event) => setTheme(event.target.value as Theme)}
            aria-label="Color theme"
          >
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
          {theme === "dark" ? <Moon size={17} /> : <Sun size={17} />}
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <h1>Referral control desk</h1>
            <p>Compare extraction evidence before a human decision.</p>
          </div>
          <div className="identity">
            <span className={identity?.localMock ? "identity-dot mock" : "identity-dot"} />
            <div>
              <strong>{identity?.displayName ?? "Connecting…"}</strong>
              <small>{identity?.localMock ? "LOCAL-ONLY MOCK IDENTITY" : "Microsoft Entra ID"}</small>
            </div>
          </div>
        </header>

        {error && (
          <div className="error" role="alert">
            <X size={18} />
            <span>{error}</span>
            <button onClick={() => setError("")} aria-label="Dismiss error">
              Dismiss
            </button>
          </div>
        )}

        <div className="workspace">
          <section className="queue-pane" id="queue">
            <div className="section-head">
              <div>
                <h2>Intake queue</h2>
                <p>{referrals.length} referrals</p>
              </div>
              <input
                ref={fileInput}
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                onChange={(event) => upload(event.target.files?.[0])}
                hidden
              />
              <button
                className="primary"
                disabled={busy}
                onClick={() => fileInput.current?.click()}
              >
                {busy ? <LoaderCircle className="spin" size={18} /> : <FileUp size={18} />}
                Add referral
              </button>
            </div>

            <div className="queue-list" role="list">
              {referrals.length === 0 ? (
                <div className="empty">
                  <FileUp size={32} />
                  <h3>Start with a referral document</h3>
                  <p>Upload a PDF, PNG, or JPEG. The API validates its type, size, and signature.</p>
                </div>
              ) : (
                referrals.map((referral) => (
                  <button
                    role="listitem"
                    key={referral.id}
                    className={`queue-row ${selectedId === referral.id ? "selected" : ""}`}
                    onClick={() => setSelectedId(referral.id)}
                  >
                    <span className={`status-mark ${referral.status}`} />
                    <span className="queue-copy">
                      <strong>{referral.filename}</strong>
                      <small>
                        {new Date(referral.createdAt).toLocaleString()} · {referral.id.slice(0, 8)}
                      </small>
                    </span>
                    <span className={`status ${referral.status}`}>{statusLabel[referral.status]}</span>
                    <ChevronRight size={17} />
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="review-pane" id="review" aria-live="polite">
            {!selected ? (
              <div className="empty tall">
                <FileCheck2 size={34} />
                <h2>No referral selected</h2>
                <p>Choose a queue item to inspect extraction evidence and record a decision.</p>
              </div>
            ) : (
              <>
                <div className="review-head">
                  <div>
                    <h2>{selected.filename}</h2>
                    <p>Submitted by {selected.submittedBy}</p>
                  </div>
                  <div className="review-head-actions">
                    <span className={`status ${selected.status}`}>{statusLabel[selected.status]}</span>
                    <button
                      className="secondary danger"
                      disabled={busy}
                      onClick={() => remove(selected)}
                      aria-label={`Delete ${selected.filename}`}
                    >
                      <Trash2 size={17} /> Delete
                    </button>
                  </div>
                </div>

                {(selected.status === "queued" || selected.status === "processing") && (
                  <div className="processing">
                    <div className="progress-copy">
                      <span>Dual-engine extraction</span>
                      <strong>{selected.progress}%</strong>
                    </div>
                    <div className="progress-track" aria-label={`${selected.progress}% processed`}>
                      <span style={{ width: `${selected.progress}%` }} />
                    </div>
                    <p>Document Intelligence and Content Understanding are processing in parallel.</p>
                  </div>
                )}

                {selected.comparison && (
                  <>
                    <div className="agreement">
                      <strong>{selected.comparison.agreementPercent}%</strong>
                      <span>field agreement</span>
                      <p>Disagreements stay highlighted until a reviewer makes a decision.</p>
                    </div>
                    <div className="comparison" role="table" aria-label="Extraction comparison">
                      <div className="comparison-header" role="row">
                        <span role="columnheader">Field</span>
                        <span role="columnheader">Document Intelligence</span>
                        <span role="columnheader">Content Understanding</span>
                      </div>
                      {selected.comparison.rows.map((row) => (
                        <div className={`comparison-row ${row.matches ? "" : "diff"}`} role="row" key={row.field}>
                          <strong role="cell">{formatField(row.field)}</strong>
                          <span role="cell">
                            {row.documentIntelligence}
                            <small>{Math.round(row.documentIntelligenceConfidence * 100)}% confidence</small>
                          </span>
                          <span role="cell">
                            {row.contentUnderstanding}
                            <small>{Math.round(row.contentUnderstandingConfidence * 100)}% confidence</small>
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {selected.status === "needs_review" && (
                  <div className="decision">
                    <label htmlFor="review-note">Review note</label>
                    <textarea
                      id="review-note"
                      maxLength={2000}
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      placeholder="Record what you verified or why this should return for correction."
                    />
                    <div className="decision-actions">
                      <button className="secondary danger" disabled={busy} onClick={() => decide(false)}>
                        <X size={18} /> Reject
                      </button>
                      <button className="primary" disabled={busy} onClick={() => decide(true)}>
                        <Check size={18} /> Approve extraction
                      </button>
                    </div>
                  </div>
                )}

                {selected.status === "failed" && (
                  <div className="final-state rejected">
                    <X size={20} />
                    <div>
                      <strong>Extraction failed</strong>
                      <span>
                        The document could not be processed after several attempts. Delete it to try
                        again, and check the API container logs for the underlying error.
                      </span>
                    </div>
                  </div>
                )}

                {(selected.status === "approved" || selected.status === "rejected") && (
                  <div className={`final-state ${selected.status}`}>
                    {selected.status === "approved" ? <Check size={20} /> : <X size={20} />}
                    <div>
                      <strong>{statusLabel[selected.status]} by {selected.reviewedBy}</strong>
                      <span>{selected.reviewNote || "No review note recorded."}</span>
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;


