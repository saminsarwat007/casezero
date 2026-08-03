"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { RefreshCcw, Upload } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CaseRegister } from "@/components/case-register";
import { PageHeader } from "@/components/page-header";
import { apiFetch, isRehearsal } from "@/lib/api";
import { useCases } from "@/hooks/use-cases";

export default function SimplePage() {
  const { cases, loading, error, refresh, rehearsal } = useCases();
  const input = useRef<HTMLInputElement>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tour, setTour] = useState(false);
  useEffect(() => setTour(localStorage.getItem("casezero_tour") === "1"), []);
  const resolved = cases.filter((item) => ["FINANCIALLY_RESOLVED", "COMMUNICATED", "CLOSED"].includes(item.status)).length;
  const attention = cases.filter((item) => ["REVIEW_PENDING", "VERIFIED", "QUARANTINED"].includes(item.status));

  async function inject(file?: File) {
    if (!file) return;
    if (isRehearsal()) { setNotice("Rehearsal mode does not write. Sign in to inject this message."); return; }
    setBusy(true); setNotice(null);
    try {
      const raw = await file.arrayBuffer();
      const result = await apiFetch<{ case_ref: string; status: string }>("/intake", {
        method: "POST", body: raw, headers: { "Content-Type": "message/rfc822" },
      });
      setNotice(`${result.case_ref} reached ${result.status.replaceAll("_", " ")}.`);
      await refresh();
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Intake failed.");
    } finally { setBusy(false); if (input.current) input.current.value = ""; }
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="Simple mode / Daily operating ledger"
        title="Only three cases need you."
        lede="Everything else has either resolved under policy or is moving within its working-day deadline."
        action={<button className="btn primary" onClick={() => input.current?.click()} disabled={busy}><Upload aria-hidden="true" size={17} strokeWidth={1.5} />{busy ? "Processing…" : "Inject .eml"}</button>}
      />
      {tour ? (
        <aside className="tour-note" aria-labelledby="tour-note-title">
          <div><p className="eyebrow mono">Stop 01 of 05 / Judge walkthrough</p><h2 id="tour-note-title" className="section-title">Start with the three cases that need a person.</h2><p>Then follow the numbered left rail: Mission control → Policy studio → Customer alert → Audit explorer.</p></div>
          <div className="tour-actions"><Link className="btn primary" href="/pro">Next: Mission control</Link><button className="btn ghost" type="button" onClick={() => { localStorage.removeItem("casezero_tour"); setTour(false); }}>Dismiss guide</button></div>
        </aside>
      ) : null}
      <input ref={input} hidden type="file" name="complaint_email" aria-label="Upload RFC822 complaint" accept=".eml,message/rfc822" onChange={(event) => void inject(event.target.files?.[0])} />
      {notice ? <div className={notice.includes("failed") ? "error-box" : "panel panel-pad"} role="status" style={{ marginTop: 18 }}>{notice}</div> : null}
      {error && !rehearsal ? <div className="error-box" role="alert" style={{ marginTop: 18 }}>{error} <button className="btn ghost" style={{ marginLeft: 12 }} onClick={() => void refresh()}><RefreshCcw aria-hidden="true" size={15} />Retry</button></div> : null}
      <section className="section" aria-labelledby="today-metrics">
        <h2 id="today-metrics" className="sr-only">Today&apos;s metrics</h2>
        <div className="metric-ledger panel">
          <div className="metric"><p className="eyebrow">Cases today</p><div className="metric-value mono">{loading ? "—" : cases.length}</div><div className="metric-note">Across all intake channels</div></div>
          <div className="metric"><p className="eyebrow">Auto-resolved</p><div className="metric-value mono">{loading ? "—" : resolved}</div><div className="metric-note">PASS + policy + signed ticket</div></div>
          <div className="metric"><p className="eyebrow">Need you</p><div className="metric-value mono">{loading ? "—" : attention.length}</div><div className="metric-note">Review, verify, or inspect quarantine</div></div>
        </div>
      </section>
      <section className="section" aria-labelledby="commands">
        <div className="section-heading"><div><p className="eyebrow mono">Natural-language operations</p><h2 id="commands" className="section-title">Ask without learning the system.</h2></div></div>
        <div className="chips">
          {[
            "Show cases at risk", "Open the review queue", "Summarise today", "Show quarantined input",
          ].map((label) => <button key={label} className="chip" onClick={() => setNotice(`${label} — ${attention.length} case(s) match the current register.`)}>{label}</button>)}
        </div>
      </section>
      <section className="section" aria-labelledby="needs-attention">
        <div className="section-heading"><div><p className="eyebrow mono">Needs attention / Ordered by SLA risk</p><h2 id="needs-attention" className="section-title">The human queue</h2></div><span className="mono muted">{attention.length.toString().padStart(2, "0")} OPEN</span></div>
        {loading ? <div className="skeleton" role="status" aria-label="Loading cases needing attention" /> : <CaseRegister cases={attention} />}
      </section>
      <section className="section" aria-labelledby="recent">
        <div className="section-heading"><div><p className="eyebrow mono">Complete register</p><h2 id="recent" className="section-title">Recent cases</h2></div></div>
        {loading ? <div className="skeleton" role="status" aria-label="Loading recent cases" /> : <CaseRegister cases={cases} />}
      </section>
    </AppShell>
  );
}
