"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Guilloche } from "@/components/design/guilloche";
import { MicroRule } from "@/components/design/micro-rule";
import { apiFetch, supabase } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("ops@casezero.my");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    if (!supabase) {
      setError("Supabase public settings are missing. Add them to dashboard/.env.local.");
      setBusy(false); return;
    }
    const result = await supabase.auth.signInWithPassword({ email, password });
    if (result.error) { setError(result.error.message); setBusy(false); return; }
    localStorage.removeItem("casezero_rehearsal");
    let destination = "/simple";
    try {
      const controls = await apiFetch<{ settings: { default_workspace: "/simple" | "/pro" } }>("/settings");
      destination = controls.settings.default_workspace;
    } catch { /* Identity is valid; fall back to the calm daily view. */ }
    router.push(destination); router.refresh();
  }

  function rehearsal() {
    localStorage.setItem("casezero_rehearsal", "1");
    router.push("/simple");
  }

  return (
    <main className="login-page">
      <Guilloche className="login-guilloche" />
      <section className="login-sheet" aria-labelledby="login-title">
        <div className="brand"><span className="brand-word">CaseZero</span><span className="brand-mark" aria-hidden="true" /></div>
        <div style={{ marginTop: 46, position: "relative", zIndex: 2 }}>
          <p className="eyebrow mono">Authorised bank staff / controlled access</p>
          <h1 id="login-title" className="page-title" style={{ fontSize: 44 }}>Open the case register.</h1>
          <p className="page-lede">Your role is enforced by Postgres. Investigators see only the cases assigned to them.</p>
        </div>
        <form className="login-form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="email">Work email</label>
            <input className="input" id="email" name="email" type="email" autoComplete="username" spellCheck={false} value={email} onChange={(event) => setEmail(event.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input className="input" id="password" name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </div>
          {error ? <div className="error-box" role="alert">{error}</div> : null}
          <div className="login-actions">
            <button className="btn primary" type="submit" disabled={busy}>{busy ? "Verifying role…" : "Open live workspace"}</button>
            <button className="btn ghost" type="button" onClick={rehearsal}>Open offline rehearsal</button>
          </div>
          <p className="field-help">Rehearsal mode uses labelled synthetic data and makes no bank or model calls.</p>
        </form>
        <div className="invite-note">
          <strong>New colleague?</strong>
          <p>Your CaseZero Admin adds your work email in Operators. Open the invitation email once, set your password, then return here. New teams can explore the labelled rehearsal before live access is configured.</p>
          <Link href="/">Open the first-visit guide</Link>
        </div>
        <div style={{ marginTop: 28 }}><MicroRule /></div>
      </section>
    </main>
  );
}
