import { FileUp, LoaderCircle, Moon, Sun, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { ReferralDetail } from "./components/ReferralDetail";
import { ReferralList } from "./components/ReferralList";
import { applyTheme, initialTheme, type Theme } from "./theme";
import type { Health, Identity, Referral } from "./types";
import { awaitingDecision, countFor, referralsFor, type View } from "./views";

// A thrown Error with an empty message would render as no banner at all,
// leaving a failed action looking like nothing happened.
function toMessage(reason: unknown, fallback: string) {
  const message = reason instanceof Error ? reason.message.trim() : "";
  return message || fallback;
}

function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [awaitingPickup, setAwaitingPickup] = useState<string[]>([]);
  const [view, setView] = useState<View>("inflight");
  const fileInput = useRef<HTMLInputElement>(null);

  const visible = useMemo(() => referralsFor(view, referrals), [view, referrals]);
  const inFlightCount = countFor("inflight", referrals);
  const decidedCount = countFor("decided", referrals);
  const needingDecision = awaitingDecision(referrals);
  const selected = visible.find((row) => row.id === selectedId) ?? null;

  const refresh = useCallback(async () => {
    try {
      const rows = await api.list();
      setReferrals(rows);
      // A delivery stops being "awaiting pickup" once the workflow has created
      // its referral, which is the moment the pipeline visibly did its job.
      setAwaitingPickup((pending) =>
        pending.filter((filename) => !rows.some((row) => row.filename === filename)),
      );
      setError("");
    } catch (reason) {
      setError(toMessage(reason, "Unable to load referrals."));
    }
  }, []);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    Promise.all([api.me(), api.health(), api.list()])
      .then(([user, status, rows]) => {
        setIdentity(user);
        setHealth(status);
        setReferrals(rows);
      })
      .catch((reason: unknown) => setError(toMessage(reason, "Unable to load the workspace.")));
  }, []);

  // Keep a referral selected whenever the current view has one to show, so the
  // detail pane is never blank for no reason.
  useEffect(() => {
    if (visible.length === 0) return;
    if (visible.some((row) => row.id === selectedId)) return;
    setSelectedId(visible[0].id);
  }, [visible, selectedId]);

  useEffect(() => {
    const working = referrals.some(
      (row) => row.status === "queued" || row.status === "processing",
    );
    if (!working && awaitingPickup.length === 0) return;
    const timer = window.setInterval(refresh, 1500);
    return () => window.clearInterval(timer);
  }, [referrals, awaitingPickup, refresh]);

  async function deliver(file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const delivery = await api.deliver(file);
      // No referral comes back, because none exists yet. The document is in the
      // landing zone and the workflow takes it from here.
      setAwaitingPickup((pending) => [...pending, delivery.filename]);
      setView("inflight");
      await refresh();
    } catch (reason) {
      setError(toMessage(reason, "The document could not be delivered."));
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
      // The decision moves it out of the in flight view, so follow it there
      // rather than silently dropping the reviewer back to an empty pane.
      setView("decided");
      setSelectedId(updated.id);
    } catch (reason) {
      setError(toMessage(reason, "The decision could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(referral: Referral) {
    if (
      !window.confirm(
        `Delete "${referral.filename}"? This also removes its document and frees it for redelivery.`,
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await api.remove(referral.id);
      setReferrals((rows) => rows.filter((row) => row.id !== referral.id));
      setSelectedId(null);
      setError("");
    } catch (reason) {
      setError(toMessage(reason, "The referral could not be deleted."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true">
            RI
          </span>
          <div>
            <h1>Referral intake</h1>
            <p>A window onto the workflow, not the thing that runs it.</p>
          </div>
        </div>
        <div className="topbar-right">
          {health && (
            <span
              className={`chip ${health.landingZone}`}
              title={
                health.landingZone === "azure"
                  ? "Documents are written to the storage account that raises the event."
                  : "Documents are written to the local landing zone used for development."
              }
            >
              landing zone: {health.landingZone}
            </span>
          )}
          <div className="identity">
            <span className={identity?.localMock ? "identity-dot mock" : "identity-dot"} />
            <div>
              <strong>{identity?.displayName ?? "Connecting…"}</strong>
              <small>{identity?.localMock ? "Local mock identity" : "Microsoft Entra ID"}</small>
            </div>
          </div>
          <label className="theme">
            {theme === "dark" ? <Moon size={16} /> : <Sun size={16} />}
            <span className="visually-hidden">Colour theme</span>
            <select value={theme} onChange={(event) => setTheme(event.target.value as Theme)}>
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
        </div>
      </header>

      <nav className="tabs" aria-label="Referral views">
        <button
          type="button"
          className={view === "inflight" ? "tab active" : "tab"}
          aria-current={view === "inflight" ? "page" : undefined}
          onClick={() => setView("inflight")}
        >
          In flight
          <em className="tab-count">{inFlightCount}</em>
        </button>
        <button
          type="button"
          className={view === "decided" ? "tab active" : "tab"}
          aria-current={view === "decided" ? "page" : undefined}
          onClick={() => setView("decided")}
        >
          Decided
          <em className="tab-count">{decidedCount}</em>
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          onChange={(event) => deliver(event.target.files?.[0])}
          hidden
        />
        <button
          type="button"
          className="primary deliver"
          disabled={busy}
          onClick={() => fileInput.current?.click()}
          title="Writes the document to the incoming container, exactly as an upstream system would"
        >
          {busy ? (
            <LoaderCircle className="spin" size={16} aria-hidden="true" />
          ) : (
            <FileUp size={16} aria-hidden="true" />
          )}
          Deliver document
        </button>
      </nav>

      {error && (
        <div className="banner error" role="alert">
          <X size={18} aria-hidden="true" />
          <span>{error}</span>
          <button type="button" className="ghost" onClick={() => setError("")}>
            Dismiss
          </button>
        </div>
      )}

      <div className="workspace">
        <section className="list-pane" aria-label="Referrals">
          <div className="pane-head">
            <h2>{view === "inflight" ? "In flight" : "Decided"}</h2>
            <p>
              {view === "inflight"
                ? needingDecision > 0
                  ? `${visible.length} in the workflow, ${needingDecision} waiting on you`
                  : `${visible.length} in the workflow`
                : `${visible.length} closed out`}
            </p>
          </div>
          <ReferralList
            view={view}
            referrals={visible}
            awaitingPickup={awaitingPickup}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </section>

        <section className="detail-pane" aria-live="polite" aria-label="Referral detail">
          {selected ? (
            <ReferralDetail
              referral={selected}
              busy={busy}
              note={note}
              onNoteChange={setNote}
              onDecide={decide}
              onDelete={() => remove(selected)}
            />
          ) : (
            <div className="empty tall">
              <h3>No referral selected</h3>
              <p>Choose one to see where its document is and what the engines read from it.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default App;
