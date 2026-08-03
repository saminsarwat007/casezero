"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Stamp } from "@/components/design/stamp";
import { demoDetail } from "@/lib/demo-data";

export default function AuditPage() {
  const [tampered, setTampered] = useState(false);
  return (
    <AppShell>
      <PageHeader eyebrow="Audit explorer / Recomputed SHA-256" title="Trust the chain, not the screen." lede="The application cannot update or delete an audit event. A privileged-owner tamper breaks the next hash and names the exact sequence." />
      <div className="detail-grid section">
        <section className={`panel panel-pad ${tampered ? "void" : ""}`}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 14, alignItems: "start" }}><div><p className="eyebrow mono">MYB-2026-000012 / 13 links</p><h2 className="section-title">{tampered ? "Integrity failure at sequence 04" : "Complete chain verified"}</h2></div><Stamp endorse={tampered}>{tampered ? "VOID" : "VALID"}</Stamp></div>
          <ol className="timeline" style={{ marginTop: 18 }}>{demoDetail.events.map((event) => <li key={event.seq} style={tampered && event.seq === 4 ? { color: "var(--endorse)" } : undefined}><span className="timeline-seq mono">{String(event.seq).padStart(2, "0")}</span><div><strong>{event.event_type}</strong><div className="hash mono">{tampered && event.seq === 4 ? `BROKEN · expected 8a3f04… found e09c91…` : event.hash}</div></div></li>)}</ol>
        </section>
        <aside className="panel panel-pad">
          <p className="eyebrow mono">Demonstration control</p><h2 className="section-title">Simulate a table-owner tamper</h2>
          <p className="muted">This rehearsal changes only the visual proof state. The separate live integrity script performs the privileged SQL edit and restores the row.</p>
          <button className={`btn ${tampered ? "primary" : "danger"}`} onClick={() => setTampered((value) => !value)}>{tampered ? "Restore verified view" : "Tamper sequence 04"}</button>
          <div style={{ marginTop: 28 }}><p className="eyebrow mono">Controls in force</p>{["UPDATE revoked from service role", "DELETE revoked from service role", "Canonical JSON payload hashing", "Genesis + sequential link check"].map((item) => <div className="fact-row" key={item}><span>{item}</span><strong className="mono">ON</strong></div>)}</div>
        </aside>
      </div>
    </AppShell>
  );
}
