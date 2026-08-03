"use client";

import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, isRehearsal } from "@/lib/api";
import { useCases } from "@/hooks/use-cases";

type Action = "APPROVE" | "REJECT" | "REQUEST_INFO";

export default function ReviewPage() {
  const { cases, refresh } = useCases("REVIEW_PENDING");
  const [selected, setSelected] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const current = useMemo(() => cases.find((item) => item.case_ref === selected) ?? cases[0], [cases, selected]);

  async function act(action: Action) {
    if (!current || busy) return;
    if (action === "REJECT" && !window.confirm(`Reject ${current.case_ref}? This records a formal decision on the complaint.`)) return;
    setBusy(true); setNotice(null);
    if (isRehearsal()) {
      setNotice(`${action.replaceAll("_", " ")} rehearsed for ${current.case_ref}. No bank data changed.`);
      setBusy(false); return;
    }
    try {
      const result = await apiFetch<{ status: string }>(`/review/${current.case_ref}`, { method: "POST", body: JSON.stringify({ action, note }) });
      setNotice(`${current.case_ref} is now ${result.status.replaceAll("_", " ")}.`);
      await refresh(); setSelected(null); setNote("");
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Review action failed."); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key.toLowerCase() === "a") void act("APPROVE");
      if (event.key.toLowerCase() === "r") void act("REJECT");
      if (event.key.toLowerCase() === "i") void act("REQUEST_INFO");
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  });

  return (
    <AppShell>
      <PageHeader eyebrow="Investigator co-pilot / Target under 60 seconds" title="Decide with the evidence assembled." lede="A approves, R rejects, I requests information. Every action remains subject to the same kernel and compliance gates." />
      {notice ? <div className="panel panel-pad" role="status" style={{ marginTop: 18 }}>{notice}</div> : null}
      <div className="review-layout section">
        <section className="table-wrap" aria-label="Cases awaiting review">
          <table className="data-table"><thead><tr><th scope="col">Case</th><th scope="col">Claim</th><th scope="col">Verification</th><th scope="col">Urgency</th><th scope="col">SLA due</th></tr></thead><tbody>{cases.map((item) => <tr key={item.id} className={current?.id === item.id ? "selected" : ""}><td><button type="button" className="table-link mono" aria-pressed={current?.id === item.id} onClick={() => setSelected(item.case_ref)}>{item.case_ref}</button></td><td><strong>RM {Number(item.amount_rm || 0).toFixed(2)}</strong><div className="muted">{item.summary}</div></td><td><StatusBadge status={item.verification_result} /></td><td>{item.urgency}</td><td className="mono">{item.sla_due ? new Date(item.sla_due).toLocaleDateString("en-MY") : "—"}</td></tr>)}</tbody></table>
          {!cases.length ? <div className="empty">No cases are waiting for a human. This is the desired empty state.</div> : null}
        </section>
        <aside className="panel panel-pad decision-panel">
          <p className="eyebrow mono">Decision register</p><h2 className="section-title">{current?.case_ref || "Select a case"}</h2>
          {current ? <><dl className="fact-list"><div className="fact-row"><dt>Claimed</dt><dd className="mono">RM {Number(current.amount_rm || 0).toFixed(2)}</dd></div><div className="fact-row"><dt>Category</dt><dd>{current.category?.replaceAll("_", " ")}</dd></div><div className="fact-row"><dt>Confidence</dt><dd className="mono">{Math.round(Number(current.confidence || 0) * 100)}%</dd></div></dl><div className="field" style={{ marginTop: 16 }}><label htmlFor="review-note">Decision note</label><textarea id="review-note" name="review_note" autoComplete="off" className="textarea" value={note} onChange={(event) => setNote(event.target.value)} /></div><div className="decision-actions"><button className="btn primary" onClick={() => void act("APPROVE")} disabled={busy}><span className="kbd">A</span> Approve resolution</button><button className="btn danger" onClick={() => void act("REJECT")} disabled={busy}><span className="kbd">R</span> Reject claim</button><button className="btn ghost" onClick={() => void act("REQUEST_INFO")} disabled={busy}><span className="kbd">I</span> Request information</button></div></> : <p className="muted">Choose a row to inspect the prepared decision.</p>}
        </aside>
      </div>
    </AppShell>
  );
}
