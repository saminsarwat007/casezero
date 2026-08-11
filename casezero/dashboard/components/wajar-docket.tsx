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
  reply: string;
  understood_by: "deterministic" | "model";
};

/** One turn of the conversation.
 *
 * An Axiom turn carries the command it answered *and* the plan it produced, so
 * confirming an older docket re-plans that command and not whatever was typed
 * afterwards.
 */
type Turn = {
  id: number;
  role: "operator" | "axiom";
  text: string;
  command?: string;
  plan?: WajarPlan;
  receipt?: string;
  failed?: boolean;
};

const prompts = ["Summarise operations", "Show cases at SLA risk", "Verify MYB-2026-000012", "Open the review queue"];

function rehearsalPlan(command: string): WajarPlan {
  const lower = command.toLowerCase();
  const base = {
    plan_id: `AXP-${Math.abs(command.split("").reduce((total, char) => (total * 31 + char.charCodeAt(0)) | 0, 7)).toString(16).toUpperCase().padStart(8, "0")}`,
    effect: "Read-only rehearsal; no bank or customer data changes.", authority: "Any signed-in operator",
    confirmation_required: false, permitted: true, parameters: {}, gates: ["Synthetic rehearsal register", "No external writes"], result: {},
    reply: "", understood_by: "deterministic" as const,
  };
  const ref = command.match(/MYB-\d{4}-\d{6}/i)?.[0]?.toUpperCase();
  if ((lower.includes("verify") || lower.includes("chain")) && ref) return { ...base, action: "VERIFY_CHAIN", title: `Verify ${ref}`, summary: "Eight event links recomputed from canonical payloads; no mismatch was found.", route: `/case/${ref}`, gates: ["RLS-visible case", "SHA-256 chain recomputation"], result: { verdict: "VERIFIED", links: 8, first_bad_seq: null } };
  if (lower.includes("risk") || lower.includes("deadline") || lower.includes("breach")) return { ...base, action: "SHOW_SLA_RISK", title: "Cases approaching deadline", summary: "Two open cases are inside the configured 24-hour warning horizon.", route: "/simple", result: { count: 2, warning_hours: 24, next_case: "MYB-2026-000015" } };
  if (lower.includes("summar" ) || lower.includes("operations") || lower.includes("today")) return { ...base, action: "SUMMARISE_OPERATIONS", title: "Operations summary", summary: "Five cases are visible; two need attention and one is fully communicated.", route: "/pro", result: { total: 5, needs_attention: 2, communicated: 1, automation_rate: "20.0%" } };
  if ((lower.includes("set") || lower.includes("turn")) && (lower.includes("sla") || lower.includes("resolution") || lower.includes("axiom") || lower.includes("wajar"))) return { ...base, action: "UPDATE_SETTING", title: "Change an operating control", summary: lower.includes("sla") ? "Set SLA warning horizon to 12 hours." : "Update the selected operating control.", effect: "The control register changes and a hash-chained settings event is appended.", authority: "Admin only", confirmation_required: true, parameters: lower.includes("sla") ? { key: "sla_warning_hours", value: 12 } : {}, gates: ["Admin role", "Explicit confirmation", "Server-side validation", "Hash-chained settings event"] };
  const nav = lower.includes("review") ? ["OPEN_REVIEW", "Open the review queue", "/review"] : lower.includes("policy") ? ["OPEN_POLICY", "Open Policy Studio", "/policy"] : lower.includes("setting") ? ["OPEN_SETTINGS", "Open Settings", "/settings"] : lower.includes("quarantine") ? ["OPEN_QUARANTINE", "Open Quarantine", "/quarantine"] : null;
  if (nav) return { ...base, action: nav[0], title: nav[1], summary: `Take the operator to ${nav[1].toLowerCase()}.`, route: nav[2] };
  return { ...base, action: "HELP", title: "I can prepare a governed action", summary: "Ask for an operations summary, deadline risk, a case-chain check, navigation, or an administrative control change." };
}

/** The server sends `reply` already defaulted to `summary`; rehearsal must match
 *  or the offline conversation renders empty bubbles. */
const spoken = (plan: WajarPlan) => plan.reply || plan.summary;

export function WajarDocket() {
  const router = useRouter();
  const launchRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const threadEnd = useRef<HTMLDivElement>(null);
  const nextId = useRef(0);
  const [open, setOpen] = useState(false);
  const [command, setCommand] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  function say(turn: Omit<Turn, "id">) {
    const id = (nextId.current += 1);
    setTurns((current) => [...current, { ...turn, id }]);
    return id;
  }

  useEffect(() => {
    function requested(event: Event) {
      const detail = (event as CustomEvent<string>).detail;
      setOpen(true); setCommand(detail || "");
      requestAnimationFrame(() => inputRef.current?.focus());
    }
    window.addEventListener("casezero:wajar", requested);
    return () => window.removeEventListener("casezero:wajar", requested);
  }, []);

  useEffect(() => { if (open) requestAnimationFrame(() => inputRef.current?.focus()); }, [open]);
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [open]);
  useEffect(() => { threadEnd.current?.scrollIntoView({ block: "end" }); }, [turns, busy]);

  function closeDocket() {
    setOpen(false);
    requestAnimationFrame(() => launchRef.current?.focus());
  }

  function keepFocusInDocket(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeDocket();
      return;
    }
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    )).filter((element) => !element.hasAttribute("hidden"));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function ask(event?: FormEvent) {
    event?.preventDefault();
    const asked = command.trim();
    if (asked.length < 2) return;
    setBusy(true); setCommand("");
    say({ role: "operator", text: asked });
    try {
      const plan = isRehearsal()
        ? rehearsalPlan(asked)
        : (await apiFetch<{ plan: WajarPlan }>("/assistant/plan", { method: "POST", body: JSON.stringify({ command: asked }) })).plan;
      say({ role: "axiom", text: spoken(plan), command: asked, plan });
    } catch (reason) {
      say({ role: "axiom", text: reason instanceof Error ? reason.message : "Axiom could not prepare this action.", failed: true });
    } finally { setBusy(false); }
  }

  async function continueAction(turn: Turn) {
    const plan = turn.plan;
    if (!plan?.permitted || !turn.command) return;
    if (!plan.confirmation_required && plan.route) { setOpen(false); router.push(plan.route); return; }
    if (!plan.confirmation_required) return;
    setBusy(true);
    try {
      if (isRehearsal()) {
        const receipt = `AXR-${plan.plan_id.replace("AXP-", "")}-REHEARSAL`;
        setTurns((current) => current.map((item) => (item.id === turn.id ? { ...item, receipt } : item)));
      } else {
        const response = await apiFetch<{ receipt: { receipt_id: string } }>("/assistant/execute", {
          method: "POST",
          // plan_id binds the confirmation to the docket that was inspected. If the
          // server's re-read lands on a different action it refuses with 409.
          body: JSON.stringify({ command: turn.command, confirm: true, plan_id: plan.plan_id }),
        });
        const receipt = response.receipt.receipt_id;
        setTurns((current) => current.map((item) => (item.id === turn.id ? { ...item, receipt } : item)));
      }
    } catch (reason) {
      say({ role: "axiom", text: reason instanceof Error ? reason.message : "Axiom could not execute this action.", failed: true });
    } finally { setBusy(false); }
  }

  return (
    <>
      <button ref={launchRef} className="wajar-launch" type="button" onClick={() => setOpen(true)} aria-label="Open Axiom operating agent" aria-expanded={open} aria-controls="wajar-docket">
        <span className="wajar-glyph" aria-hidden="true">A</span><span><strong>Axiom</strong><small>Operating agent</small></span>
      </button>
      {open ? <div className="wajar-scrim" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDocket(); }}>
        <aside ref={dialogRef} className="wajar-docket" id="wajar-docket" role="dialog" aria-modal="true" aria-labelledby="wajar-title" onKeyDown={keepFocusInDocket}>
          <header className="wajar-head">
            <div><p className="eyebrow mono">Axiom by CaseZero / Control docket</p><h2 id="wajar-title">Ask. Inspect. Act.</h2><p>Axiom can use named bank capabilities. It cannot invent authority or bypass a gate.</p></div>
            <button className="wajar-close" type="button" onClick={closeDocket} aria-label="Close Axiom">×</button>
          </header>

          <div className="wajar-thread" aria-live="polite" aria-busy={busy}>
            {turns.length === 0 ? (
              <div className="wajar-prompts" aria-label="Suggested Axiom commands">
                {prompts.map((prompt) => <button type="button" key={prompt} onClick={() => { setCommand(prompt); inputRef.current?.focus(); }}>{prompt}</button>)}
              </div>
            ) : null}

            {turns.map((turn) => (
              <article className={`wajar-msg ${turn.role}${turn.failed ? " failed" : ""}`} key={turn.id}>
                <p className="wajar-who mono">{turn.role === "operator" ? "You" : "Axiom"}</p>
                <p className="wajar-bubble">{turn.text}</p>

                {turn.plan ? (
                  <>
                    <p className={`wajar-understood mono${turn.plan.understood_by === "model" ? " by-model" : ""}`}>
                      {turn.plan.understood_by === "model" ? "Read by the language model · authority still decided in code" : "Matched without a model"}
                    </p>
                    <section className="action-docket" aria-label={`Action docket ${turn.plan.plan_id}`}>
                      <div className="docket-stamp"><span className="mono">{turn.plan.plan_id}</span><strong>{turn.plan.permitted ? "PREPARED" : "REFUSED"}</strong></div>
                      <p className="eyebrow mono">Selected capability / {turn.plan.action.replaceAll("_", " ")}</p>
                      <h3>{turn.plan.title}</h3>
                      {/* A deterministic plan has no separate reply, so the bubble already said this. */}
                      {turn.plan.summary === turn.text ? null : <p className="docket-summary">{turn.plan.summary}</p>}
                      <dl className="docket-facts"><div><dt>Effect</dt><dd>{turn.plan.effect}</dd></div><div><dt>Authority</dt><dd>{turn.plan.authority}</dd></div><div><dt>Confirmation</dt><dd>{turn.plan.confirmation_required ? "Required" : "Not required"}</dd></div></dl>
                      {Object.keys(turn.plan.result).length ? <div className="docket-result"><p className="eyebrow mono">Result preview</p>{Object.entries(turn.plan.result).slice(0, 5).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong className="mono">{typeof value === "object" ? JSON.stringify(value) : String(value)}</strong></div>)}</div> : null}
                      <div className="docket-gates"><p className="eyebrow mono">Controls that remain in force</p><ol>{turn.plan.gates.map((gate) => <li key={gate}>{gate}</li>)}</ol></div>
                      {turn.receipt ? <div className="wajar-receipt" role="status"><span>Execution receipt</span><strong className="mono">{turn.receipt}</strong><small>{isRehearsal() ? "Rehearsal only · no live control changed" : "Recorded in the Axiom action ledger"}</small></div> : null}
                      {!turn.receipt && turn.plan.permitted && (turn.plan.route || turn.plan.confirmation_required) ? <button className="btn primary docket-action" type="button" onClick={() => void continueAction(turn)} disabled={busy}>{turn.plan.confirmation_required ? "Confirm and execute" : "Open destination"}<span aria-hidden="true">↗</span></button> : null}
                    </section>
                  </>
                ) : null}
              </article>
            ))}

            {busy ? <p className="wajar-thinking mono">Axiom is reading the request…</p> : null}
            <div ref={threadEnd} />
          </div>

          <form className="wajar-command" onSubmit={ask}>
            <label htmlFor="wajar-input">What needs to happen?</label>
            <div className="wajar-input-row"><input ref={inputRef} id="wajar-input" name="axiom_command" value={command} minLength={2} required onChange={(event) => setCommand(event.target.value)} placeholder="Show cases at SLA risk…" autoComplete="off" /><button type="submit" disabled={busy}>{busy ? "Asking…" : "Ask Axiom"}</button></div>
          </form>
          <footer className="wajar-foot mono">NO DIRECT POSTING CAPABILITY · MONEY STILL REQUIRES PASS + SIGNED KERNEL TICKET</footer>
        </aside>
      </div> : null}
    </>
  );
}
