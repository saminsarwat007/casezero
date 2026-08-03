"use client";

import { AppShell } from "@/components/app-shell";
import { AgentTheater } from "@/components/agent-theater";
import { CaseCard } from "@/components/case-card";
import { PageHeader } from "@/components/page-header";
import { categoryLabel } from "@/components/case-register";
import { useCases } from "@/hooks/use-cases";
import { useAnalytics } from "@/hooks/use-operations";

const columns = [
  ["RECEIVED", ["RECEIVED"]],
  ["CLASSIFIED", ["CLASSIFIED"]],
  ["VERIFIED", ["VERIFIED", "REVIEW_PENDING"]],
  ["FINANCIALLY RESOLVED", ["FINANCIALLY_RESOLVED"]],
  ["COMMUNICATED", ["COMMUNICATED", "CLOSED"]],
] as const;

const volumes = [
  ["unauthorized_transaction", 35], ["billing_error", 22], ["mis_selling", 18],
  ["atm_debit_card", 12], ["insurance_takaful", 6], ["loan_financing", 5], ["emoney_digital", 2],
] as const;

export default function ProPage() {
  const { cases, loading, rehearsal } = useCases();
  const { data: analytics, error: analyticsError } = useAnalytics();
  const resolved = cases.filter((item) => ["COMMUNICATED", "FINANCIALLY_RESOLVED", "CLOSED"].includes(item.status)).length;
  const automation = Number(analytics?.metrics.automation_rate ?? (cases.length ? resolved / cases.length : 0)) * 100;
  const latestEval = analytics?.eval_runs[0];
  return (
    <AppShell>
      <PageHeader eyebrow="Pro mode / Pipeline observability" title="Every case leaves a mark." lede="Watch the agents propose, the kernel decide, and the signed ledger prove what moved." />
      {rehearsal ? <div className="panel panel-pad" style={{ marginTop: 18 }}><strong>Offline rehearsal</strong><div className="muted">The choreography below uses labelled synthetic events. Live mode streams the same event vocabulary from FastAPI SSE.</div></div> : null}
      <section className="section" aria-labelledby="pipeline-title">
        <div className="section-heading"><div><p className="eyebrow mono">Case pipeline / Spec vocabulary</p><h2 id="pipeline-title" className="section-title">Mission control</h2></div><span className="mono muted">{loading ? "—" : cases.length} CASES</span></div>
        <div className="pipeline">
          {columns.map(([label, statuses]) => {
            const items = cases.filter((item) => (statuses as readonly string[]).includes(item.status));
            return <div className="pipeline-column" key={label}><div className="pipeline-head"><strong>{label}</strong><span className="mono">{items.length.toString().padStart(2, "0")}</span></div>{items.map((item) => <CaseCard item={item} key={item.id} />)}</div>;
          })}
        </div>
      </section>
      <section className="section" aria-labelledby="theater-title">
        <div className="section-heading"><div><p className="eyebrow mono">The single inversion</p><h2 id="theater-title" className="section-title">Agent theater</h2></div><span className="mono muted">MCP / STDIO</span></div>
        <AgentTheater />
      </section>
      <section className="section" aria-labelledby="analytics-title">
        <div className="section-heading"><div><p className="eyebrow mono">Measured, not estimated</p><h2 id="analytics-title" className="section-title">Operations evidence</h2></div></div>
        <div className="analytics-grid">
          <div className="panel chart-panel">
            <p className="eyebrow">Category volume contract</p>
            <div className="category-bars">{volumes.map(([category, value]) => <div className="bar-row" key={category}><span>{categoryLabel(category)}</span><span className="bar-track"><span className="bar-fill" style={{ display: "block", width: `${value / 35 * 100}%` }} /></span><span className="mono">{value}%</span></div>)}</div>
          </div>
          <div className="panel chart-panel"><p className="eyebrow">Automation rate</p><div className="metric-value mono" style={{ marginTop: 50 }}>{automation.toFixed(1)}%</div><p className="muted">Target is measured against all received cases. Human-routed work is never counted as automated.</p></div>
          <div className="panel chart-panel"><p className="eyebrow">Investigator hours freed</p><div className="metric-value mono" style={{ marginTop: 50 }}>{(resolved * 1.5).toFixed(1)}</div><p className="muted">Auto-resolved cases × 90-minute baseline, shown as a visible arithmetic claim.</p></div>
        </div>
        {analyticsError ? <div className="error-box" style={{ marginTop: 12 }}>{analyticsError}</div> : null}
        <div className="metric-ledger panel" style={{ marginTop: 12 }} aria-label="Latest model evaluation">
          <div className="metric"><p className="eyebrow">Classification accuracy</p><div className="metric-value mono">{latestEval ? `${(Number(latestEval.accuracy) * 100).toFixed(2)}%` : "—"}</div><div className="metric-note">Gemini production classifier / {latestEval?.n_cases ?? 0} synthetic cases</div></div>
          <div className="metric"><p className="eyebrow">Processing latency</p><div className="metric-value mono" style={{ fontSize: "clamp(34px,4vw,58px)" }}>{latestEval ? `${(Number(latestEval.p50_ms) / 1000).toFixed(2)}s` : "—"}</div><div className="metric-note">P50 / P95 {(Number(latestEval?.p95_ms ?? 0) / 1000).toFixed(2)}s</div></div>
          <div className="metric"><p className="eyebrow">Measured model cost</p><div className="metric-value mono" style={{ fontSize: "clamp(34px,4vw,58px)" }}>RM {Number(latestEval?.cost_rm_per_case ?? 0).toFixed(6)}</div><div className="metric-note">Injection firewall {latestEval?.injection_caught ?? 0}/{latestEval?.injection_total ?? 0}</div></div>
        </div>
        <div className="panel chart-panel" style={{ marginTop: 12 }}><p className="eyebrow">Investigator workload distribution</p>{analytics?.investigator_workload.length ? analytics.investigator_workload.map((row) => <div className="fact-row" key={row.investigator}><span>{row.investigator}</span><strong className="mono">{row.assigned} ASSIGNED / {row.overdue} OVERDUE</strong></div>) : <div className="empty">No cases are currently assigned.</div>}</div>
      </section>
    </AppShell>
  );
}
