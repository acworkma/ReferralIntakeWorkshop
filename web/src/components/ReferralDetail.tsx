import { Check, RotateCcw, Trash2, TriangleAlert } from "lucide-react";
import { stageIndex, statusLabel } from "../pipeline";
import type { Referral } from "../types";
import { ComparisonTable } from "./ComparisonTable";
import { PipelineTrail } from "./PipelineTrail";

interface Props {
  referral: Referral;
  busy: boolean;
  note: string;
  onNoteChange: (note: string) => void;
  onDecide: (approved: boolean) => void;
  onDelete: () => void;
}

export function ReferralDetail({
  referral,
  busy,
  note,
  onNoteChange,
  onDecide,
  onDelete,
}: Props) {
  const working = referral.status === "queued" || referral.status === "processing";
  return (
    <>
      <header className="detail-head">
        <div>
          <h2>{referral.filename}</h2>
          <p>
            {referral.source === "web-simulator"
              ? `Delivered by ${referral.submittedBy} through the upstream simulator`
              : `Delivered by ${referral.submittedBy}`}
            {" · "}
            {referral.id.slice(0, 8)}
          </p>
        </div>
        <div className="detail-actions">
          <span className={`status ${referral.status}`}>{statusLabel(referral.status)}</span>
          <button
            type="button"
            className="ghost danger"
            disabled={busy}
            onClick={onDelete}
            aria-label={`Delete ${referral.filename}`}
          >
            <Trash2 size={16} aria-hidden="true" /> Delete
          </button>
        </div>
      </header>

      <PipelineTrail
        current={stageIndex(referral.status)}
        container={referral.container}
        failed={referral.status === "failed"}
      />

      {working && (
        <div className="progress">
          <div className="progress-track" aria-label={`${referral.progress}% processed`}>
            <span style={{ width: `${referral.progress}%` }} />
          </div>
          <small>{referral.progress}% complete</small>
        </div>
      )}

      {referral.status === "failed" && (
        <div className="banner failed" role="status">
          <TriangleAlert size={18} aria-hidden="true" />
          <div>
            <strong>The workflow could not process this document</strong>
            <span>
              {referral.failureReason ??
                "No reason was recorded. Check the function's invocation logs."}
            </span>
          </div>
        </div>
      )}

      {referral.comparison && (
        <ComparisonTable
          rows={referral.comparison.rows}
          agreementPercent={referral.comparison.agreementPercent}
        />
      )}

      {referral.status === "needs_review" && (
        <section className="panel decision">
          <label htmlFor="review-note">Review note</label>
          <textarea
            id="review-note"
            maxLength={2000}
            value={note}
            onChange={(event) => onNoteChange(event.target.value)}
            placeholder="Record what you verified, or why this needs correcting upstream."
          />
          <div className="decision-actions">
            <button type="button" className="ghost danger" disabled={busy} onClick={() => onDecide(false)}>
              <RotateCcw size={16} aria-hidden="true" /> Return for correction
            </button>
            <button type="button" className="primary" disabled={busy} onClick={() => onDecide(true)}>
              <Check size={16} aria-hidden="true" /> Approve
            </button>
          </div>
          <p className="panel-note">
            The decision moves the document to its final container and raises a business event.
            The Logic App decides what happens next.
          </p>
        </section>
      )}

      {(referral.status === "approved" || referral.status === "rejected") && (
        <div className={`banner ${referral.status}`} role="status">
          {referral.status === "approved" ? (
            <Check size={18} aria-hidden="true" />
          ) : (
            <RotateCcw size={18} aria-hidden="true" />
          )}
          <div>
            <strong>
              {referral.status === "approved" ? "Approved" : "Returned for correction"} by{" "}
              {referral.reviewedBy}
            </strong>
            <span>{referral.reviewNote || "No review note recorded."}</span>
          </div>
        </div>
      )}
    </>
  );
}
