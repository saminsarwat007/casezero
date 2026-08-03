"use client";

import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Stamp } from "@/components/design/stamp";
import { useFraudRings } from "@/hooks/use-operations";

const positions = [
  [16, 18], [48, 12], [80, 20], [88, 68], [70, 86], [34, 84], [10, 62], [52, 90],
] as const;

export default function RadarPage() {
  const { items, error } = useFraudRings();
  const ring = items[0];
  const victims = (ring?.account_nos ?? []).map((account, index) => [...positions[index % positions.length], account] as const);
  return (
    <AppShell>
      <PageHeader eyebrow="Cross-case intelligence / Merchant + device signals" title="Eight ordinary cases. One organised pattern." lede="No single reviewer sees a ring. CaseZero correlates the merchant and device across accounts, then preserves the cases that prove it." />
      <div className="detail-grid section">
        {error ? <div className="error-box" role="alert">{error}</div> : null}
        <section className="radar-stage" aria-label="Fraud ring relationship map">
          <svg className="radar-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{victims.map(([x, y], index) => <line key={index} x1="50" y1="50" x2={x} y2={y} stroke="#526158" strokeWidth=".25" strokeDasharray="1 1" />)}</svg>
          <div className="radar-node core"><div><p className="eyebrow mono" style={{ color: "#97a59b" }}>{ring?.signal_type ?? "Merchant + device"}</p><strong>{ring?.signal_value?.split(" / ")[0] ?? "NO ACTIVE RING"}</strong><div className="mono" style={{ marginTop: 5, fontSize: 9 }}>{ring?.signal_value?.split(" / ")[1] ?? "waiting for cross-case signal"}</div></div></div>
          {victims.map(([x, y, account], index) => <div className="radar-node victim" key={account} style={{ left: `${x}%`, top: `${y}%` }}><div><span className="mono">{account}</span><div style={{ color: "#97a59b" }}>CASE {String(index + 1).padStart(2, "0")}</div></div></div>)}
        </section>
        <aside className="panel panel-pad">
          <p className="eyebrow mono">RING_ALERT / High severity</p><div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 10 }}><h2 className="section-title">Shared point-of-sale fingerprint</h2><Stamp endorse>ALERT</Stamp></div>
          <p>{ring ? `${ring.case_count} accounts share the ${ring.signal_type} signal ${ring.signal_value}. Cross-account spread makes coincidence unlikely.` : "The detector is waiting for at least three linked accounts."}</p>
          <dl className="fact-list"><div className="fact-row"><dt>Victim accounts</dt><dd className="mono">{String(ring?.case_count ?? 0).padStart(2, "0")}</dd></div><div className="fact-row"><dt>Total exposure</dt><dd className="mono">RM {Number(ring?.total_rm ?? 0).toLocaleString("en-MY", { minimumFractionDigits: 2 })}</dd></div><div className="fact-row"><dt>Signal types</dt><dd>{ring?.signal_type ?? "—"}</dd></div><div className="fact-row"><dt>Recommended action</dt><dd>Block and investigate signal</dd></div></dl>
          <Link className="btn primary" href="/audit" style={{ marginTop: 18 }}>Open evidence register</Link>
        </aside>
      </div>
    </AppShell>
  );
}
