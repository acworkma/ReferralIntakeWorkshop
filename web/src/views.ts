import type { Referral, Status } from "./types";

export type View = "inflight" | "decided";

// The two views split on one question: is this document still the workflow's
// business, or is it finished? Every status belongs to exactly one side, so a
// referral is never in both lists and never missing from both.
export const IN_FLIGHT: Status[] = ["queued", "processing", "needs_review"];
export const DECIDED: Status[] = ["approved", "rejected", "failed"];

export function statusesFor(view: View): Status[] {
  return view === "inflight" ? IN_FLIGHT : DECIDED;
}

export function referralsFor(view: View, referrals: Referral[]): Referral[] {
  const statuses = statusesFor(view);
  return referrals.filter((referral) => statuses.includes(referral.status));
}

export function countFor(view: View, referrals: Referral[]): number {
  return referralsFor(view, referrals).length;
}

/** Referrals a human still has to act on, which is the number that matters. */
export function awaitingDecision(referrals: Referral[]): number {
  return referrals.filter((referral) => referral.status === "needs_review").length;
}
