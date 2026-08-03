"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Guilloche } from "@/components/design/guilloche";
import { MicroRule } from "@/components/design/micro-rule";
import { Stamp } from "@/components/design/stamp";
import { apiFetch, isRehearsal } from "@/lib/api";

type Tracker = { case_ref: string; status: string; category?: string; urgency?: string; sla_due?: string; outcome?: string; amount_rm?: number; timeline: Array<{ event_type: string }>; contact: string };
const rehearsal: Tracker = { case_ref: "MYB-2026-000012", status: "COMMUNICATED", category: "unauthorized_transaction", urgency: "High", sla_due: "2026-08-05T09:15:00+08:00", outcome: "RESOLVED_IN_FULL", amount_rm: 890, timeline: [{ event_type: "CASE_RECEIVED" }, { event_type: "CLASSIFIED" }, { event_type: "VERIFICATION_COMPLETED" }, { event_type: "JOURNAL_POSTED" }, { event_type: "MESSAGE_SENT" }], contact: "complaints@mybank.com.my" };

export default function TrackPage() {
  const params = useParams<{ token: string }>();
  const [data, setData] = useState<Tracker | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (isRehearsal() || params.token === "demo") setData(rehearsal); else apiFetch<Tracker>(`/track/${params.token}`).then(setData).catch((reason) => setError(reason instanceof Error ? reason.message : "Tracker unavailable.")); }, [params.token]);
  return (
    <main className="customer-page"><div className="customer-sheet">
      <header className="page-header" style={{ minHeight: 220 }}><Guilloche className="guilloche" /><div className="header-copy"><p className="eyebrow mono">MYBank complaint tracker</p><h1 className="page-title">{data?.case_ref || "Your case"}</h1><p className="page-lede">A quiet, current record of what has happened and when you should hear from us.</p></div></header><MicroRule />
      {error ? <div className="error-box section" role="alert">{error}</div> : null}
      {!data ? <div className="skeleton section" role="status" aria-label="Loading complaint tracker" /> : <>
        <section className="section panel panel-pad"><div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start" }}><div><p className="eyebrow">Current position</p><h2 className="section-title">{data.status.replaceAll("_", " ")}</h2><p className="muted">Expected response by {data.sla_due ? new Date(data.sla_due).toLocaleDateString("en-MY", { dateStyle: "long" }) : "the date in your letter"}.</p></div>{data.outcome === "RESOLVED_IN_FULL" ? <Stamp>FINANCIALLY RESOLVED</Stamp> : null}</div>{data.outcome === "RESOLVED_IN_FULL" ? <div className="panel panel-pad" style={{ marginTop: 20 }}><p className="eyebrow">Adjustment posted</p><div className="metric-value mono" style={{ fontSize: 46 }}>RM {Number(data.amount_rm || 0).toFixed(2)}</div><p>The money has been returned to the account on your complaint.</p></div> : null}</section>
        <section className="section"><p className="eyebrow mono">Working-day timeline</p><h2 className="section-title">What has happened</h2><div style={{ marginTop: 16 }}>{data.timeline.map((item, index) => <div className="tracker-line" key={`${item.event_type}-${index}`}><span className="tracker-dot done" /><div><strong>{item.event_type.replaceAll("_", " ")}</strong><p className="muted" style={{ margin: "3px 0 0" }}>{["Your complaint reached MYBank.", "The complaint type and deadline were assigned.", "Bank records were checked.", "An authorised adjustment was posted.", "Your decision letter was released."][index] || "Recorded on your case."}</p></div></div>)}</div></section>
        <section className="section panel panel-pad"><p className="eyebrow mono">Your rights</p><h2 className="section-title">If you remain dissatisfied</h2><p>You may refer the matter to the Financial Markets Ombudsman Service within six (6) months from the date of the final decision letter. Contact us at <strong>{data.contact}</strong> if you need the referral pack.</p></section>
      </>}
    </div></main>
  );
}
