import { LoaderCircle } from "lucide-react";
import { statusLabel } from "../pipeline";
import type { Referral } from "../types";
import type { View } from "../views";

interface Props {
  view: View;
  referrals: Referral[];
  awaitingPickup: string[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function ReferralList({ view, referrals, awaitingPickup, selectedId, onSelect }: Props) {
  const empty = referrals.length === 0 && awaitingPickup.length === 0;
  if (empty) {
    return (
      <div className="empty">
        {view === "inflight" ? (
          <>
            <h3>Nothing is in the workflow</h3>
            <p>
              Deliver a PDF, PNG, or JPEG to the landing zone, or drop one straight into the
              storage account with azcopy. Either way the same workflow picks it up.
            </p>
          </>
        ) : (
          <>
            <h3>Nothing has been decided yet</h3>
            <p>
              Approved, returned, and failed referrals collect here once a reviewer has acted on
              them.
            </p>
          </>
        )}
      </div>
    );
  }

  return (
    <ul className="referral-list">
      {view === "inflight" &&
        awaitingPickup.map((filename) => (
          <li key={`pending-${filename}`} className="referral-row pending">
            <LoaderCircle className="spin" size={16} aria-hidden="true" />
            <span className="referral-copy">
              <strong>{filename}</strong>
              <small>in incoming, not yet claimed</small>
            </span>
            <span className="status queued">Landed</span>
          </li>
        ))}
      {referrals.map((referral) => (
        <li key={referral.id}>
          <button
            type="button"
            className={`referral-row ${selectedId === referral.id ? "selected" : ""}`}
            aria-current={selectedId === referral.id ? "true" : undefined}
            onClick={() => onSelect(referral.id)}
          >
            <span className={`status-mark ${referral.status}`} aria-hidden="true" />
            <span className="referral-copy">
              <strong>{referral.filename}</strong>
              <small>
                {new Date(referral.createdAt).toLocaleString()}
                {referral.container ? ` · ${referral.container}` : ""}
              </small>
            </span>
            <span className={`status ${referral.status}`}>{statusLabel(referral.status)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
