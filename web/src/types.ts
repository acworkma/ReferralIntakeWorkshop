export type Status =
  | "queued"
  | "processing"
  | "needs_review"
  | "approved"
  | "rejected"
  | "failed";

export interface ComparisonRow {
  field: string;
  documentIntelligence: string;
  contentUnderstanding: string;
  documentIntelligenceConfidence: number;
  contentUnderstandingConfidence: number;
  matches: boolean;
  // Absent on referrals extracted before this field was introduced.
  comparable?: boolean;
}

export interface Referral {
  id: string;
  filename: string;
  status: Status;
  progress: number;
  submittedBy: string;
  source: string;
  /** The landing zone container the document is in right now. */
  container: string | null;
  failureReason: string | null;
  comparison: { rows: ComparisonRow[]; agreementPercent: number } | null;
  approved: boolean | null;
  reviewNote: string | null;
  reviewedBy: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * What comes back from dropping a document in the landing zone. Deliberately
 * not a referral: none exists yet. The blob write raises an event, and the
 * workflow is what creates the record.
 */
export interface Delivery {
  filename: string;
  container: string;
  deliveredAt: string;
  message: string;
}

export interface Identity {
  displayName: string;
  localMock: boolean;
}

/**
 * Tells the operator whether the app is writing to a real storage account or to
 * the local landing zone used for development. The two behave identically, so
 * without this there is no way to tell them apart from the browser.
 */
export interface Health {
  status: string;
  time: string;
  landingZone: "azure" | "local";
}
