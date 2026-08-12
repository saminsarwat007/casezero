/** Faithful copies of what the API actually returns for the boardroom.
 *
 * Every field here mirrors a real producer so a passing browser test cannot
 * certify a shape the server does not emit:
 *
 * * seats + baselines      → `api/agents/roster.py` (`SEATS`, `STAGE_ROLES`)
 * * stage labels           → `api/agents/roster.py` (`PIPELINE_STAGES`)
 * * `says` / `facts`       → `api/agents/handoff.py` (`_intake_line` … `_quarantine_line`)
 * * `value{}`              → `api/agents/handoff.py` (`build_value`)
 *
 * The spoken lines are written out verbatim rather than regenerated here on
 * purpose. A helper that rebuilt them from the payload would pass even if the
 * Python changed underneath; a literal string fails loudly, which is the point.
 */

export type Fact = { label: string; value: string };

export type Handoff = {
  stage: string;
  label: string;
  event_type: string;
  from: string;
  to: string;
  spoken: boolean;
  says: string;
  facts: Fact[];
  seq: number | null;
  hash: string | null;
  recorded_at: string | null;
  baseline_minutes: number;
  refused?: boolean;
};

export const STARTED_AT = "2026-08-04T08:00:00+00:00";
const HASH = "e414ce2b6706843f0b79e60607d6f30402109127ec86c5925277fc4fc4e92aa1";

/** `PIPELINE_STAGES` — plain-English labels, the stakeholder-facing wording. */
export const STAGE_LABELS: Record<string, string> = {
  intake: "Check for harmful content",
  classify: "Identify the complaint type",
  sla: "Set priority and deadline",
  verify: "Check against bank records",
  gate: "Decide: auto-resolve or human review",
  journal: "Move the money",
  communicate: "Send response to customer",
};

/** `STAGE_ROLES` — speaker, listener and the manual minutes each stage replaces.
 *  The minutes sum to exactly 90, which `test_roster.py` asserts server-side. */
const STAGE_ROLES: Record<string, [string, string, number]> = {
  intake: ["intake", "classifier", 15],
  classify: ["classifier", "kernel", 12],
  sla: ["kernel", "verifier", 8],
  verify: ["verifier", "kernel", 25],
  gate: ["kernel", "resolver", 10],
  journal: ["resolver", "communicator", 12],
  communicate: ["communicator", "customer", 8],
};

export const STAGE_IDS = Object.keys(STAGE_LABELS);

/** Chain sequence numbers are not one-per-stage: a run writes more events than it
 *  has observable stages (13 links for these 7), so the gaps here are deliberate.
 *  A contiguous 1..7 would let an off-by-one in the UI go unnoticed. */
const SEQ_BY_STAGE: Record<string, number> = {
  intake: 2,
  classify: 4,
  sla: 5,
  verify: 7,
  gate: 9,
  journal: 10,
  communicate: 13,
};

const EVENT_TYPES: Record<string, string> = {
  intake: "INTAKE_EXTRACTED",
  classify: "CLASSIFIED",
  sla: "URGENCY_ASSIGNED",
  verify: "VERIFICATION_COMPLETED",
  gate: "GATE_DECISION",
  journal: "JOURNAL_POSTED",
  communicate: "MESSAGE_SENT",
};

/** Exactly the sentences `handoff.py` assembles for a clean PASS-and-post run. */
const SPOKEN: Record<string, { says: string; facts: Fact[] }> = {
  intake: {
    says:
      "Clean. English complaint, claiming RM2,450.00, against TECHWORLD KL. " +
      "Account number encrypted before anything read it.",
    facts: [
      { label: "Account", value: "******6890" },
      { label: "Amount", value: "RM2,450.00" },
      { label: "Language", value: "English" },
      { label: "Attachments", value: "0" },
    ],
  },
  classify: {
    says: "This is an unauthorised transaction. I am 97% confident.",
    facts: [
      { label: "Category", value: "unauthorized_transaction" },
      { label: "Confidence", value: "97%" },
      { label: "Decided by", value: "language model" },
      {
        label: "Model's reasoning",
        value: "The sender denies authorising the card payment and states the card was never out of their possession.",
      },
    ],
  },
  sla: {
    says:
      "High priority. 5 working days under the BNM window, due 2026-08-11. " +
      "Unauthorised transactions are treated as high urgency.",
    facts: [
      { label: "Urgency", value: "High" },
      { label: "Working days", value: "5" },
      { label: "Deadline", value: "2026-08-11" },
      { label: "Rule", value: "BNM/RH/PD 028-103 s10.2" },
    ],
  },
  verify: {
    says:
      "Core banking confirms the claim. 3 checks against the ledger. " +
      "The transaction exists, the amount matches, and the card was not present.",
    facts: [
      { label: "Verification", value: "PASS" },
      { label: "Evidence checks", value: "3" },
      { label: "Bank tool calls", value: "2" },
      { label: "Model calls", value: "none — this seat compares records, it does not reason" },
    ],
  },
  gate: {
    says:
      "Approved for automatic resolution. PASS evidence with the amount inside the " +
      "auto-approval limit.",
    facts: [
      { label: "Ruling", value: "POST" },
      { label: "Verification input", value: "PASS" },
      { label: "Amount", value: "RM2,450.00" },
      { label: "Dual control", value: "not required" },
      { label: "Policy", value: "auto_approval_limit_rm" },
    ],
  },
  journal: {
    says: "RM2,450.00 reversal posted. Debit SUSPENSE:FRAUD, credit ******6890. Books balance.",
    facts: [
      { label: "Entry type", value: "REVERSAL" },
      { label: "Amount", value: "RM2,450.00" },
      { label: "Balanced", value: "yes" },
      { label: "Authorised by", value: "signed kernel ticket" },
    ],
  },
  communicate: {
    says:
      "Letter written and sent. Compliance lint passed with no repairs. " +
      "The regulatory wording is inserted by the kernel, not by me.",
    facts: [
      { label: "Outcome", value: "RESOLVED_IN_FULL" },
      { label: "Compliance checks", value: "4" },
      { label: "Letter length", value: "1180 characters" },
      { label: "Repaired by kernel", value: "no" },
    ],
  },
};

/** `_quarantine_line` — the only line intake gets when the firewall refuses. */
const QUARANTINE = {
  says:
    "Refused. The message carried an instruction aimed at the assistant rather than " +
    "a description of a dispute. I stopped before any model read this, so nothing " +
    "downstream ever saw it.",
  facts: [
    { label: "Outcome", value: "QUARANTINED" },
    { label: "Model calls", value: "zero — the block happens before the first one" },
  ],
};

/** `build_handoffs` for a run whose first `spokenCount` stages have landed.
 *  Stage N + 1 onwards carry `spoken: false` and an empty line — the boardroom
 *  must leave those seats silent rather than anticipate them. */
export function handoffsAt(spokenCount: number): Handoff[] {
  return STAGE_IDS.map((stage, index) => {
    const [from, to, baseline] = STAGE_ROLES[stage];
    const spoken = index < spokenCount;
    return {
      stage,
      label: STAGE_LABELS[stage],
      event_type: EVENT_TYPES[stage],
      from,
      to,
      spoken,
      says: spoken ? SPOKEN[stage].says : "",
      facts: spoken ? SPOKEN[stage].facts : [],
      seq: spoken ? SEQ_BY_STAGE[stage] : null,
      hash: spoken ? HASH : null,
      // One stage per second, so an elapsed figure per hop is checkable.
      recorded_at: spoken ? `2026-08-04T08:00:0${index + 1}+00:00` : null,
      baseline_minutes: baseline,
    };
  });
}

/** A quarantined run: intake refuses, and every stage after it stays silent. */
export function quarantinedHandoffs(): Handoff[] {
  const rows = handoffsAt(0);
  rows[0] = {
    ...rows[0],
    spoken: true,
    says: QUARANTINE.says,
    facts: QUARANTINE.facts,
    refused: true,
  };
  return rows;
}

/** `build_value` — savings are only claimed for stages that actually ran. */
export function valueFor(handoffs: Handoff[], elapsedSeconds: number) {
  const realised = handoffs
    .filter((row) => row.spoken)
    .reduce((sum, row) => sum + row.baseline_minutes, 0);
  return {
    baseline_minutes_total: 90,
    baseline_minutes_realised: realised,
    elapsed_seconds: Number(elapsedSeconds.toFixed(2)),
    minutes_saved: Number(Math.max(realised - elapsedSeconds / 60, 0).toFixed(1)),
    stages_spoken: handoffs.filter((row) => row.spoken).length,
    stages_total: handoffs.length,
  };
}

type SeatSpec = {
  id: string;
  name: string;
  kind: "agent" | "kernel";
  role: string;
  replaces: string;
  obligation: string;
  uses_model: boolean;
  provider: string | null;
  model: string | null;
  fallback_from: string | null;
};

/** `roster.SEATS` with both keys present — the honest multi-brain deployment. */
const SEATS: SeatSpec[] = [
  {
    id: "intake",
    name: "Intake",
    kind: "agent",
    role: "Reads the email and any PDF, extracts the claim, blocks injected instructions",
    replaces: "Complaints desk — opening mail, reading attachments, keying in details",
    obligation: "Identifiers encrypted and redacted before any model sees them",
    uses_model: true,
    provider: "gemini",
    model: "gemini-2.5-flash",
    fallback_from: null,
  },
  {
    id: "classifier",
    name: "Classifier",
    kind: "agent",
    role: "Decides which of the seven dispute categories this is, and how sure it is",
    replaces: "Complaints officer — categorising and writing up the case",
    obligation: "Category and confidence stamped on the case record",
    uses_model: true,
    provider: "gemini",
    model: "gemini-2.5-flash",
    fallback_from: null,
  },
  {
    id: "kernel",
    name: "Compliance Kernel",
    kind: "kernel",
    role: "Applies the rule pack: urgency, working-day deadline, and whether money may move",
    replaces: "Compliance officer and team lead — SLA diary and approval limits",
    obligation: "BNM Complaints Handling working-day window; auto-approval and dual-control limits",
    uses_model: false,
    provider: null,
    model: null,
    fallback_from: null,
  },
  {
    id: "verifier",
    name: "Verifier",
    kind: "agent",
    role: "Queries core banking and CRM over MCP and compares the claim to the ledger",
    replaces: "Investigator — logging into core banking and CRM to pull the transaction",
    obligation: "PASS, FAIL or MANUAL_REVIEW returned with the evidence behind it",
    uses_model: false,
    provider: null,
    model: null,
    fallback_from: null,
  },
  {
    id: "resolver",
    name: "Resolver",
    kind: "agent",
    role: "Posts the reversal or credit, but only against a signed kernel ticket",
    replaces: "Finance operations — raising the journal and chasing approval",
    obligation: "Balanced double entry; posting refused without a signed authorisation",
    uses_model: false,
    provider: null,
    model: null,
    fallback_from: null,
  },
  {
    id: "communicator",
    name: "Communicator",
    kind: "agent",
    role: "Drafts the customer letter; the kernel inserts and enforces the regulatory text",
    replaces: "Compliance and communications — drafting and reviewing the reply",
    obligation: "FMOS six-month referral right for eligible claims up to RM250,000",
    uses_model: true,
    provider: "groq",
    model: "llama-3.3-70b-versatile",
    fallback_from: null,
  },
  {
    id: "supervisor",
    name: "Supervisor",
    kind: "agent",
    role: "Watches the deadline on every open case and escalates before it is missed",
    replaces: "Team lead — manually reviewing the deadline report",
    obligation: "Deadline forecast ahead of breach, against the 11% miss rate today",
    uses_model: false,
    provider: null,
    model: null,
    fallback_from: null,
  },
];

function rosterOf(seats: SeatSpec[]) {
  return {
    seats,
    providers: [...new Set(seats.map((seat) => seat.provider).filter(Boolean))].sort(),
    baseline_minutes_total: 90,
    analyst_hourly_rm: 24.0,
    stage_baseline_minutes: Object.fromEntries(
      STAGE_IDS.map((stage) => [stage, STAGE_ROLES[stage][2]]),
    ),
  };
}

export const ROSTER = rosterOf(SEATS);

/** The same deployment with no Groq credential. `describe()` resolves the
 *  communicator to Gemini and sets `fallback_from`, so the UI is obliged to
 *  disclose one brain rather than advertise two. */
export const ROSTER_MISSING_GROQ = rosterOf(
  SEATS.map((seat) =>
    seat.id === "communicator"
      ? { ...seat, provider: "gemini", model: "gemini-2.5-flash", fallback_from: "groq" }
      : seat,
  ),
);

/** `GET /demo/personas` — the allow-listed synthetic customers plus the bounds
 *  the composer must render from rather than hardcode. */
export const PERSONAS = {
  enabled: true,
  personas: [
    { account_no: "7142556890", full_name: "Ahmad bin Ismail", email: "ahmad.ismail@example.my", segment: "retail", product: "savings" },
    { account_no: "7142001233", full_name: "Siti binti Rahman", email: "siti.rahman@example.my", segment: "vulnerable", product: "savings" },
  ],
  limits: {
    max_subject: 160,
    max_body: 4000,
    max_attachment_mb: 4,
    min_amount_rm: 1.0,
    max_amount_rm: 100000.0,
    attachment_types: ["application/pdf"],
    runs_per_hour: 2,
  },
};

/** `GET /demo/live/{token}/progress` — the feed the composer polls while the
 *  POST is still open. */
export function progressPayload({
  spokenCount,
  state = "RUNNING",
  quarantined = false,
  elapsedSeconds = 4.21,
}: {
  spokenCount: number;
  state?: "RUNNING" | "COMPLETED" | "FAILED";
  quarantined?: boolean;
  elapsedSeconds?: number;
}) {
  const handoffs = quarantined ? quarantinedHandoffs() : handoffsAt(spokenCount);
  return {
    state,
    token: "composed-token",
    case_ref: "MYB-2026-000502",
    started_at: STARTED_AT,
    stages: STAGE_IDS.map((id, index) => ({
      id,
      label: STAGE_LABELS[id],
      agent: PIPELINE_AGENTS[id],
      event_type: EVENT_TYPES[id],
      done: handoffs[index].spoken && !handoffs[index].refused,
      seq: handoffs[index].seq,
      actor: handoffs[index].spoken ? `agent:${id}` : null,
      recorded_at: handoffs[index].recorded_at,
    })),
    handoffs,
    value: valueFor(handoffs, elapsedSeconds),
    events_recorded: handoffs.filter((row) => row.spoken).length,
    quarantined,
  };
}

/** `PIPELINE_STAGES[3]` — the agent column shown on the checklist rail. */
const PIPELINE_AGENTS: Record<string, string> = {
  intake: "Intake agent",
  classify: "Classifier agent",
  sla: "Compliance kernel",
  verify: "Verifier agent (MCP)",
  gate: "Financial gate",
  journal: "Resolver agent",
  communicate: "Communicator agent",
};

/** `_event_stage` evidence — the plain-English line `main.py` writes per stage. */
const EVIDENCE: Record<string, string> = {
  intake:
    "The complaint was checked for harmful or injected content before any AI read it. " +
    "The customer's account number was hidden for safety.",
  classify: "The AI read the complaint and identified it as an unauthorised transaction. It is 97% sure about this.",
  sla: "Marked as High. The bank's policy says this must be resolved within 5 working days.",
  verify: "The bank's records were checked against the claim. The system confirmed the claim by examining 3 pieces of evidence.",
  gate: "The system approved this for automatic resolution.",
  journal: "RM 2,450.00 was moved. The debit and credit sides match, so the books are balanced.",
  communicate: "The response letter was checked for compliance and approved for sending. The customer has been notified.",
};

export const PROOF_TOKEN = "live-proof-token-12345678901234567890";

/** `GET /demo/live/{token}` — the persisted proof. Carries `handoffs`, `value`
 *  and `roster` so a reopened run redraws the identical boardroom offline, which
 *  is the Plan-B path for the demo. */
export function liveProof({
  quarantined = false,
  spokenCount = STAGE_IDS.length,
  roster = ROSTER,
  elapsedSeconds = 4.21,
}: {
  quarantined?: boolean;
  spokenCount?: number;
  roster?: typeof ROSTER;
  elapsedSeconds?: number;
} = {}) {
  const handoffs = quarantined ? quarantinedHandoffs() : handoffsAt(spokenCount);
  return {
    state: "COMPLETED" as const,
    token: PROOF_TOKEN,
    started_at: STARTED_AT,
    finished_at: "2026-08-04T08:00:04+00:00",
    proof: {
      execution: {
        token: PROOF_TOKEN,
        case_ref: "MYB-2026-000501",
        started_at: STARTED_AT,
        completed_at: "2026-08-04T08:00:04+00:00",
        duration_ms: Math.round(elapsedSeconds * 1000),
        runtime: "Vercel",
        assurance: "VERIFIED_LIVE",
        reused: false,
        source: "SYNTHETIC_INPUT",
        execution_mode: "LIVE_EXECUTION",
      },
      input: {
        fixture: "unauthorised_transaction_v1",
        authored_by: "FIXTURE" as "FIXTURE" | "STAKEHOLDER",
        sender: "ahmad.live@example.my",
        subject: "Unauthorised card transaction",
        account_no_masked: "******6890",
        amount_rm: 2450,
        merchant: "TECHWORLD KL",
        txn_ref: "CZLIVE-20260804-ABC12345",
        body_chars: undefined as number | undefined,
        body_sha256: undefined as string | undefined,
        attachment: null as string | null,
        attachment_read_by: null as "pdf_text" | "vision_ocr" | null,
      },
      result: {
        status: quarantined ? "QUARANTINED" : "COMMUNICATED",
        outcome: quarantined ? "REFUSED" : "RESOLVED_IN_FULL",
        verification_result: quarantined ? "—" : "PASS",
        category: quarantined ? "—" : "unauthorized_transaction",
        urgency: quarantined ? "—" : "High",
        confidence: quarantined ? 0 : 0.97,
        posted: !quarantined,
        degraded: [],
      },
      stages: STAGE_IDS.map((id, index) => ({
        id,
        label: STAGE_LABELS[id],
        status: handoffs[index].spoken && !handoffs[index].refused ? "PASS" : "MISSING",
        event_type: EVENT_TYPES[id],
        seq: handoffs[index].seq,
        actor: handoffs[index].spoken ? `agent:${id}` : null,
        recorded_at: handoffs[index].recorded_at,
        hash: handoffs[index].hash,
        evidence: EVIDENCE[id],
      })),
      handoffs,
      value: valueFor(handoffs, elapsedSeconds),
      roster: roster.seats,
      // Quarantine happens before the first model call, so the telemetry is empty
      // rather than small — that is the claim the boardroom makes visually.
      models: quarantined
        ? []
        : [
            { agent: "intake", provider: "gemini", model: "gemini-2.5-flash", tokens_in: 420, tokens_out: 80, latency_ms: 512, cost_rm: 0.001, metered: true },
            { agent: "classifier", provider: "gemini", model: "gemini-2.5-flash", tokens_in: 510, tokens_out: 94, latency_ms: 640, cost_rm: 0.001, metered: true },
            { agent: "communicator", provider: "groq", model: "llama-3.3-70b-versatile", tokens_in: 610, tokens_out: 240, latency_ms: 380, cost_rm: 0.001, metered: true },
          ],
      tools: quarantined
        ? []
        : [
            { server: "core-banking", tool: "verify_claim", transport: "stdio", latency_ms: 92, ok: true },
            { server: "core-banking", tool: "post_adjustment", transport: "stdio", latency_ms: 88, ok: true },
          ],
      journal: {
        balanced: !quarantined,
        entries: quarantined
          ? []
          : [
              {
                entry_type: "REVERSAL",
                debit_account: "SUSPENSE:FRAUD",
                credit_account_masked: "******6890",
                amount_rm: 2450,
                posted_by: "agent:resolver",
                posted_at: "2026-08-04T08:00:03+00:00",
              },
            ],
      },
      chain: {
        ok: true,
        links: quarantined ? 3 : 13,
        head_hash: HASH,
        first_bad_seq: null,
        reason: null,
      },
    },
  };
}
