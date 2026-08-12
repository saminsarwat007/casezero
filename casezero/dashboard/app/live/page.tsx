"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { apiFetch } from "@/lib/api";
import {
  Boardroom,
  type AgentsRoster,
  type Handoff,
  type RosterSeat,
  type RunValue,
} from "@/components/boardroom";
import { ValueLedger } from "@/components/value-ledger";

type Stage = {
  id: string;
  label: string;
  status: "PASS" | "MISSING" | "SKIPPED";
  event_type: string;
  seq?: number | null;
  actor?: string | null;
  recorded_at?: string | null;
  hash?: string | null;
  evidence: string;
};

type Persona = {
  account_no: string;
  full_name: string;
  email: string;
  segment: string;
  product: string;
};

/** The composer's bounds, read from the server so the form and the guard agree. */
type Limits = {
  max_subject: number;
  max_body: number;
  max_attachment_mb: number;
  min_amount_rm: number;
  max_amount_rm: number;
  attachment_types: string[];
  runs_per_hour: number;
};

type PersonaCatalogue = {
  enabled: boolean;
  personas: Persona[];
  limits: Limits;
};

/** Stage progress of a run that is still open, read from the hash chain itself. */
type ProgressStage = {
  id: string;
  label: string;
  agent: string;
  event_type: string;
  done: boolean;
  seq?: number | null;
  actor?: string | null;
  recorded_at?: string | null;
};

type RunProgress = {
  state: "RUNNING" | "COMPLETED" | "FAILED";
  token: string;
  case_ref?: string | null;
  started_at: string;
  stages: ProgressStage[];
  handoffs?: Handoff[];
  value?: RunValue;
  events_recorded: number;
  quarantined: boolean;
};

type ModelCall = {
  agent: string;
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  cost_rm: number;
  metered: boolean;
};

type ToolCall = {
  server: string;
  tool: string;
  transport: string;
  latency_ms?: number | null;
  ok: boolean;
};

type LiveProof = {
  execution: {
    token: string;
    case_ref: string;
    started_at: string;
    completed_at: string;
    duration_ms: number;
    runtime: string;
    assurance: "VERIFIED_LIVE" | "LIVE_DEGRADED";
    reused: boolean;
    source: "SYNTHETIC_INPUT";
    execution_mode: "LIVE_EXECUTION";
  };
  input: {
    fixture: string;
    sender: string;
    subject: string;
    account_no_masked: string;
    amount_rm: number;
    merchant: string;
    txn_ref: string;
    authored_by?: "STAKEHOLDER" | "FIXTURE";
    body_chars?: number;
    body_sha256?: string;
    attachment?: string | null;
    attachment_read_by?: "pdf_text" | "vision_ocr" | null;
  };
  result: {
    status: string;
    outcome: string;
    verification_result: string;
    category: string;
    urgency: string;
    confidence: number;
    posted: boolean;
    degraded: string[];
  };
  stages: Stage[];
  handoffs?: Handoff[];
  value?: RunValue;
  roster?: RosterSeat[];
  models: ModelCall[];
  tools: ToolCall[];
  journal: {
    balanced: boolean;
    entries: Array<{
      entry_type: string;
      debit_account: string;
      credit_account_masked: string;
      amount_rm: number;
      posted_by: string;
      posted_at?: string | null;
    }>;
  };
  chain: {
    ok: boolean;
    links: number;
    head_hash?: string | null;
    first_bad_seq?: number | null;
    reason?: string | null;
  };
};

type LiveResponse = {
  state: "RUNNING" | "COMPLETED" | "FAILED";
  token: string;
  started_at: string;
  finished_at?: string | null;
  proof?: LiveProof | null;
};

const currency = new Intl.NumberFormat("en-MY", {
  style: "currency",
  currency: "MYR",
  minimumFractionDigits: 2,
});

const wholeNumber = new Intl.NumberFormat("en-MY", { maximumFractionDigits: 0 });

function displayDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-MY", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "Asia/Kuala_Lumpur",
  }).format(new Date(value));
}

const POLL_MS = 700;

/** The composer mints its own run token so progress can be polled while the POST
 *  is still open. The server validates the shape as `[A-Za-z0-9_-]{32,96}`. */
function mintRunToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/** Seeded wording, deliberately without an account number: the guard scans the
 *  subject and body, and an allow-listed number belonging to a *different*
 *  persona is refused. Switching persona must never strand what was typed. */
const DEFAULT_SUBJECT = "Unauthorised card transaction";
const DEFAULT_BODY =
  "I did not authorise this card payment and my card has stayed with me the whole time. " +
  "Please investigate the charge and reverse it.";

function maskAccount(account: string) {
  return `${"*".repeat(Math.max(account.length - 4, 0))}${account.slice(-4)}`;
}

function stageElapsed(stage: ProgressStage, startedAt: string) {
  if (!stage.done || !stage.recorded_at) return "waiting";
  const ms = new Date(stage.recorded_at).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms)) return "recorded";
  return `+${(Math.max(ms, 0) / 1000).toFixed(1)}s`;
}

function LiveRunner() {
  const router = useRouter();
  const search = useSearchParams();
  const [response, setResponse] = useState<LiveResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingProof, setLoadingProof] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [elapsed, setElapsed] = useState(0);

  const [tab, setTab] = useState<"compose" | "sample">("compose");
  const [catalogue, setCatalogue] = useState<PersonaCatalogue | null>(null);
  const [catalogueError, setCatalogueError] = useState("");
  const [accountNo, setAccountNo] = useState("");
  const [fromName, setFromName] = useState("");
  const [subject, setSubject] = useState(DEFAULT_SUBJECT);
  const [body, setBody] = useState(DEFAULT_BODY);
  const [amount, setAmount] = useState("2450");
  const [merchant, setMerchant] = useState("TECHWORLD KL");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const stopPolling = useRef<(() => void) | null>(null);
  const composeTabRef = useRef<HTMLButtonElement>(null);
  const sampleTabRef = useRef<HTMLButtonElement>(null);
  const attachmentRef = useRef<HTMLInputElement>(null);

  // The boardroom must never advertise a brain that is not running, so the
  // seating plan is read from the live router — and, for a reopened proof, from
  // the roster frozen into that proof at execution time.
  const [roster, setRoster] = useState<AgentsRoster | null>(null);
  const [rosterError, setRosterError] = useState("");
  const reduceMotion = useReducedMotion() ?? false;
  const [view, setView] = useState<"board" | "list">("board");

  const proof = response?.proof ?? null;
  const verified = proof?.execution.assurance === "VERIFIED_LIVE";
  const runToken = search.get("run");
  const limits = catalogue?.limits ?? null;
  const persona = catalogue?.personas.find((item) => item.account_no === accountNo) ?? null;

  useEffect(() => {
    if (reduceMotion) setView("list");
  }, [reduceMotion]);

  useEffect(() => {
    let live = true;
    apiFetch<AgentsRoster>("/demo/agents")
      .then((data) => {
        if (live) setRoster(data);
      })
      .catch((reason) => {
        if (live) setRosterError(reason instanceof Error ? reason.message : "roster unavailable");
      });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!runToken) return;
    let current = true;
    setLoadingProof(true);
    setError("");
    apiFetch<LiveResponse>(`/demo/live/${encodeURIComponent(runToken)}`)
      .then((data) => {
        if (current) setResponse(data);
      })
      .catch((reason) => {
        if (current) setError(reason instanceof Error ? reason.message : "The proof could not be opened.");
      })
      .finally(() => {
        if (current) setLoadingProof(false);
      });
    return () => {
      current = false;
    };
  }, [runToken]);

  useEffect(() => {
    if (!busy) return;
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Date.now() - started), 250);
    return () => window.clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    let live = true;
    apiFetch<PersonaCatalogue>("/demo/personas")
      .then((data) => {
        if (!live) return;
        setCatalogue(data);
        const first = data.personas[0];
        if (first) {
          setAccountNo(first.account_no);
          setFromName(first.full_name);
        }
      })
      .catch((reason) => {
        if (live) setCatalogueError(reason instanceof Error ? reason.message : "The composer could not load.");
      });
    return () => {
      live = false;
    };
  }, []);

  // Stop polling if the visitor leaves mid-run.
  useEffect(() => () => stopPolling.current?.(), []);

  /** Poll stage progress while the compose POST is still open.
   *
   * A recursive timeout rather than an interval, because an async callback on a
   * 700 ms interval would overlap itself. Errors are swallowed on purpose: the
   * run row is only inserted once admission passes, so a valid run answers 404
   * for its first poll or two, and a refused run answers 404 forever.
   */
  const pollProgress = useCallback((token: string) => {
    let cancelled = false;
    let timer = 0;
    const tick = async () => {
      try {
        const data = await apiFetch<RunProgress>(`/demo/live/${encodeURIComponent(token)}/progress`);
        if (cancelled) return;
        if (Array.isArray(data.stages)) {
          setProgress(data);
          if (data.state !== "RUNNING") return;
        }
      } catch {
        if (cancelled) return;
      }
      timer = window.setTimeout(tick, POLL_MS);
    };
    timer = window.setTimeout(tick, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  async function runComposedCase(event: FormEvent) {
    event.preventDefault();
    if (!persona || !limits) return;
    if (attachment && attachment.size > limits.max_attachment_mb * 1024 * 1024) {
      attachmentRef.current?.focus();
      return;
    }
    const token = mintRunToken();
    setBusy(true);
    setElapsed(0);
    setError("");
    setNotice("");
    setResponse(null);
    setProgress(null);

    const form = new FormData();
    form.set("token", token);
    form.set("account_no", persona.account_no);
    form.set("from_name", fromName.trim() || persona.full_name);
    form.set("from_email", persona.email);
    form.set("subject", subject.trim());
    form.set("body", body.trim());
    form.set("amount_rm", amount);
    form.set("merchant", merchant.trim());
    if (attachment) form.set("attachment", attachment);

    stopPolling.current = pollProgress(token);
    try {
      const data = await apiFetch<LiveResponse>("/demo/compose", { method: "POST", body: form });
      setResponse(data);
      router.replace(`/live?run=${encodeURIComponent(data.token)}`, { scroll: false });
      setNotice(
        data.proof?.execution.reused
          ? "Your hourly limit reused a previously completed live proof; no result was fabricated."
          : "Your complaint ran on the deployed pipeline. Every receipt below came from your wording."
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The live execution stopped.");
    } finally {
      stopPolling.current?.();
      stopPolling.current = null;
      setBusy(false);
    }
  }

  async function runLiveCase() {
    setBusy(true);
    setElapsed(0);
    setError("");
    setNotice("");
    setResponse(null);
    // The fixture runner mints its own token server-side, so the browser cannot
    // watch this one land stage by stage. It gets the wait block, not a rail.
    setProgress(null);
    try {
      const data = await apiFetch<LiveResponse>("/demo/live", { method: "POST" });
      setResponse(data);
      router.replace(`/live?run=${encodeURIComponent(data.token)}`, { scroll: false });
      setNotice(
        data.proof?.execution.reused
          ? "Your hourly limit reused a previously completed live proof; no result was fabricated."
          : "Fresh execution complete. Every receipt below came from this run."
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The live execution stopped.");
    } finally {
      setBusy(false);
    }
  }

  async function loadLatest() {
    setLoadingProof(true);
    setError("");
    setProgress(null);
    try {
      const data = await apiFetch<LiveResponse>("/demo/live/latest");
      setResponse(data);
      router.replace(`/live?run=${encodeURIComponent(data.token)}`, { scroll: false });
      setNotice("Showing the latest completed live run. Its original timestamp is preserved below.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No completed run is available.");
    } finally {
      setLoadingProof(false);
    }
  }

  function downloadProof() {
    if (!proof) return;
    const blob = new Blob([JSON.stringify(proof, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${proof.execution.case_ref}-live-proof.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function copyProofLink() {
    await navigator.clipboard.writeText(window.location.href);
    setNotice("Proof link copied.");
  }

  const totalTokens = useMemo(
    () => proof?.models.reduce((sum, call) => sum + call.tokens_in + call.tokens_out, 0) ?? 0,
    [proof]
  );

  const runnerOff = catalogue !== null && !catalogue.enabled;
  const composerReady = Boolean(persona && limits) && !runnerOff;
  // Native form validation explains short fields at the field itself. Keep the
  // action available until a request actually starts so the browser can move
  // focus to the first invalid field instead of leaving a silent disabled CTA.
  const canCompose = composerReady && !busy && !loadingProof;
  const attachmentError = Boolean(
    attachment && limits && attachment.size > limits.max_attachment_mb * 1024 * 1024,
  );
  const budgetLine = limits
    ? `SYNTHETIC IDENTITIES ONLY · MAX ${limits.runs_per_hour} RUNS / DEVICE / HOUR · PDF ≤ ${limits.max_attachment_mb} MB`
    : "SYNTHETIC IDENTITIES ONLY · METERED RUNS PER DEVICE · NO REAL PII ACCEPTED";
  const stagesDone = progress?.stages.filter((stage) => stage.done).length ?? 0;

  const liveHandoffs = progress?.handoffs ?? [];
  const proofHandoffs = proof?.handoffs ?? [];
  const proofQuarantined = Boolean(
    proof && (proofHandoffs.some((handoff) => handoff.refused) || proof.result.status === "QUARANTINED")
  );
  const proofSeats = proof?.roster ?? roster?.seats ?? null;
  const attachmentMethod = proof?.input.attachment_read_by === "pdf_text"
    ? "Digital text read directly"
    : proof?.input.attachment_read_by === "vision_ocr"
      ? "Scanned pages transcribed with vision"
      : "No PDF attached";

  function selectComposerTab(next: "compose" | "sample", focus = false) {
    setTab(next);
    if (focus) {
      requestAnimationFrame(() => {
        (next === "compose" ? composeTabRef : sampleTabRef).current?.focus();
      });
    }
  }

  function moveComposerTab(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home"
      ? "compose"
      : event.key === "End"
        ? "sample"
        : tab === "compose"
          ? "sample"
          : "compose";
    selectComposerTab(next, true);
  }

  const viewToggle = (
    <div className="board-toggle" role="group" aria-label="How to watch this run">
      <button type="button" aria-pressed={view === "board"} onClick={() => setView("board")}>
        The boardroom
      </button>
      <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>
        The checklist
      </button>
    </div>
  );

  return (
    <main id="main-content" className="live-page">
      <header className="live-masthead">
        <Link href="/" className="brand" aria-label="CaseZero home">
          <span className="brand-word" translate="no">CaseZero</span>
          <span className="brand-mark" aria-hidden="true" />
        </Link>
        <nav className="live-nav" aria-label="Live demo navigation">
          <Link href="/">Overview</Link>
          <Link href="/login">Staff Sign In</Link>
        </nav>
      </header>

      <section className="truth-banner" aria-label="Data and execution boundary">
        <span><i aria-hidden="true" /> Fictional customer identity only</span>
        <strong>Your words + your PDF · Real API · Real models · Real Supabase writes</strong>
      </section>

      <section className="live-hero" aria-labelledby="live-title">
        <div className="live-intro">
          <p className="eyebrow mono">Axiom / Live Case 01</p>
          <h1 id="live-title">Watch one complaint become proof.</h1>
          <p>
            Write the complaint yourself, attach your own PDF, and watch each stage land as its
            evidence is written. No dashboard tour, no prefilled result — the pipeline underneath is
            the deployed one.
          </p>
          {proof ? (
            <div className="live-actions">
              <button className="btn ghost" type="button" onClick={downloadProof}>Download Proof JSON</button>
            </div>
          ) : null}
          <p className="live-budget mono">{budgetLine}</p>
        </div>

        <div className="live-input">
          <div className="compose-tabs" role="tablist" aria-label="Choose the complaint to run">
            <button ref={composeTabRef} id="compose-tab" type="button" role="tab" aria-controls="compose-panel" aria-selected={tab === "compose"} tabIndex={tab === "compose" ? 0 : -1} className={tab === "compose" ? "active" : ""} onKeyDown={moveComposerTab} onClick={() => selectComposerTab("compose")}>
              <strong>Write your own complaint</strong>
              <span>Your wording, your evidence</span>
            </button>
            <button ref={sampleTabRef} id="sample-tab" type="button" role="tab" aria-controls="sample-panel" aria-selected={tab === "sample"} tabIndex={tab === "sample" ? 0 : -1} className={tab === "sample" ? "active" : ""} onKeyDown={moveComposerTab} onClick={() => selectComposerTab("sample")}>
              <strong>Use the sample</strong>
              <span>One fixed sanitized email</span>
            </button>
          </div>

          {tab === "compose" ? (
            <form id="compose-panel" role="tabpanel" aria-labelledby="compose-tab" className="fixture-sheet compose-sheet" onSubmit={runComposedCase}>
              <div className="fixture-head">
                <span className="mono">RFC822 / YOU WRITE IT</span>
                <strong>SYNTHETIC</strong>
              </div>

              {runnerOff ? (
                <p className="compose-blocked" role="status">
                  The public live runner is switched off right now, so nothing can be executed from
                  here. Staff can still inject an RFC822 email after signing in.
                </p>
              ) : catalogueError ? (
                <div className="error-box" role="alert">
                  The fictional customers could not be loaded, so the composer cannot open. {catalogueError}
                </div>
              ) : !catalogue ? (
                <p className="compose-blocked" role="status">Loading the fictional customers…</p>
              ) : (
                <>
                  <div className="field">
                    <label htmlFor="compose-persona">File it as</label>
                    <select className="select" id="compose-persona" name="account_no" autoComplete="off" value={accountNo} onChange={(event) => {
                      const next = catalogue.personas.find((item) => item.account_no === event.target.value);
                      if (!next) return;
                      setAccountNo(next.account_no);
                      setFromName(next.full_name);
                    }}>
                      {catalogue.personas.map((item) => (
                        <option key={item.account_no} value={item.account_no}>
                          {item.full_name} · {maskAccount(item.account_no)} · {item.product.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                    <p className="field-help">
                      This choice supplies only a safe fictional identity and matching ledger account.
                      Your complaint, amount, merchant and PDF are not prefilled; they become the fresh case.
                    </p>
                  </div>

                  <div className="compose-row">
                    <div className="field">
                      <label htmlFor="compose-from">Sender name</label>
                      <input className="input" id="compose-from" name="from_name" value={fromName} maxLength={80} onChange={(event) => setFromName(event.target.value)} autoComplete="off" />
                    </div>
                    <div className="field">
                      <label htmlFor="compose-amount">Disputed amount (RM)</label>
                      <input
                        className="input mono" id="compose-amount" name="amount_rm" type="number" inputMode="decimal" autoComplete="off"
                        min={limits?.min_amount_rm} max={limits?.max_amount_rm} step="0.01"
                        value={amount} onChange={(event) => setAmount(event.target.value)} required
                      />
                    </div>
                  </div>

                  <div className="field">
                    <label htmlFor="compose-subject">Subject</label>
                    <input className="input" id="compose-subject" name="subject" value={subject} minLength={4} maxLength={limits?.max_subject} onChange={(event) => setSubject(event.target.value)} autoComplete="off" required />
                    <p className="field-help mono">{subject.trim().length} / {limits?.max_subject ?? "—"} · MINIMUM 4</p>
                  </div>

                  <div className="field">
                    <label htmlFor="compose-body">What happened?</label>
                    <textarea className="textarea" id="compose-body" name="body" value={body} minLength={20} maxLength={limits?.max_body} onChange={(event) => setBody(event.target.value)} autoComplete="off" required />
                    <p className="field-help mono">{body.trim().length} / {limits?.max_body ?? "—"} · MINIMUM 20</p>
                    <p className="field-help">
                      Do not paste a real account number or NRIC. The runner refuses them outright
                      rather than quietly deleting them, so nothing teaches you that real data is
                      accepted here.
                    </p>
                  </div>

                  <div className="compose-row">
                    <div className="field">
                      <label htmlFor="compose-merchant">Merchant</label>
                      <input className="input" id="compose-merchant" name="merchant" value={merchant} maxLength={80} onChange={(event) => setMerchant(event.target.value)} autoComplete="off" />
                    </div>
                    <div className="field">
                      <label htmlFor="compose-file">Evidence PDF (optional)</label>
                      <input
                        ref={attachmentRef}
                        className="input compose-file" id="compose-file" name="attachment" type="file"
                        accept={limits?.attachment_types.join(",") ?? "application/pdf"}
                        aria-describedby={attachmentError ? "compose-file-error" : undefined}
                        aria-invalid={attachmentError}
                        onChange={(event) => setAttachment(event.target.files?.[0] ?? null)}
                      />
                      {attachmentError ? (
                        <p className="field-error" id="compose-file-error" role="alert">
                          This PDF is larger than {limits?.max_attachment_mb} MB. Choose a smaller file.
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <p className="field-help">
                    A digital PDF is read as text; a scan is transcribed by the vision model. Either
                    way the transcription is screened again before any reasoning step, because a
                    document can carry an instruction as easily as an email can.
                  </p>

                  <dl className="compose-bound">
                    <div><dt>From</dt><dd>{fromName.trim() || persona?.full_name} &lt;{persona?.email}&gt;</dd></div>
                    <div><dt>Account</dt><dd className="mono">{persona ? maskAccount(persona.account_no) : "—"}</dd></div>
                  </dl>

                  <button className="btn primary live-primary" type="submit" disabled={!canCompose}>
                    {busy ? "Executing Live…" : "Run My Complaint Live"}
                  </button>
                </>
              )}
            </form>
          ) : (
            <article id="sample-panel" role="tabpanel" aria-labelledby="sample-tab" className="fixture-sheet">
              <div className="fixture-head">
                <span className="mono">RFC822 / ALLOW-LISTED</span>
                <strong>SYNTHETIC</strong>
              </div>
              <dl>
                <div><dt>From</dt><dd>ahmad.live@example.my</dd></div>
                <div><dt>Subject</dt><dd>Unauthorised card transaction</dd></div>
                <div><dt>Account</dt><dd className="mono">******6890</dd></div>
                <div><dt>Claim</dt><dd>{currency.format(2450)} · TECHWORLD KL</dd></div>
              </dl>
              <blockquote>
                “I did not authorise this card payment. My card has remained with me. Please investigate and reverse the charge.”
              </blockquote>
              <p>This fictional customer protects privacy. The execution underneath is not fictional.</p>
              <button className="btn primary live-primary" type="button" onClick={runLiveCase} disabled={busy || loadingProof || runnerOff}>
                {busy ? "Executing Live…" : "Run a Fresh Live Complaint"}
              </button>
              <p className="field-help">
                {runnerOff
                  ? "The public live runner is switched off right now, so nothing can be executed from here."
                  : "The sample mints its own run token on the server, so the browser only learns it once the run is over. It cannot be watched stage by stage; the composer can."}
              </p>
            </article>
          )}
        </div>
      </section>

      <section className="execution-stage" aria-live="polite" aria-busy={busy || loadingProof}>
        {progress && !proof ? viewToggle : null}
        {progress && !proof && view === "board" ? (
          <Boardroom
            seats={roster?.seats ?? null}
            rosterError={rosterError || undefined}
            handoffs={liveHandoffs}
            state={progress.state}
            quarantined={progress.quarantined}
            caseRef={progress.case_ref}
            startedAt={progress.started_at}
            elapsedSeconds={busy ? elapsed / 1000 : progress.value?.elapsed_seconds ?? null}
          />
        ) : null}
        {progress && !proof && view === "list" ? (
          <div className="stage-rail" aria-live="off">
            <div className="stage-rail-head">
              <div>
                <p className="eyebrow mono">
                  Live progress / {progress.events_recorded} hashed {progress.events_recorded === 1 ? "event" : "events"} so far
                </p>
                <h2>{stagesDone} of {progress.stages.length} stages recorded.</h2>
                <p>
                  A stage lights up only once its chained database event exists. Nothing here runs
                  ahead of the evidence.
                </p>
              </div>
              <strong className="mono">{(elapsed / 1000).toFixed(1)}s</strong>
            </div>
            <p className="sr-only" role="status">{stagesDone} of {progress.stages.length} pipeline stages recorded.</p>
            {progress.quarantined ? (
              <p className="stage-quarantined">
                The injection firewall quarantined this message before any model read it. The run
                stopped on purpose — that is the control working, not a stalled pipeline.
              </p>
            ) : null}
            <ol>
              {progress.stages.map((stage, index) => (
                <li key={stage.id} className={stage.done ? "done" : undefined}>
                  <span className="stage-tick mono" aria-hidden="true">{stage.done ? "✓" : String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <strong>{stage.label}</strong>
                    <small className="mono">{stage.agent} · {stage.event_type}</small>
                  </div>
                  <span className="stage-elapsed mono">{stageElapsed(stage, progress.started_at)}</span>
                </li>
              ))}
            </ol>
            <p className="stage-rail-foot mono">
              {progress.case_ref ? `CASE ${progress.case_ref}` : "CASE REFERENCE PENDING"} · {progress.state}
            </p>
          </div>
        ) : null}
        {progress && !proof && progress.value && (progress.value.stages_spoken > 0 || progress.quarantined) ? (
          <ValueLedger
            handoffs={liveHandoffs}
            value={progress.value}
            seats={roster?.seats ?? null}
            analystDefault={roster?.analyst_hourly_rm ?? null}
            startedAt={progress.started_at}
            quarantined={progress.quarantined}
            running={progress.state === "RUNNING"}
          />
        ) : null}

        {busy && !progress ? (
          <div className="execution-wait">
            <span className="live-pulse" aria-hidden="true" />
            <div>
              <p className="eyebrow mono">Request accepted / waiting for signed result</p>
              <h2>Production services are working.</h2>
              <p>No stage is marked complete until its database event and hash return.</p>
            </div>
            <strong className="mono">{(elapsed / 1000).toFixed(1)}s</strong>
          </div>
        ) : null}

        {loadingProof ? (
          <div className="execution-wait"><span className="live-pulse" aria-hidden="true" /><h2>Opening persisted proof…</h2></div>
        ) : null}

        {error ? (
          <div className="execution-error" role="alert">
            <div>
              <p className="eyebrow mono">
                {tab === "compose" ? "Refused or stopped / no fallback data" : "Honest failure / no fallback data"}
              </p>
              <h2>{tab === "compose" ? "This complaint did not run." : "The live run did not complete."}</h2>
              <p>{error}</p>
              {tab === "compose" ? <p>Adjust the complaint above and submit it again.</p> : null}
            </div>
            <div className="live-actions">
              {tab === "sample" ? <button className="btn primary" type="button" onClick={runLiveCase}>Try Live Run Again</button> : null}
              <button className="btn ghost" type="button" onClick={loadLatest}>Open Latest Completed Proof</button>
            </div>
          </div>
        ) : null}

        {proof && !loadingProof ? (
          <>
            <header className="proof-verdict">
              <div>
                <p className="eyebrow mono">Execution receipt / {proof.execution.runtime}</p>
                <h2>{proof.execution.case_ref}</h2>
                <p>{proof.execution.reused ? "Reopened persisted execution" : "Fresh execution"} · completed {displayDate(proof.execution.completed_at)}</p>
              </div>
              <div className={verified ? "live-stamp verified" : "live-stamp degraded"}>
                <span>{verified ? "Verified Live" : "Live · Degraded"}</span>
                <small>{(proof.execution.duration_ms / 1000).toFixed(2)} seconds</small>
              </div>
            </header>

            {notice ? <p className="proof-notice" role="status">{notice}</p> : null}
            {proof.result.degraded.length ? <div className="degraded-note" role="alert"><strong>Degraded capability</strong><span>{proof.result.degraded.join(" · ")}</span></div> : null}

            <section className="input-receipt" aria-labelledby="input-receipt-title">
              <div className="input-receipt-copy">
                <p className="eyebrow mono">
                  Input receipt / {proof.input.authored_by === "STAKEHOLDER" ? "written by this visitor" : "sanitised sample"}
                </p>
                <h2 id="input-receipt-title">
                  {proof.input.authored_by === "STAKEHOLDER"
                    ? "This result starts with what you submitted."
                    : "This result starts with the labelled sample."}
                </h2>
                <p>
                  The fictional identity only keeps real customer data out of the public demo. The
                  complaint wording, amount, merchant and PDF below are the inputs the pipeline used.
                </p>
              </div>
              <dl>
                <div><dt>Subject</dt><dd>{proof.input.subject}</dd></div>
                <div><dt>Claim</dt><dd>{currency.format(proof.input.amount_rm)} · {proof.input.merchant}</dd></div>
                <div><dt>Evidence</dt><dd>{proof.input.attachment ? `${proof.input.attachment} · ${attachmentMethod}` : attachmentMethod}</dd></div>
                <div>
                  <dt>Words received</dt>
                  <dd className="mono">
                    {proof.input.body_chars == null ? "Sample fixture" : `${proof.input.body_chars} characters`}
                    {proof.input.body_sha256 ? ` · SHA-256 ${proof.input.body_sha256.slice(0, 12)}…` : ""}
                  </dd>
                </div>
              </dl>
            </section>

            {proofHandoffs.length ? (
              <>
                {viewToggle}
                {view === "board" ? (
                  <Boardroom
                    seats={proofSeats}
                    rosterError={!proof.roster && !roster ? rosterError || undefined : undefined}
                    handoffs={proofHandoffs}
                    state="COMPLETED"
                    quarantined={proofQuarantined}
                    caseRef={proof.execution.case_ref}
                    startedAt={proof.execution.started_at}
                    elapsedSeconds={proof.execution.duration_ms / 1000}
                    reused={proof.execution.reused}
                  />
                ) : null}
                {proof.value ? (
                  <ValueLedger
                    handoffs={proofHandoffs}
                    value={proof.value}
                    seats={proofSeats}
                    analystDefault={roster?.analyst_hourly_rm ?? null}
                    startedAt={proof.execution.started_at}
                    quarantined={proofQuarantined}
                    running={false}
                  />
                ) : null}
              </>
            ) : null}

            <div className="proof-outcome" aria-label="Live outcome">
              <div><span>Case Status</span><strong>{proof.result.status}</strong></div>
              <div><span>Bank Evidence</span><strong>{proof.result.verification_result}</strong></div>
              <div><span>Financial Posting</span><strong>{proof.result.posted ? "POSTED" : "NOT POSTED"}</strong></div>
              <div><span>Audit Chain</span><strong>{proof.chain.ok ? `${proof.chain.links} LINKS · VALID` : "BROKEN"}</strong></div>
            </div>

            <section className="audit-tape" aria-labelledby="tape-title">
              <div className="audit-tape-head"><div><p className="eyebrow mono">Continuous evidence rail</p><h2 id="tape-title">What happened, in order.</h2></div><span className="mono">{proof.stages.length} GATES / {proof.chain.links} HASHED EVENTS</span></div>
              <ol>
                {proof.stages.map((stage, index) => (
                  <li key={stage.id} className={stage.status === "SKIPPED" ? "stage-skipped" : undefined}>
                    <span className="tape-index mono">{String(index + 1).padStart(2, "0")}</span>
                    <div className="tape-copy"><div><h3>{stage.label}</h3><span className="mono">{stage.event_type}</span></div><p>{stage.evidence}</p><small className="mono">{stage.actor ?? "—"} · {stage.recorded_at ? displayDate(stage.recorded_at) : "persisted in sequence"}</small></div>
                    <div className="tape-proof"><strong>{stage.status}</strong><span className="mono">SEQ {stage.seq ?? "—"}</span><code>{stage.hash?.slice(0, 14) ?? "—"}…</code></div>
                  </li>
                ))}
              </ol>
            </section>

            <section className="proof-grid" aria-label="Technical execution receipts">
              <article className="proof-block">
                <p className="eyebrow mono">Model telemetry / actual</p>
                <h2>{proof.models.length} metered calls</h2>
                <p className="proof-block-lede">{wholeNumber.format(totalTokens)} tokens were recorded against this case.</p>
                <div className="receipt-list">
                  {proof.models.map((call, index) => <div key={`${call.agent}-${index}`}><span>{call.agent}</span><strong>{call.provider} / {call.model}</strong><small className="mono">{call.latency_ms}ms · {call.tokens_in + call.tokens_out} tokens</small></div>)}
                </div>
              </article>

              <article className="proof-block dark">
                <p className="eyebrow mono">MCP gateway / actual</p>
                <h2>{proof.tools.length} bank tool calls</h2>
                <p className="proof-block-lede">The model did not decide whether the ledger matched or whether money could move.</p>
                <div className="receipt-list">
                  {proof.tools.map((call, index) => <div key={`${call.tool}-${index}`}><span>{call.ok ? "PASS" : "FAIL"}</span><strong>{call.server}.{call.tool}</strong><small className="mono">{call.transport} · {call.latency_ms == null ? "recorded" : `${call.latency_ms}ms`}</small></div>)}
                </div>
              </article>
            </section>

            <section className="journal-proof" aria-labelledby="journal-title">
              <div className="journal-copy"><p className="eyebrow mono">Financial kernel</p><h2 id="journal-title">One amount. Two sides. Zero model authority.</h2><p>The resolver could post only after PASS evidence and a short-lived ticket signed by the deterministic gate.</p></div>
              {proof.journal.entries.map((entry, index) => <div className="journal-entry" key={`${entry.entry_type}-${index}`}><div><span>Debit</span><strong>{entry.debit_account}</strong><em>{currency.format(entry.amount_rm)}</em></div><b aria-hidden="true">=</b><div><span>Credit</span><strong>{entry.credit_account_masked}</strong><em>{currency.format(entry.amount_rm)}</em></div></div>)}
              <div className="journal-balance mono">{proof.journal.balanced ? "BALANCED · POSTED BY SIGNED AUTHORITY" : "NOT BALANCED · ACTION REQUIRED"}</div>
            </section>

            <footer className="chain-footer">
              <div><p className="eyebrow mono">Tamper-evident head hash</p><code>{proof.chain.head_hash ?? "No hash returned"}</code></div>
              <div className="live-actions">
                <button className="btn ghost" type="button" onClick={copyProofLink}>Copy Proof Link</button>
                {tab === "compose"
                  ? <a className="btn primary" href="#compose-body">Write Another Complaint</a>
                  : <button className="btn primary" type="button" onClick={runLiveCase}>Run Another Live Case</button>}
              </div>
            </footer>
          </>
        ) : null}

        {!progress && !busy && !loadingProof && !error && !proof ? (
          <>
            {roster ? (
              <Boardroom
                seats={roster.seats}
                handoffs={[]}
                state="IDLE"
                quarantined={false}
              />
            ) : null}
            <div className="execution-empty">
              <span className="mono">NOT RUN YET</span>
              <h2>The evidence rail starts empty.</h2>
              <p>
                {tab === "compose"
                  ? "Write the complaint above and submit it. Axiom will fill this space only with receipts returned by the live backend."
                  : "Press “Run a Fresh Live Complaint.” Axiom will fill this space only with receipts returned by the live backend."}
              </p>
            </div>
          </>
        ) : null}
      </section>

      <section className="what-is-real" aria-labelledby="real-title">
        <div><p className="eyebrow mono">The honest boundary</p><h2 id="real-title">Synthetic person. Production behavior.</h2></div>
        <dl>
          <div><dt>Why not a real customer?</dt><dd>The words are yours, but the identity cannot be. A public link must never become a real PII intake channel, so the complaint must name one of six fictional customers and any other account number or NRIC is refused outright rather than quietly stripped.</dd></div>
          <div><dt>What is live?</dt><dd>FastAPI, the selected LLM, MCP core-banking tools, policy gates, Supabase rows, journal posting, and hash verification.</dd></div>
          <div><dt>How does a bank go live?</dt><dd>Staff connect the approved complaints mailbox and core/CRM MCP servers, then invite operators by work email.</dd></div>
        </dl>
      </section>

      <footer className="welcome-foot mono">CASEZERO · AXIOM LIVE EXECUTION · SANITIZED INPUT / VERIFIABLE OUTPUT</footer>
    </main>
  );
}

export default function LivePage() {
  return <Suspense fallback={<main className="live-page"><div className="execution-empty"><h1>Opening Live Case…</h1></div></main>}><LiveRunner /></Suspense>;
}
