"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { apiFetch, isRehearsal } from "@/lib/api";

type Staff = {
  id?: string;
  email: string;
  full_name: string;
  role: "OPS" | "INVESTIGATOR" | "COMPLIANCE" | "ADMIN";
  created_at?: string;
  invitation?: string;
};

const rehearsalStaff: Staff[] = [
  { id: "r-admin", email: "ravi.kumaran@mybank.example", full_name: "Ravi Kumaran", role: "ADMIN", invitation: "ACTIVE" },
  { id: "r-ops", email: "amina.rahman@mybank.example", full_name: "Amina Rahman", role: "OPS", invitation: "ACTIVE" },
  { id: "r-compliance", email: "mei.tan@mybank.example", full_name: "Mei Ling Tan", role: "COMPLIANCE", invitation: "ACTIVE" },
];

const roleHelp = {
  OPS: "Run intake and day-to-day case operations.",
  INVESTIGATOR: "See and decide only assigned cases.",
  COMPLIANCE: "Review evidence and approve policy changes.",
  ADMIN: "Invite staff and manage every CaseZero role.",
};

export default function OperatorsPage() {
  const [staff, setStaff] = useState<Staff[]>([]);
  const [rehearsal, setRehearsal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<Staff["role"]>("OPS");

  useEffect(() => {
    const offline = isRehearsal();
    setRehearsal(offline);
    if (offline) {
      setStaff(rehearsalStaff);
      setLoading(false);
      return;
    }
    apiFetch<{ items: Staff[] }>("/admin/users")
      .then((result) => setStaff(result.items))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load operators."))
      .finally(() => setLoading(false));
  }, []);

  async function invite(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null); setNotice(null);
    const entry: Staff = { email: email.trim().toLowerCase(), full_name: fullName.trim(), role };
    try {
      if (rehearsal) {
        setStaff((current) => [...current, { ...entry, id: `rehearsal-${current.length}`, invitation: "REHEARSED" }]);
        setNotice(`Invitation rehearsed for ${entry.email}. No email was sent.`);
      } else {
        const invited = await apiFetch<Staff>("/admin/users/invite", { method: "POST", body: JSON.stringify(entry) });
        setStaff((current) => [...current, invited]);
        setNotice(`Secure invitation sent to ${invited.email}.`);
      }
      setEmail(""); setFullName(""); setRole("OPS");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Invitation failed.");
    } finally { setBusy(false); }
  }

  return (
    <AppShell>
      <PageHeader eyebrow="Admin / Identity register" title="Invite work emails. Assign least privilege." lede="Public sign-up is disabled. Every colleague enters through a single-use Supabase invitation and a role enforced by Postgres RLS." />

      <section className="stakeholder-access-note" aria-labelledby="stakeholder-access-title">
        <div><p className="eyebrow mono">New team access</p><h2 id="stakeholder-access-title" className="section-title">Rehearsal first. Work email when ready.</h2><p>Stakeholders can learn the workspace with synthetic data, then each live operator accepts a single-use invitation tied to a least-privilege role.</p></div>
        <Link className="btn ghost" href="/">Preview stakeholder onboarding</Link>
      </section>

      <section className="operators-grid section" aria-labelledby="invite-title">
        <form className="panel panel-pad invite-form" onSubmit={invite}>
          <div><p className="eyebrow mono">Invitation register</p><h2 id="invite-title" className="section-title">Add a colleague</h2></div>
          <div className="field"><label htmlFor="full-name">Full name</label><input className="input" id="full-name" autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} required /></div>
          <div className="field"><label htmlFor="invite-email">Work email</label><input className="input" id="invite-email" type="email" autoComplete="email" spellCheck={false} value={email} onChange={(event) => setEmail(event.target.value)} required /></div>
          <div className="field"><label htmlFor="invite-role">CaseZero role</label><select className="select" id="invite-role" value={role} onChange={(event) => setRole(event.target.value as Staff["role"])}>{Object.keys(roleHelp).map((name) => <option key={name}>{name}</option>)}</select><p className="field-help">{roleHelp[role]}</p></div>
          {notice ? <div className="success-box" role="status">{notice}</div> : null}
          {error ? <div className="error-box" role="alert">{error}</div> : null}
          <button className="btn primary" type="submit" disabled={busy}>{busy ? "Registering…" : rehearsal ? "Rehearse invitation" : "Send secure invitation"}</button>
          <p className="field-help">{rehearsal ? "Rehearsal mode never sends email or creates a user." : "The recipient gets one email linking to CaseZero password setup."}</p>
        </form>

        <div className="operator-register">
          <div className="section-heading"><div><p className="eyebrow mono">Current access register</p><h2 className="section-title">Operators</h2></div><span className="mono muted">{staff.length.toString().padStart(2, "0")} PEOPLE</span></div>
          {loading ? <div className="skeleton" role="status" aria-label="Loading operator register" /> : null}
          {!loading && !staff.length && !error ? <div className="empty">No operators are registered.</div> : null}
          {staff.length ? <div className="table-wrap"><table className="data-table operator-table"><thead><tr><th>Person</th><th>Role</th><th>Invitation</th></tr></thead><tbody>{staff.map((person) => <tr key={person.id ?? person.email}><td><strong>{person.full_name}</strong><span className="operator-email">{person.email}</span></td><td><span className="status-badge">{person.role}</span></td><td className="mono">{person.invitation ?? "ACTIVE"}</td></tr>)}</tbody></table></div> : null}
        </div>
      </section>
    </AppShell>
  );
}
