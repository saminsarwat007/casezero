"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Guilloche } from "@/components/design/guilloche";
import { MicroRule } from "@/components/design/micro-rule";
import { Stamp } from "@/components/design/stamp";
import { apiFetch, isRehearsal } from "@/lib/api";

type Alert = {
  token: string;
  txn_ref: string;
  amount_rm: number;
  merchant: string;
  occurred_at?: string;
  status: "PENDING" | "CONFIRMED" | "DISPUTED" | "EXPIRED";
  expires_at: string;
  bank_name: string;
};
type Response = { alert: Alert; accepted?: boolean; message?: string; case?: { status: string; outcome?: string; track_token?: string } };

const demo: Alert = {
  token: "demo-proactive-techworld-2026",
  txn_ref: "TXN20260718TECHWORLD",
  amount_rm: 2450,
  merchant: "TECHWORLD KL",
  occurred_at: "2026-07-18T03:02:00+08:00",
  status: "PENDING",
  expires_at: "2026-12-31T23:59:59+08:00",
  bank_name: "Demonstration Bank",
};

export default function ProactivePage() {
  const params = useParams<{ token: string }>();
  const [alert, setAlert] = useState<Alert | null>(null);
  const [result, setResult] = useState<Response | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rehearsal, setRehearsal] = useState(false);

  useEffect(() => {
    const offline = isRehearsal() || params.token === "demo";
    setRehearsal(offline);
    if (offline) setAlert(demo);
    else apiFetch<Alert>(`/proactive/${params.token}`).then(setAlert).catch((reason) => setError(reason instanceof Error ? reason.message : "Alert unavailable."));
  }, [params.token]);

  async function decide(confirmedNotMine: boolean) {
    if (!alert || busy) return;
    setBusy(true); setError(null);
    if (isRehearsal()) {
      window.setTimeout(() => {
        const next = { ...alert, status: confirmedNotMine ? "DISPUTED" as const : "CONFIRMED" as const };
        setAlert(next);
        setResult({ alert: next, accepted: confirmedNotMine, case: confirmedNotMine ? { status: "COMMUNICATED", outcome: "RESOLVED_IN_FULL", track_token: "demo" } : undefined });
        setBusy(false);
      }, 650);
      return;
    }
    try {
      const data = await apiFetch<Response>(`/proactive/${params.token}/respond`, {
        method: "POST",
        body: JSON.stringify({ confirmed_not_mine: confirmedNotMine }),
      });
      setAlert(data.alert); setResult(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "We could not record your answer.");
    } finally { setBusy(false); }
  }

  return (
    <main className="customer-page" id="main-content">
      <div className="phone-stage">
        <div className="phone-speaker" aria-hidden="true" />
        <div className="customer-sheet proactive-sheet">
          <header className="page-header" style={{ minHeight: 210 }}><Guilloche className="guilloche" /><div className="header-copy"><p className="eyebrow mono">{alert?.bank_name || "Your bank"} / security check</p><h1 className="page-title">Was this you?</h1><p className="page-lede">One answer can open a pre-filled dispute. No email, form, or phone call.</p></div></header><MicroRule />
          {rehearsal ? <div className="rehearsal-ribbon">OFFLINE REHEARSAL / NO BANK DATA CHANGES</div> : null}
          {error ? <div className="error-box section" role="alert">{error}</div> : null}
          {!alert ? <div className="skeleton section" role="status" aria-label="Loading transaction alert" /> : result?.case?.outcome === "RESOLVED_IN_FULL" ? (
            <section className="section panel panel-pad resolved-card">
              <Stamp>FINANCIALLY RESOLVED</Stamp>
              <p className="eyebrow" style={{ marginTop: 24 }}>Adjustment posted</p>
              <div className="metric-value mono">RM {Number(alert.amount_rm).toFixed(2)}</div>
              <p>Your dispute was filed with its transaction evidence and resolved through the governed pipeline.</p>
              <Link className="btn primary" href={`/track/${result.case.track_token || "demo"}`}>Open complaint tracker</Link>
            </section>
          ) : alert.status === "CONFIRMED" ? (
            <section className="section panel panel-pad"><Stamp>CONFIRMED</Stamp><h2 className="section-title" style={{ marginTop: 22 }}>No dispute was filed.</h2><p>Thank you. We recorded that the transaction was yours.</p></section>
          ) : (
            <>
              <section className="section panel panel-pad transaction-card">
                <p className="eyebrow mono">Flagged transaction / {alert.txn_ref}</p>
                <h2 className="section-title">{alert.merchant}</h2>
                <div className="metric-value mono">RM {Number(alert.amount_rm).toLocaleString("en-MY", { minimumFractionDigits: 2 })}</div>
                <dl className="fact-list"><div className="fact-row"><dt>Time</dt><dd className="mono">03:02 MYT</dd></div><div className="fact-row"><dt>Signal</dt><dd>Foreign-pattern amount spike</dd></div><div className="fact-row"><dt>Account</dt><dd className="mono">******1233</dd></div></dl>
              </section>
              <section className="proactive-actions" aria-label="Confirm transaction"><button className="btn ghost" type="button" disabled={busy} onClick={() => void decide(false)}>Yes, it was me</button><button className="btn danger" type="button" disabled={busy} onClick={() => void decide(true)}>{busy ? "Filing dispute…" : "Not me — dispute it"}</button></section>
              <p className="customer-footnote">Your answer is token-bound to this transaction. A dispute can only post money after core-bank verification returns PASS.</p>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
