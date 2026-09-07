import { describe, expect, it } from "vitest";
import type { Referral, Status } from "./types";
import {
  DECIDED,
  IN_FLIGHT,
  awaitingDecision,
  countFor,
  referralsFor,
} from "./views";

const ALL_STATUSES: Status[] = [
  "queued",
  "processing",
  "needs_review",
  "approved",
  "rejected",
  "failed",
];

function referral(status: Status): Referral {
  return { id: status, filename: `${status}.pdf`, status } as Referral;
}

describe("queue views", () => {
  it("puts every status in exactly one view", () => {
    // The original nav did not filter at all, so every referral appeared under
    // both links and the two views were indistinguishable.
    for (const status of ALL_STATUSES) {
      const inFlight = IN_FLIGHT.includes(status);
      const decided = DECIDED.includes(status);
      expect(inFlight || decided).toBe(true);
      expect(inFlight && decided).toBe(false);
    }
  });

  it("separates work in progress from closed-out referrals", () => {
    const rows = ALL_STATUSES.map(referral);
    expect(referralsFor("inflight", rows).map((row) => row.status)).toEqual([
      "queued",
      "processing",
      "needs_review",
    ]);
    expect(referralsFor("decided", rows).map((row) => row.status)).toEqual([
      "approved",
      "rejected",
      "failed",
    ]);
  });

  it("accounts for every referral across the two counts", () => {
    const rows = ALL_STATUSES.map(referral);
    expect(countFor("inflight", rows) + countFor("decided", rows)).toBe(rows.length);
  });

  it("counts only referrals that still need a human decision", () => {
    const rows = [referral("queued"), referral("needs_review"), referral("approved")];
    expect(awaitingDecision(rows)).toBe(1);
  });
});
