"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Stamp } from "@/components/design/stamp";
import { apiFetch, isRehearsal } from "@/lib/api";

type Impact = {
  corpus_cases: number;
  auto_resolution_rate_before: number;
  auto_resolution_rate_after: number;
  exposure_rm_before: number;
  exposure_rm_after: number;
  sla_breach_risk_before: number;
  sla_breach_risk_after: number;
  changed_case_refs: string[];
};
type Proposal = {
  id: string;
  status: "DRAFT" | "APPLIED" | "REJECTED";
  target_category: string;
  base_version: number;
  proposed_yaml: string;
  plain_english_diff: string;
  eval_impact: Impact;
  risk_flag?: string | null;
  chain?: { ok: boolean };
};

const example = "For billing errors under RM500, auto-resolve without dual control, but always notify the branch manager.";
const rehearsalProposal: Proposal = {
  id: "rehearsal-proposal",
  status: "DRAFT",
  target_category: "billing_error",
  base_version: 1,
  proposed_yaml: "resolution:\n  auto_approve_max_rm: 500\nworkflow:\n  notify_roles: [BRANCH_MANAGER]",
  plain_english_diff: "resolution.auto_approve_max_rm: 1000 → 500\nworkflow.notify_roles: None → ['BRANCH_MANAGER']",
  eval_impact: { corpus_cases: 44, auto_resolution_rate_before: 0.1364, auto_resolution_rate_after: 0.0682, exposure_rm_before: 1695, exposure_rm_after: 687.5, sla_breach_risk_before: 0.8, sla_breach_risk_after: 0.8, changed_case_refs: ["CZ-V1-071", "CZ-V1-078", "CZ-V1-085"] },
  risk_flag: null,
  chain: { ok: true },
};

const categories = [
  ["billing_error", "Billing error"], ["unauthorized_transaction", "Unauthorised transaction"],
  ["atm_debit_card", "ATM / debit card"], ["mis_selling", "Mis-selling"],
  ["insurance_takaful", "Insurance / takaful"], ["loan_financing", "Loan / financing"],
  ["emoney_digital", "E-money / digital payment"],
];

export default function PolicyPage() {
  const [request, setRequest] = useState(example);
  const [category, setCategory] = useState("billing_error");
  const [stage, setStage] = useState(1);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function compose() {
    setBusy(true); setNotice(null); setStage(2);
    if (isRehearsal()) {
      window.setTimeout(() => { setProposal({ ...rehearsalProposal, target_category: category }); setStage(3); setBusy(false); }, 300);
      return;
    }
    try {
      const row = await apiFetch<Proposal>("/policy/compose", { method: "POST", body: JSON.stringify({ category, request }) });
      setProposal(row); setStage(3);
    } catch (reason) { setStage(1); setNotice(reason instanceof Error ? reason.message : "Policy request refused."); }
    finally { setBusy(false); }
  }

  async function decide(action: "apply" | "reject") {
    if (!proposal || busy) return;
    setBusy(true); setNotice(null);
    if (isRehearsal()) {
      const status = action === "apply" ? "APPLIED" : "REJECTED";
      setProposal({ ...proposal, status }); setStage(4); setBusy(false);
      setNotice(`${status} in offline rehearsal. No live policy changed.`); return;
    }
    try {
      const row = await apiFetch<Proposal>(`/policy/proposals/${proposal.id}/${action}`, { method: "POST", body: JSON.stringify({ note: "Impact replay reviewed.", confirm_risk: Boolean(proposal.risk_flag) }) });
      setProposal(row); setStage(4); setNotice(`Policy proposal ${row.status.toLowerCase()} and hash-logged.`);
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Governance action failed."); }
    finally { setBusy(false); }
  }

  const impact = proposal?.eval_impact;
  const delta = impact ? (Number(impact.auto_resolution_rate_after) - Number(impact.auto_resolution_rate_before)) * 100 : 0;
  return (
    <AppShell>
      <PageHeader eyebrow="Policy studio / Compliance role required to apply" title="Reprogram policy in one sentence." lede="The model may propose a schema-valid change. It cannot remove disclosures, weaken FMOS, disable verification, or touch the hash chain." />
      {notice ? <div className="panel panel-pad" role="status" style={{ marginTop: 18 }}>{notice}</div> : null}
      <section className="section policy-flow" aria-label="Policy composer stages">
        {["Interpret", "Diff", "Simulate", "Govern"].map((label, index) => <div key={label} className={`policy-step ${stage === index + 1 ? "active" : ""}`}><p className="eyebrow mono" style={{ color: stage === index + 1 ? "inherit" : undefined }}>0{index + 1}</p><strong>{label}</strong></div>)}
      </section>
      <div className="detail-grid section">
        <form className="panel panel-pad" onSubmit={(event) => { event.preventDefault(); void compose(); }}>
          <p className="eyebrow mono">Natural-language request</p><h2 className="section-title">What should change?</h2>
          <div className="field" style={{ marginTop: 18 }}><label htmlFor="policy-category">Rule pack</label><select id="policy-category" name="category" autoComplete="off" className="input" value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></div>
          <div className="field" style={{ marginTop: 14 }}><label htmlFor="policy-request">Policy instruction</label><textarea id="policy-request" name="policy_request" autoComplete="off" className="textarea" value={request} minLength={8} required aria-describedby="policy-request-help" onChange={(event) => setRequest(event.target.value)} /><span id="policy-request-help" className="field-help">Protected policy paths are refused before simulation. Use at least 8 characters.</span></div>
          <button className="btn primary" type="submit" disabled={busy} style={{ marginTop: 14 }}>{busy ? "Running 200-case replay…" : "Interpret and simulate"}</button>
          <div style={{ marginTop: 28 }}><p className="eyebrow mono">Protected by construction</p>{["Mandatory BNM disclosures", "FMOS six-month window", "PASS-only money movement", "Hash-chain audit"].map((item) => <div className="fact-row" key={item}><span>{item}</span><strong className="mono">IMMUTABLE</strong></div>)}</div>
        </form>
        <aside className="panel panel-pad">
          <p className="eyebrow mono">Candidate / {proposal ? `${proposal.target_category} v${proposal.base_version} → v${proposal.base_version + 1}` : "waiting"}</p><h2 className="section-title">Plain-English diff</h2>
          {!proposal ? <div className="empty" style={{ marginTop: 16 }}>Interpret the request to produce a protected diff.</div> : <div style={{ marginTop: 16 }}>{proposal.plain_english_diff.split("\n").map((line) => <div className="diff-line" key={line}><span className="diff-sign">~</span><span>{line}</span></div>)}<details style={{ marginTop: 14 }}><summary className="btn ghost">View candidate YAML</summary><pre className="panel panel-pad mono" style={{ whiteSpace: "pre-wrap", fontSize: 10 }}>{proposal.proposed_yaml}</pre></details></div>}
          {impact ? <><p className="eyebrow mono" style={{ marginTop: 24 }}>{impact.corpus_cases}-case category replay / 200-case corpus</p><div className="simulation"><div className="sim-cell"><div className="mono case-amount">{delta >= 0 ? "+" : ""}{delta.toFixed(1)}%</div><span className="muted">Auto-resolution</span></div><div className="sim-cell"><div className="mono case-amount">{(Number(impact.sla_breach_risk_after) - Number(impact.sla_breach_risk_before)).toFixed(2)}</div><span className="muted">SLA risk added</span></div><div className="sim-cell"><div className="mono case-amount">{impact.changed_case_refs.length}</div><span className="muted">Cases changed</span></div></div><div className="fact-row"><span>Exposure before / after</span><strong className="mono">RM {Number(impact.exposure_rm_before).toFixed(2)} → RM {Number(impact.exposure_rm_after).toFixed(2)}</strong></div>{proposal.risk_flag ? <div className="error-box" role="alert">{proposal.risk_flag} / explicit confirmation required</div> : null}<div style={{ display: "flex", gap: 10, marginTop: 18, alignItems: "center" }}>{proposal.status === "APPLIED" ? <Stamp>APPLIED · V{proposal.base_version + 1}</Stamp> : proposal.status === "REJECTED" ? <Stamp endorse>REJECTED</Stamp> : <><button className="btn primary" type="button" disabled={busy} onClick={() => void decide("apply")}>Apply as Compliance</button><button className="btn ghost" type="button" disabled={busy} onClick={() => void decide("reject")}>Reject proposal</button></>}</div><p className="mono muted" style={{ fontSize: 9, marginTop: 14 }}>PROPOSAL CHAIN {proposal.chain?.ok ? "VERIFIED" : "PENDING"}</p></> : null}
        </aside>
      </div>
    </AppShell>
  );
}
