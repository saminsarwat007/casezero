"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Stamp } from "@/components/design/stamp";
import { StatusBadge } from "@/components/status-badge";
import { apiDownload, apiFetch, isRehearsal } from "@/lib/api";
import { demoDetail } from "@/lib/demo-data";
import type { CaseDetail } from "@/lib/types";

export default function CasePage() {
  const params = useParams<{ ref: string }>();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  useEffect(() => {
    if (isRehearsal()) { setDetail({ ...demoDetail, case: { ...demoDetail.case, case_ref: params.ref } }); return; }
    apiFetch<CaseDetail>(`/cases/${params.ref}`).then(setDetail).catch((reason) => setError(reason instanceof Error ? reason.message : "Case unavailable."));
  }, [params.ref]);
  const gate = useMemo(() => detail?.events.find((event) => event.event_type === "GATE_DECISION"), [detail]);
  const message = useMemo(() => [...(detail?.events || [])].reverse().find((event) => event.event_type === "MESSAGE_SENT"), [detail]);

  async function exportFmos() {
    setExporting(true); setError(null);
    if (isRehearsal()) {
      setError("Offline rehearsal cannot generate a live FMOS file. Use output/pdf/FMOS-MYB-2026-000012.pdf for the verified demo artifact.");
      setExporting(false); return;
    }
    try {
      const blob = await apiDownload(`/cases/${params.ref}/fmos-pack`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = `FMOS-${params.ref}.pdf`; link.click();
      URL.revokeObjectURL(url);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "FMOS export failed."); }
    finally { setExporting(false); }
  }

  return (
    <AppShell>
      <PageHeader eyebrow="Case file / Governance schema" title={params.ref} lede="The claim and the system of record are held in balance. Every decision names the rule and evidence that produced it." />
      {error ? <div className="error-box" role="alert" style={{ marginTop: 18 }}>{error}</div> : null}
      {!detail ? <div className="skeleton section" role="status" aria-label="Loading case record" /> : (
        <>
          <section className="section balance-grid" aria-label="Claimed compared with system of record">
            <div className="balance-side">
              <p className="eyebrow mono">Claimed / Customer statement</p>
              <h2 className="section-title">{detail.case.summary}</h2>
              <dl className="fact-list">
                <div className="fact-row"><dt>Amount</dt><dd className="mono">RM {Number(detail.case.amount_rm || 0).toLocaleString("en-MY", { minimumFractionDigits: 2 })}</dd></div>
                <div className="fact-row"><dt>Account</dt><dd className="mono">{detail.case.account_no_masked}</dd></div>
                <div className="fact-row"><dt>Channel</dt><dd>{detail.case.channel}</dd></div>
              </dl>
            </div>
            <div className="balance-divider mono">VERIFICATION</div>
            <div className="balance-side">
              <p className="eyebrow mono">Of record / Core banking</p>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14 }}>
                <h2 className="section-title">Evidence matched</h2><Stamp endorse={detail.case.verification_result !== "PASS"}>{detail.case.verification_result || "PENDING"}</Stamp>
              </div>
              <dl className="fact-list">
                <div className="fact-row"><dt>Category</dt><dd>{detail.case.category?.replaceAll("_", " ")}</dd></div>
                <div className="fact-row"><dt>Confidence</dt><dd className="mono">{Math.round(Number(detail.case.confidence || 0) * 100)}%</dd></div>
                <div className="fact-row"><dt>Status</dt><dd><StatusBadge status={detail.case.status} /></dd></div>
              </dl>
            </div>
          </section>

          <div className="detail-grid section">
            <section className="panel panel-pad" aria-labelledby="timeline-title">
              <p className="eyebrow mono">Append-only event chain</p><h2 id="timeline-title" className="section-title">Case timeline</h2>
              <ol className="timeline">{detail.events.map((event) => <li key={event.seq}><span className="timeline-seq mono">{String(event.seq).padStart(2, "0")}</span><div><strong>{event.event_type.replaceAll("_", " ")}</strong><div className="muted" style={{ fontSize: 12 }}>{event.actor}</div><div className="hash mono">{event.hash}</div></div></li>)}</ol>
            </section>
            <aside style={{ display: "grid", gap: 14, alignContent: "start" }}>
              <section className="panel panel-pad">
                <p className="eyebrow mono">Why?</p><h2 className="section-title">Decision provenance</h2>
                {gate ? <><ul>{((gate.payload.reasons as string[]) || []).map((reason) => <li key={reason}>{reason}</li>)}</ul><p className="eyebrow" style={{ marginTop: 20 }}>Citations</p>{((gate.payload.citations as string[]) || []).map((citation) => <div className="mono muted" style={{ fontSize: 10, marginTop: 6 }} key={citation}>{citation}</div>)}</> : <p className="muted">No gate ruling has been recorded yet.</p>}
              </section>
              <section className={`panel panel-pad ${detail.chain.ok ? "" : "void"}`}>
                <p className="eyebrow mono">Audit integrity</p><div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}><h2 className="section-title">{detail.chain.ok ? "Chain verified" : `Broken at ${detail.chain.first_bad_seq}`}</h2><Stamp endorse={!detail.chain.ok}>{detail.chain.ok ? "VALID" : "VOID"}</Stamp></div>
                <p className="muted">{detail.chain.ok ? `${detail.events.length} links recomputed without a break.` : detail.chain.reason}</p>
              </section>
              <section className="panel panel-pad"><p className="eyebrow mono">Measured model cost</p><div className="case-amount mono">RM {Number(detail.cost_rm).toFixed(6)}</div></section>
            </aside>
          </div>

          <section className="section panel panel-pad" aria-labelledby="journal-title">
            <p className="eyebrow mono">Double-entry journal</p><h2 id="journal-title" className="section-title">Money movement</h2>
            {detail.journal.length ? <div className="table-wrap" style={{ marginTop: 16 }}><table className="data-table"><caption className="sr-only">Balanced journal entries for this case</caption><thead><tr><th scope="col">Entry</th><th scope="col">Debit</th><th scope="col">Credit</th><th scope="col">Amount</th><th scope="col">Posted by</th></tr></thead><tbody>{detail.journal.map((entry, index) => <tr key={index}><td>{String(entry.entry_type)}</td><td className="mono">{String(entry.debit_account)}</td><td className="mono">{String(entry.credit_account)}</td><td className="mono">RM {Number(entry.amount_rm).toFixed(2)}</td><td>{String(entry.posted_by)}</td></tr>)}</tbody></table></div> : <div className="empty" style={{ marginTop: 16 }}>No financial entry was authorised for this case.</div>}
          </section>

          <section className="section panel panel-pad" aria-labelledby="letter-title">
            <div className="section-heading"><div><p className="eyebrow mono">Customer communication / Kernel linted</p><h2 id="letter-title" className="section-title">Released letter</h2></div><button className="btn ghost" type="button" disabled={exporting} onClick={() => void exportFmos()}>{exporting ? "Assembling…" : "Export FMOS pack"}</button></div>
            {message ? <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", marginTop: 18 }}>{String(message.payload.body || "Message body was not retained.")}</pre> : <div className="empty" style={{ marginTop: 16 }}>No message has been released.</div>}
          </section>
        </>
      )}
    </AppShell>
  );
}
