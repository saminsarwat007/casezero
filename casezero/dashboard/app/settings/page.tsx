"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { apiFetch, isRehearsal } from "@/lib/api";

type Controls = {
  bank_display_name: string;
  complaints_email: string;
  timezone: "Asia/Kuala_Lumpur" | "UTC";
  sla_warning_hours: number;
  default_workspace: "/simple" | "/pro";
  wajar_enabled: boolean;
  automatic_resolution_enabled: boolean;
  updated_at?: string;
};

const defaults: Controls = {
  bank_display_name: "MYBank Berhad", complaints_email: "complaints@mybank.com.my",
  timezone: "Asia/Kuala_Lumpur", sla_warning_hours: 24, default_workspace: "/simple",
  wajar_enabled: true, automatic_resolution_enabled: true,
};

export default function SettingsPage() {
  const [controls, setControls] = useState<Controls>(defaults);
  const [chain, setChain] = useState({ ok: true, links: 3 });
  const [rehearsal, setRehearsal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const offline = isRehearsal(); setRehearsal(offline);
    if (offline) { setLoading(false); return; }
    apiFetch<{ settings: Controls; chain: { ok: boolean; links: number } }>("/settings")
      .then((data) => { setControls(data.settings); setChain(data.chain); })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "The control register is unavailable."))
      .finally(() => setLoading(false));
  }, []);

  function change<K extends keyof Controls>(key: K, value: Controls[K]) { setControls((current) => ({ ...current, [key]: value })); setNotice(null); }

  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null); setNotice(null);
    try {
      if (rehearsal) {
        setChain((current) => ({ ok: true, links: current.links + 1 }));
        setNotice("Control change rehearsed. No live setting or bank process changed.");
      } else {
        const data = await apiFetch<{ settings: Controls; chain: { ok: boolean; links: number }; changed: string[] }>("/settings", { method: "PUT", body: JSON.stringify(controls) });
        setControls(data.settings); setChain(data.chain);
        setNotice(data.changed.length ? `Saved ${data.changed.length} control change${data.changed.length === 1 ? "" : "s"}.` : "The control register was already current.");
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Control changes were not saved."); }
    finally { setBusy(false); }
  }

  return (
    <AppShell>
      <PageHeader eyebrow="Admin / Stakeholder control register" title="Change the operation. Keep the controls visible." lede="These settings alter how CaseZero is presented, prioritised, and allowed to automate. Regulated category rules stay in Policy Studio, where replay and Compliance approval remain mandatory." />
      {rehearsal ? <div className="rehearsal-ribbon settings-ribbon">SYNTHETIC CONTROL REGISTER · SAVES PRODUCE A REHEARSAL RECEIPT ONLY</div> : null}

      <form className="settings-layout section" onSubmit={save}>
        <div className="settings-sheet panel">
          <div className="settings-sheet-head"><div><p className="eyebrow mono">Institution profile</p><h2 className="section-title">What operators see</h2></div><span className="status-badge">Admin write</span></div>
          <div className="settings-fields">
            <div className="field"><label htmlFor="bank-name">Bank display name</label><input className="input" id="bank-name" value={controls.bank_display_name} onChange={(event) => change("bank_display_name", event.target.value)} minLength={2} maxLength={120} required /><p className="field-help">Used in the workspace masthead and staff-facing documents.</p></div>
            <div className="field"><label htmlFor="complaints-email">Complaints contact email</label><input className="input" id="complaints-email" type="email" value={controls.complaints_email} onChange={(event) => change("complaints_email", event.target.value)} required /><p className="field-help">Printed on customer and FMOS communications. Inbox credentials remain deployment secrets.</p></div>
            <div className="settings-pair">
              <div className="field"><label htmlFor="timezone">Operating timezone</label><select className="select" id="timezone" value={controls.timezone} onChange={(event) => change("timezone", event.target.value as Controls["timezone"])}><option value="Asia/Kuala_Lumpur">Malaysia time · UTC+8</option><option value="UTC">UTC</option></select></div>
              <div className="field"><label htmlFor="default-workspace">Default workspace</label><select className="select" id="default-workspace" value={controls.default_workspace} onChange={(event) => change("default_workspace", event.target.value as Controls["default_workspace"])}><option value="/simple">Today · Simple</option><option value="/pro">Mission control · Pro</option></select></div>
            </div>
            <div className="field"><label htmlFor="warning-hours">SLA warning horizon</label><div className="unit-input"><input className="input" id="warning-hours" type="number" min={1} max={120} value={controls.sla_warning_hours} onChange={(event) => change("sla_warning_hours", Number(event.target.value))} /><span className="mono">HOURS</span></div><p className="field-help">Wajar and Mission Control surface open cases due inside this horizon. BNM working-day deadlines themselves do not change here.</p></div>
          </div>
        </div>

        <aside className="settings-controls">
          <div className="panel control-card">
            <p className="eyebrow mono">Authority switches</p><h2 className="section-title">What automation may do</h2>
            <label className="control-toggle"><span><strong>Wajar operating agent</strong><small>Allow signed-in staff to prepare read, navigation, and governed Admin actions.</small></span><input type="checkbox" checked={controls.wajar_enabled} onChange={(event) => change("wajar_enabled", event.target.checked)} /><i aria-hidden="true" /></label>
            <label className="control-toggle risk"><span><strong>Automatic financial resolution</strong><small>When off, otherwise eligible PASS cases stop at human review. It never expands a pack threshold.</small></span><input type="checkbox" checked={controls.automatic_resolution_enabled} onChange={(event) => change("automatic_resolution_enabled", event.target.checked)} /><i aria-hidden="true" /></label>
          </div>
          <div className="control-proof">
            <span className="mono">CONTROL CHAIN</span><strong>{chain.ok ? "VERIFIED" : "BROKEN"}</strong><small>{chain.links.toString().padStart(2, "0")} append-only change receipts</small>
          </div>
          {notice ? <div className="success-box" role="status">{notice}</div> : null}
          {error ? <div className="error-box" role="alert">{error}</div> : null}
          <button className="btn primary settings-save" type="submit" disabled={busy || loading}>{busy ? "Saving control…" : rehearsal ? "Rehearse control change" : "Save control register"}</button>
        </aside>
      </form>

      <section className="settings-boundary section" aria-labelledby="settings-boundary-title">
        <div><p className="eyebrow mono">Separated by design</p><h2 id="settings-boundary-title" className="section-title">Some changes need more than a setting.</h2></div>
        <div className="boundary-actions"><Link className="boundary-link" href="/policy"><span>Category thresholds, wording, SLA packs</span><strong>Open Policy Studio ↗</strong></Link><Link className="boundary-link" href="/admin/users"><span>Work emails and least-privilege roles</span><strong>Open Operators ↗</strong></Link></div>
      </section>
    </AppShell>
  );
}
