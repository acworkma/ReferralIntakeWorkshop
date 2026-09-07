import { describe, expect, it } from "vitest";
import { fieldLabel, stageIndex, STAGES, stageState, statusLabel } from "./pipeline";
import type { Status } from "./types";

const ALL_STATUSES: Status[] = [
  "queued",
  "processing",
  "needs_review",
  "approved",
  "rejected",
  "failed",
];

describe("pipeline", () => {
  it("maps every status onto a real stage", () => {
    for (const status of ALL_STATUSES) {
      const index = stageIndex(status);
      expect(index).toBeGreaterThanOrEqual(0);
      expect(STAGES[index]).toBeDefined();
    }
  });

  it("only reaches the closed stage once a document is out of the workflow", () => {
    const closed = STAGES.length - 1;
    expect(stageIndex("queued")).toBeLessThan(closed);
    expect(stageIndex("processing")).toBeLessThan(closed);
    expect(stageIndex("needs_review")).toBeLessThan(closed);
    expect(stageIndex("approved")).toBe(closed);
    expect(stageIndex("rejected")).toBe(closed);
    expect(stageIndex("failed")).toBe(closed);
  });

  it("never shows extraction as finished while it is still running", () => {
    // needs_review is the first stage where a human has anything to do.
    expect(stageIndex("processing")).toBeLessThan(stageIndex("needs_review"));
  });

  it("marks earlier steps done, the current one current, and later ones todo", () => {
    expect(stageState(0, 2)).toBe("done");
    expect(stageState(2, 2)).toBe("current");
    expect(stageState(3, 2)).toBe("todo");
  });

  it("labels every status", () => {
    for (const status of ALL_STATUSES) {
      expect(statusLabel(status)).toBeTruthy();
    }
  });

  it("turns schema field names into readable headings", () => {
    expect(fieldLabel("patientDateOfBirth")).toBe("Patient Date Of Birth");
    expect(fieldLabel("summary")).toBe("Summary");
  });
});
