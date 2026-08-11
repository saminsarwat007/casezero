"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Guilloche } from "@/components/design/guilloche";
import { MicroRule } from "@/components/design/micro-rule";
import { supabase } from "@/lib/api";

export default function SetPasswordPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) return;
    let mounted = true;
    supabase.auth.getSession().then(({ data }) => { if (mounted) setReady(Boolean(data.session)); });
    const { data } = supabase.auth.onAuthStateChange((_event, session) => setReady(Boolean(session)));
    return () => { mounted = false; data.subscription.unsubscribe(); };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(null);
    if (password.length < 12) { setError("Use at least 12 characters."); return; }
    if (password !== confirm) { setError("Passwords do not match."); return; }
    if (!supabase) { setError("CaseZero authentication settings are missing."); return; }
    setBusy(true);
    const result = await supabase.auth.updateUser({ password });
    if (result.error) { setError(result.error.message); setBusy(false); return; }
    localStorage.removeItem("casezero_rehearsal");
    router.push("/simple"); router.refresh();
  }

  return (
    <main id="main-content" className="login-page">
      <Guilloche className="login-guilloche" />
      <section className="login-sheet" aria-labelledby="password-title">
        <div className="brand"><Link href="/" className="brand-word">CaseZero</Link><span className="brand-mark" aria-hidden="true" /></div>
        <div className="password-copy"><p className="eyebrow mono">Single-use staff invitation</p><h1 id="password-title" className="page-title password-title">Seal your operator account.</h1><p className="page-lede">Create a password for the work email your administrator invited. Your assigned role is already registered.</p></div>
        {!supabase ? <div className="error-box" role="alert">This deployment is missing Supabase public settings. Ask the deployment owner to configure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.</div> : !ready ? <div className="empty">This invitation session is missing or expired. Reopen the newest invitation email, or ask your CaseZero Admin to issue a fresh invitation.</div> : (
          <form className="login-form" onSubmit={submit}>
            <div className="field"><label htmlFor="new-password">New password</label><input className="input" id="new-password" name="new_password" type="password" autoComplete="new-password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} required /><p className="field-help">At least 12 characters. A password manager is recommended.</p></div>
            <div className="field"><label htmlFor="confirm-password">Confirm password</label><input className="input" id="confirm-password" name="confirm_password" type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required /></div>
            {error ? <div className="error-box" role="alert">{error}</div> : null}
            <button className="btn primary" type="submit" disabled={busy}>{busy ? "Sealing account…" : "Set password and open CaseZero"}</button>
          </form>
        )}
        <div style={{ marginTop: 28 }}><MicroRule /></div>
      </section>
    </main>
  );
}
