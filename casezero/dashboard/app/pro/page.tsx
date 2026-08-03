"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { AgentTheater } from "@/components/agent-theater";
import { CaseCard } from "@/components/case-card";
import { PageHeader } from "@/components/page-header";
import { categoryLabel } from "@/components/case-register";
import { useCases } from "@/hooks/use-cases";
import { useAnalytics } from "@/hooks/use-operations";

const columns = [
  { key: "received", label: "RECEIVED", statuses: ["RECEIVED"] },
  { key: "classified", label: "CLASSIFIED", statuses: ["CLASSIFIED"] },
  { key: "verified", label: "VERIFIED", statuses: ["VERIFIED", "REVIEW_PENDING"] },
  { key: "resolved", label: "FINANCIALLY RESOLVED", statuses: ["FINANCIALLY_RESOLVED"] },
  { key: "communicated", label: "COMMUNICATED", statuses: ["COMMUNICATED", "CLOSED"] },
] as const;

const volumes = [
  ["unauthorized_transaction", 35], ["billing_error", 22], ["mis_selling", 18],
  ["atm_debit_card", 12], ["insurance_takaful", 6], ["loan_financing", 5], ["emoney_digital", 2],
] as const;

export default function ProPage() {
  const { cases, loading, rehearsal } = useCases();
  const { data: analytics, error: analyticsError } = useAnalytics();
  const [activeStage, setActiveStage] = useState<(typeof columns)[number]["key"]>("verified");
  const resolved = cases.filter((item) => ["COMMUNICATED", "FINANCIALLY_RESOLVED", "CLOSED"].includes(item.status)).length;
  const review = cases.filter((item) => ["REVIEW_PENDING", "VERIFIED", "QUARANTINED"].includes(item.status)).length;
  const now = new Date("2026-08-04T09:00:00+08:00").getTime();
  const atRisk = cases.filter((item) => item.sla_due && !["COMMUNICATED", "CLOSED", "QUARANTINED"].includes(item.status) && new Date(item.sla_due).getTime() - now <= 24 * 60 * 60 * 1000).length;
  const automation = Number(analytics?.metrics.automation_rate ?? (cases.length ? resolved / cases.length : 0)) * 100;
  const latestEval = analytics?.eval_runs[0];

  return (
    <AppShell>
      <PageHeader eyebrow="Pro / Operational pulse" title="See the pressure before it becomes a breach." lede="Read the queue by state, deadline, human load, and governing evidence. Wajar is always one command away, but never one gate ahead." action={<button className="btn primary" type="button" onClick={() => window.dispatchEvent(new CustomEvent("casezero:wajar", { detail: "Show cases at SLA risk" }))}>Ask Wajar about risk <span aria-hidden="true">↗</span></button>} />
      {rehearsal ? <div className="rehearsal-ribbon pro-ribbon">SYNTHETIC OPERATING PULSE · REAL CASE STATUSES, GATES, AND MEASUREMENT CONTRACTS</div> : null}

      <section className="section" aria-labelledby="pulse-title">
        <div className="section-heading"><div><p className="eyebrow mono">Right now / Decision layer</p><h2 id="pulse-title" className="section-title">Operational pulse</h2></div><span className="mono muted">{loading ? "—" : cases.length.toString().padStart(2, "0")} VISIBLE CASES</span></div>
        <div className="pulse-ledger">
          <div className={atRisk ? "pulse-cell intervention" : "pulse-cell"}><span className="pulse-index mono">01 / DEADLINE</span><strong className="mono">{loading ? "—" : atRisk}</strong><p>inside the 24-hour warning horizon</p></div>
          <div className="pulse-cell"><span className="pulse-index mono">02 / HUMAN</span><strong className="mono">{loading ? "—" : review}</strong><p>need verification, approval, or quarantine review</p></div>
          <div className="pulse-cell"><span className="pulse-index mono">03 / AUTONOMY</span><strong className="mono">{automation.toFixed(1)}%</strong><p>resolved under PASS and active category policy</p></div>
          <div className="pulse-cell"><span className="pulse-index mono">04 / TIME RETURNED</span><strong className="mono">{(resolved * 1.5).toFixed(1)}h</strong><p>resolved cases × the 90-minute manual baseline</p></div>
        </div>
      </section>

      <section className="section" aria-labelledby="pipeline-title">
        <div className="section-heading pipeline-heading"><div><p className="eyebrow mono">Continuous state / No hidden lane</p><h2 id="pipeline-title" className="section-title">Case movement</h2></div><p className="pipeline-hint mono">SELECT A STAGE ON MOBILE</p></div>
        <div className="stage-tabs" role="tablist" aria-label="Case pipeline stages">
          {columns.map((column) => {
            const count = cases.filter((item) => (column.statuses as readonly string[]).includes(item.status)).length;
            return <button type="button" role="tab" aria-selected={activeStage === column.key} key={column.key} className={activeStage === column.key ? "active" : ""} onClick={() => setActiveStage(column.key)}><span>{column.label}</span><strong className="mono">{count.toString().padStart(2, "0")}</strong></button>;
          })}
        </div>
        <div className="pipeline">
          {columns.map((column) => {
            const items = cases.filter((item) => (column.statuses as readonly string[]).includes(item.status));
            return <div className={`pipeline-column ${activeStage === column.key ? "active" : ""}`} key={column.key} role="tabpanel"><div className="pipeline-head"><strong>{column.label}</strong><span className="mono">{items.length.toString().padStart(2, "0")}</span></div>{items.length ? items.map((item) => <CaseCard item={item} key={item.id} />) : <div className="pipeline-empty">No case is waiting here.</div>}</div>;
          })}
        </div>
      </section>

      <details className="agent-disclosure section" open>
        <summary><div><p className="eyebrow mono">Under the docket / Technical evidence</p><h2 className="section-title">Agent theater</h2></div><span className="mono muted">SHOW / HIDE</span></summary>
        <AgentTheater />
      </details>

      <section className="section" aria-labelledby="analytics-title">
        <div className="section-heading"><div><p className="eyebrow mono">Measured, not estimated</p><h2 id="analytics-title" className="section-title">Operating evidence</h2></div><span className="mono muted">LATEST CONTROLLED EVAL</span></div>
        <div className="evidence-layout">
          <div className="panel chart-panel category-contract"><p className="eyebrow">Case Study 1 category contract</p><div className="category-bars">{volumes.map(([category, value]) => <div className="bar-row" key={category}><span>{categoryLabel(category)}</span><span className="bar-track"><span className="bar-fill" style={{ display: "block", width: `${value / 35 * 100}%` }} /></span><span className="mono">{value}%</span></div>)}</div></div>
          <div className="evidence-register">
            <div><p className="eyebrow">Classification accuracy</p><strong className="mono">{latestEval ? `${(Number(latestEval.accuracy) * 100).toFixed(2)}%` : "—"}</strong><span>Gemini production classifier / {latestEval?.n_cases ?? 0} synthetic cases</span></div>
            <div><p className="eyebrow">Processing latency</p><strong className="mono">{latestEval ? `${(Number(latestEval.p50_ms) / 1000).toFixed(2)}s` : "—"}</strong><span>P50 / P95 {(Number(latestEval?.p95_ms ?? 0) / 1000).toFixed(2)}s</span></div>
            <div><p className="eyebrow">Measured model cost</p><strong className="mono cost">RM {Number(latestEval?.cost_rm_per_case ?? 0).toFixed(6)}</strong><span>Injection firewall {latestEval?.injection_caught ?? 0}/{latestEval?.injection_total ?? 0}</span></div>
          </div>
        </div>
        {analyticsError ? <div className="error-box" style={{ marginTop: 12 }}>{analyticsError}</div> : null}
        <div className="workload-panel panel"><div><p className="eyebrow mono">People / Current distribution</p><h3 className="section-title">Investigator workload</h3></div><div>{analytics?.investigator_workload.length ? analytics.investigator_workload.map((row) => <div className="workload-row" key={row.investigator}><span>{row.investigator}</span><strong className="mono">{row.assigned} ASSIGNED</strong><em className={row.overdue ? "danger mono" : "mono"}>{row.overdue} OVERDUE</em></div>) : <div className="empty">No cases are currently assigned. Use Operators to invite the team, then assign review work.</div>}</div></div>
      </section>
    </AppShell>
  );
}
