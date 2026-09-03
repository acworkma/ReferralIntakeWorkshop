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
}

export interface Referral {
  id: string;
  filename: string;
  status: Status;
  progress: number;
  submittedBy: string;
  comparison: { rows: ComparisonRow[]; agreementPercent: number } | null;
  approved: boolean | null;
  reviewNote: string | null;
  reviewedBy: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Identity {
  displayName: string;
  localMock: boolean;
}
