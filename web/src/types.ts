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
