"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, isRehearsal } from "@/lib/api";

type WajarPlan = {
  plan_id: string;
  action: string;
  title: string;
  summary: string;
  effect: string;
  authority: string;
  confirmation_required: boolean;
  permitted: boolean;
  route?: string | null;
  parameters: Record<string, unknown>;
  gates: string[];
  result: Record<string, unknown>;
};

const prompts = ["Summarise operations", "Show cases at SLA risk", "Verify MYB-2026-000012", "Open the review queue"];

function rehearsalPlan(command: string): WajarPlan {
  const lower = command.toLowerCase();
  const base = {
    plan_id: `WJP-${Math.abs(command.split("").reduce((total, char) => (total * 31 + char.charCodeAt(0)) | 0, 7)).toString(16).toUpperCase().padStart(8, "0")}`,
    effect: "Read-only rehearsal; no bank or customer data changes.", authority: "Any signed-in operator",
    confirmation_required: false, permitted: true, parameters: {}, gates: ["Synthetic rehearsal register", "No external writes"], result: {},
  };
  const ref = command.match(/MYB-\d{4}-\d{6}/i)?.[0]?.toUpperCase();
  if ((lower.includes("verify") || lower.includes("chain")) && ref) return { ...base, action: "VERIFY_CHAIN", title: `Verify ${ref}`, summary: "Eight event links recomputed from canonical payloads; no mismatch was found.", route: `/case/${ref}`, gates: ["RLS-visible case", "SHA-256 chain recomputation"], result: { verdict: "VERIFIED", links: 8, first_bad_seq: null } };
  if (lower.includes("risk") || lower.includes("deadline") || lower.includes("breach")) return { ...base, action: "SHOW_SLA_RISK", title: "Cases approaching deadline", summary: "Two open cases are inside the configured 24-hour warning horizon.", route: "/simple", result: { count: 2, warning_hours: 24, next_case: "MYB-2026-000015" } };
  if (lower.includes("summar" ) || lower.includes("operations") || lower.includes("today")) return { ...base, action: "SUMMARISE_OPERATIONS", title: "Operations summary", summary: "Five cases are visible; two need attention and one is fully communicated.", route: "/pro", result: { total: 5, needs_attention: 2, communicated: 1, automation_rate: "20.0%" } };
  if ((lower.includes("set") || lower.includes("turn")) && (lower.includes("sla") || lower.includes("resolution") || lower.includes("wajar"))) return { ...base, action: "UPDATE_SETTING", title: "Change an operating control", summary: lower.includes("sla") ? "Set SLA warning horizon to 12 hours." : "Update the selected operating control.", effect: "The control register changes and a hash-chained settings event is appended.", authority: "Admin only", confirmation_required: true, parameters: lower.includes("sla") ? { key: "sla_warning_hours", value: 12 } : {}, gates: ["Admin role", "Explicit confirmation", "Server-side validation", "Hash-chained settings event"] };
  const nav = lower.includes("review") ? ["OPEN_REVIEW", "Open the review queue", "/review"] : lower.includes("policy") ? ["OPEN_POLICY", "Open Policy Studio", "/policy"] : lower.includes("setting") ? ["OPEN_SETTINGS", "Open Settings", "/settings"] : lower.includes("quarantine") ? ["OPEN_QUARANTINE", "Open Quarantine", "/quarantine"] : null;
  if (nav) return { ...base, action: nav[0], title: nav[1], summary: `Take the operator to ${nav[1].toLowerCase()}.`, route: nav[2] };
  return { ...base, action: "HELP", title: "I can prepare a governed action", summary: "Ask for an operations summary, deadline risk, a case-chain check, navigation, or an administrative control change." };
}

export function WajarDocket() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [command, setCommand] = useState("");
  const [plan, setPlan] = useState<WajarPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);

  useEffect(() => {
    function requested(event: Event) {
      const detail = (event as CustomEvent<string>).detail;
      setOpen(true); setCommand(detail || ""); setPlan(null); setReceipt(null);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
    function escape(event: KeyboardEvent) { if (event.key === "Escape") setOpen(false); }
    window.addEventListener("casezero:wajar", requested);
    window.addEventListener("keydown", escape);
    return () => { window.removeEventListener("casezero:wajar", requested); window.removeEventListener("keydown", escape); };
  }, []);

  useEffect(() => { if (open) requestAnimationFrame(() => inputRef.current?.focus()); }, [open]);

  async function prepare(event?: FormEvent) {
    event?.preventDefault();
    if (command.trim().length < 2) return;
    setBusy(true); setError(null); setReceipt(null);
    try {
      if (isRehearsal()) setPlan(rehearsalPlan(command.trim()));
      else setPlan((await apiFetch<{ plan: WajarPlan }>("/assistant/plan", { method: "POST", body: JSON.stringify({ command: command.trim() }) })).plan);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Wajar could not prepare this action."); }
    finally { setBusy(false); }
  }

  async function continueAction() {
    if (!plan?.permitted) return;
    if (!plan.confirmation_required && plan.route) { setOpen(false); router.push(plan.route); return; }
    if (!plan.confirmation_required) return;
    setBusy(true); setError(null);
    try {
      if (isRehearsal()) {
        setReceipt(`WJR-${plan.plan_id.replace("WJP-", "")}-REHEARSAL`);
      } else {
        const response = await apiFetch<{ receipt: { receipt_id: string } }>("/assistant/execute", { method: "POST", body: JSON.stringify({ command: command.trim(), confirm: true }) });
        setReceipt(response.receipt.receipt_id);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Wajar could not execute this action."); }
    finally { setBusy(false); }
  }

  return (
    <>
      <button className="wajar-launch" type="button" onClick={() => setOpen(true)} aria-label="Open Wajar operating agent" aria-expanded={open} aria-controls="wajar-docket">
        <span className="wajar-glyph" aria-hidden="true">W</span><span><strong>Wajar</strong><small>Operating agent</small></span>
      </button>
      {open ? <div className="wajar-scrim" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
        <aside className="wajar-docket" id="wajar-docket" role="dialog" aria-modal="true" aria-labelledby="wajar-title">
          <header className="wajar-head">
            <div><p className="eyebrow mono">Wajar by CaseZero / Control docket</p><h2 id="wajar-title">Ask. Inspect. Act.</h2><p>Wajar can use named bank capabilities. It cannot invent authority or bypass a gate.</p></div>
            <button className="wajar-close" type="button" onClick={() => setOpen(false)} aria-label="Close Wajar">×</button>
          </header>
          <form className="wajar-command" onSubmit={prepare}>
            <label htmlFor="wajar-input">What needs to happen?</label>
            <div className="wajar-input-row"><input ref={inputRef} id="wajar-input" value={command} onChange={(event) => { setCommand(event.target.value); setPlan(null); setReceipt(null); }} placeholder="Show cases at SLA risk" autoComplete="off" /><button type="submit" disabled={busy || command.trim().length < 2}>{busy ? "Preparing…" : "Prepare action"}</button></div>
          </form>
          {!plan ? <div className="wajar-prompts" aria-label="Suggested Wajar commands">{prompts.map((prompt) => <button type="button" key={prompt} onClick={() => { setCommand(prompt); setPlan(null); inputRef.current?.focus(); }}>{prompt}</button>)}</div> : null}
          {error ? <div className="error-box" role="alert">{error}</div> : null}
          {plan ? <section className="action-docket" aria-live="polite">
            <div className="docket-stamp"><span className="mono">{plan.plan_id}</span><strong>{plan.permitted ? "PREPARED" : "REFUSED"}</strong></div>
            <p className="eyebrow mono">Selected capability / {plan.action.replaceAll("_", " ")}</p>
            <h3>{plan.title}</h3><p className="docket-summary">{plan.summary}</p>
            <dl className="docket-facts"><div><dt>Effect</dt><dd>{plan.effect}</dd></div><div><dt>Authority</dt><dd>{plan.authority}</dd></div><div><dt>Confirmation</dt><dd>{plan.confirmation_required ? "Required" : "Not required"}</dd></div></dl>
            {Object.keys(plan.result).length ? <div className="docket-result"><p className="eyebrow mono">Result preview</p>{Object.entries(plan.result).slice(0, 5).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong className="mono">{typeof value === "object" ? JSON.stringify(value) : String(value)}</strong></div>)}</div> : null}
            <div className="docket-gates"><p className="eyebrow mono">Controls that remain in force</p><ol>{plan.gates.map((gate) => <li key={gate}>{gate}</li>)}</ol></div>
            {receipt ? <div className="wajar-receipt" role="status"><span>Execution receipt</span><strong className="mono">{receipt}</strong><small>{isRehearsal() ? "Rehearsal only · no live control changed" : "Recorded in the Wajar action ledger"}</small></div> : null}
            {!receipt && plan.permitted && (plan.route || plan.confirmation_required) ? <button className="btn primary docket-action" type="button" onClick={() => void continueAction()} disabled={busy}>{plan.confirmation_required ? "Confirm and execute" : "Open destination"}<span aria-hidden="true">↗</span></button> : null}
          </section> : null}
          <footer className="wajar-foot mono">NO DIRECT POSTING CAPABILITY · MONEY STILL REQUIRES PASS + SIGNED KERNEL TICKET</footer>
        </aside>
      </div> : null}
    </>
  );
}
