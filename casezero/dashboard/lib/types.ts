export type CaseStatus =
  | "RECEIVED"
  | "CLASSIFIED"
  | "VERIFIED"
  | "REVIEW_PENDING"
  | "FINANCIALLY_RESOLVED"
  | "COMMUNICATED"
  | "CLOSED"
  | "QUARANTINED";

export type CaseRecord = {
  id: string;
  case_ref: string;
  status: CaseStatus;
  category?: string | null;
  urgency?: "High" | "Medium" | "Low" | null;
  confidence?: number | null;
  amount_rm?: number | null;
  verification_result?: "PASS" | "FAIL" | "MANUAL_REVIEW" | null;
  outcome?: string;
  account_no_masked?: string | null;
  sla_due?: string | null;
  sla_working_days?: number | null;
  summary?: string | null;
  channel?: string;
  created_at?: string;
  track_token?: string;
};

export type CaseEvent = {
  seq: number;
  event_type: string;
  actor: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  hash: string;
};

export type CaseDetail = {
  case: CaseRecord;
  events: CaseEvent[];
  journal: Array<Record<string, unknown>>;
  chain: { ok: boolean; first_bad_seq?: number | null; reason?: string | null };
  cost_rm: number;
};
