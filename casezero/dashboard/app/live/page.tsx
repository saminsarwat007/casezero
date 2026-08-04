"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";

type Stage = {
  id: string;
  label: string;
  status: "PASS" | "MISSING";
  event_type: string;
  seq?: number | null;
  actor?: string | null;
  recorded_at?: string | null;
  hash?: string | null;
  evidence: string;
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

function LiveRunner() {
  const router = useRouter();
  const search = useSearchParams();
  const [response, setResponse] = useState<LiveResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingProof, setLoadingProof] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [elapsed, setElapsed] = useState(0);

  const proof = response?.proof ?? null;
  const verified = proof?.execution.assurance === "VERIFIED_LIVE";
  const runToken = search.get("run");

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

  async function runLiveCase() {
    setBusy(true);
    setElapsed(0);
    setError("");
    setNotice("");
    setResponse(null);
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
        <span><i aria-hidden="true" /> Synthetic Customer Input</span>
        <strong>Real API · Real Model · MCP Bank Tools · Real Supabase Writes</strong>
      </section>

      <section className="live-hero" aria-labelledby="live-title">
        <div className="live-intro">
          <p className="eyebrow mono">Axiom / Live Case 01</p>
          <h1 id="live-title">Watch one complaint become proof.</h1>
          <p>
            No dashboard tour. No prefilled result. Run one sanitized email through the deployed
            banking-dispute pipeline, then inspect the evidence Axiom actually wrote.
          </p>
          <div className="live-actions">
            <button className="btn primary live-primary" type="button" onClick={runLiveCase} disabled={busy || loadingProof}>
              {busy ? "Executing Live…" : "Run a Fresh Live Complaint"}
            </button>
            {proof ? <button className="btn ghost" type="button" onClick={downloadProof}>Download Proof JSON</button> : null}
          </div>
          <p className="live-budget mono">ALLOW-LISTED FIXTURE · MAX 2 RUNS / DEVICE / HOUR · NO PUBLIC PII UPLOAD</p>
        </div>

        <article className="fixture-sheet" aria-label="Sanitized complaint that will be executed">
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
        </article>
      </section>

      <section className="execution-stage" aria-live="polite" aria-busy={busy || loadingProof}>
        {busy ? (
          <div className="execution-wait">
            <span className="live-pulse" aria-hidden="true" />
            <div>
              <p className="eyebrow mono">Request accepted / waiting for signed result</p>
              <h2>Production services are working.</h2>
              <p>No stage is marked complete until its database event and hash return.</p>
            </div>
            <strong className="mono">{(elapsed / 1000).toFixed(1)}s</strong>
          </div>
        ) : loadingProof ? (
          <div className="execution-wait"><span className="live-pulse" aria-hidden="true" /><h2>Opening persisted proof…</h2></div>
        ) : error ? (
          <div className="execution-error" role="alert">
            <div><p className="eyebrow mono">Honest failure / no fallback data</p><h2>The live run did not complete.</h2><p>{error}</p></div>
            <div className="live-actions"><button className="btn primary" type="button" onClick={runLiveCase}>Try Live Run Again</button><button className="btn ghost" type="button" onClick={loadLatest}>Open Latest Completed Proof</button></div>
          </div>
        ) : proof ? (
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
                  <li key={stage.id}>
                    <span className="tape-index mono">{String(index + 1).padStart(2, "0")}</span>
                    <div className="tape-copy"><div><h3>{stage.label}</h3><span className="mono">{stage.event_type}</span></div><p>{stage.evidence}</p><small className="mono">{stage.actor ?? "—"} · {stage.recorded_at ? displayDate(stage.recorded_at) : "persisted in sequence"}</small></div>
                    <div className="tape-proof"><strong>{stage.status}</strong><span className="mono">SEQ {stage.seq ?? "—"}</span><code>{stage.hash?.slice(0, 14) ?? "missing"}…</code></div>
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
              <div className="live-actions"><button className="btn ghost" type="button" onClick={copyProofLink}>Copy Proof Link</button><button className="btn primary" type="button" onClick={runLiveCase}>Run Another Live Case</button></div>
            </footer>
          </>
        ) : (
          <div className="execution-empty">
            <span className="mono">NOT RUN YET</span>
            <h2>The evidence rail starts empty.</h2>
            <p>Press “Run a Fresh Live Complaint.” Axiom will fill this space only with receipts returned by the live backend.</p>
          </div>
        )}
      </section>

      <section className="what-is-real" aria-labelledby="real-title">
        <div><p className="eyebrow mono">The honest boundary</p><h2 id="real-title">Synthetic person. Production behavior.</h2></div>
        <dl>
          <div><dt>Why not a real customer?</dt><dd>A public judge link must never expose bank PII or create an unauthenticated complaint-upload channel.</dd></div>
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
