import type { Status } from "./types";

/**
 * The pipeline as the architecture actually defines it. Each step is a real
 * place a document can be, and the container named here is the container the
 * document is physically in at that point. Nothing in this file is decorative:
 * if a step is shown as reached, the workflow reached it.
 */
export interface Stage {
  key: string;
  label: string;
  container: string;
  detail: string;
}

export const STAGES: Stage[] = [
  {
    key: "landed",
    label: "Landed",
    container: "incoming",
    detail: "The document is in the landing zone. Writing it raised the event.",
  },
  {
    key: "extracting",
    label: "Extracting",
    container: "processing",
    detail: "The function claimed it and is running both engines against it.",
  },
  {
    key: "review",
    label: "Awaiting review",
    container: "processing",
    detail: "Extraction is done. A human decision is the only thing left.",
  },
  {
    key: "closed",
    label: "Closed",
    container: "archive / failed",
    detail: "The decision moved the document to its final container.",
  },
];

const STAGE_BY_STATUS: Record<Status, number> = {
  queued: 1,
  processing: 1,
  needs_review: 2,
  approved: 3,
  rejected: 3,
  failed: 3,
};

/** Index into STAGES for a referral's current status. */
export function stageIndex(status: Status): number {
  return STAGE_BY_STATUS[status];
}

/**
 * A document that has been delivered but has no referral row yet is still in
 * `incoming`, unclaimed. It is the most instructive state in the whole app,
 * because it is the window where the pipeline is running without the app.
 */
export const AWAITING_PICKUP_STAGE = 0;

export type StageState = "done" | "current" | "todo";

export function stageState(index: number, current: number): StageState {
  if (index < current) return "done";
  if (index === current) return "current";
  return "todo";
}

const STATUS_LABEL: Record<Status, string> = {
  queued: "Claimed",
  processing: "Extracting",
  needs_review: "Needs review",
  approved: "Approved",
  rejected: "Returned",
  failed: "Failed",
};

export function statusLabel(status: Status): string {
  return STATUS_LABEL[status];
}

/** Turns a schema field name such as `patientDateOfBirth` into a heading. */
export function fieldLabel(value: string): string {
  return value.replace(/([A-Z])/g, " $1").replace(/^./, (letter) => letter.toUpperCase());
}
