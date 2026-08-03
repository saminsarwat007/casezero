"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Guilloche } from "@/components/design/guilloche";
import { MicroRule } from "@/components/design/micro-rule";
import { Stamp } from "@/components/design/stamp";

const route = [
  ["01", "Today", "See the operating ledger and the three cases that need a person.", "/simple"],
  ["02", "Mission control", "Watch the eight-agent pipeline, measured quality, latency, and cost.", "/pro"],
  ["03", "Policy studio", "Change a rule in plain language, replay it, and exercise the approval gate.", "/policy"],
  ["04", "Customer alert", "Dispute a synthetic transaction and watch it resolve end to end.", "/proactive/demo-proactive-techworld-2026"],
  ["05", "Audit explorer", "Tamper with sequence 04 and see the hash chain identify the break.", "/audit"],
] as const;

export default function Home() {
  const router = useRouter();

  function openWalkthrough() {
    localStorage.setItem("casezero_rehearsal", "1");
    localStorage.setItem("casezero_tour", "1");
    router.push("/simple?tour=1");
  }

  return (
    <main id="main-content" className="welcome-page">
      <header className="welcome-masthead">
        <Link href="/" className="brand" aria-label="CaseZero home">
          <span className="brand-word">CaseZero</span><span className="brand-mark" aria-hidden="true" />
        </Link>
        <Link className="btn ghost" href="/login">Staff sign in</Link>
      </header>

      <section className="welcome-hero" aria-labelledby="welcome-title">
        <Guilloche className="welcome-guilloche" />
        <div className="welcome-copy">
          <p className="eyebrow mono">First visit / Guided evidence route</p>
          <h1 id="welcome-title" className="welcome-title">Resolve the dispute.<br />Prove every step.</h1>
          <p className="welcome-lede">CaseZero is an agentic bank-complaint operating system. Start with a safe, fully labelled walkthrough—no login, no real customer data, and no bank writes.</p>
          <div className="welcome-actions">
            <button className="btn primary" type="button" onClick={openWalkthrough}>Open judge walkthrough</button>
            <a className="btn ghost" href="#guide">Read the 5-minute guide</a>
          </div>
          <p className="safe-path mono">SYNTHETIC DATA · ZERO EXTERNAL WRITES · RESET BY REFRESH</p>
        </div>
        <div className="welcome-seal" aria-label="Walkthrough status">
          <Stamp>Judge ready</Stamp>
          <dl className="seal-facts">
            <div><dt>Route</dt><dd>05 stops</dd></div>
            <div><dt>Time</dt><dd>05 minutes</dd></div>
            <div><dt>Access</dt><dd>No account</dd></div>
          </dl>
        </div>
      </section>

      <MicroRule />

      <section id="guide" className="welcome-section" aria-labelledby="guide-title">
        <div className="welcome-section-head">
          <div><p className="eyebrow mono">Recommended judging route</p><h2 id="guide-title" className="section-title">Five stops tell the whole story.</h2></div>
          <p className="muted">The numbered route stays available in the left rail. Every destructive-looking action is a rehearsal.</p>
        </div>
        <ol className="guide-route">
          {route.map(([index, title, description, href]) => (
            <li key={href}>
              <span className="guide-index mono">{index}</span>
              <div><h3>{title}</h3><p>{description}</p></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="access-ledger" aria-labelledby="access-title">
        <div className="access-intro">
          <p className="eyebrow mono">For real operators</p>
          <h2 id="access-title" className="section-title">Work email access is invitation-only.</h2>
          <p className="muted">A CaseZero administrator adds a colleague from Operators. Supabase emails a one-time invitation, the colleague sets a password, and their assigned role drives Postgres row-level security.</p>
          <Link className="btn ghost" href="/login">I already have an invitation</Link>
        </div>
        <ol className="access-steps">
          <li><span className="mono">A</span><div><strong>Admin enters the work email</strong><p>No shared credentials and no public registration form.</p></div></li>
          <li><span className="mono">B</span><div><strong>Recipient opens the secure email</strong><p>The single-use link lands on CaseZero&apos;s password setup page.</p></div></li>
          <li><span className="mono">C</span><div><strong>Database enforces the role</strong><p>OPS, Investigator, Compliance, or Admin permissions apply on every request.</p></div></li>
        </ol>
      </section>

      <footer className="welcome-foot mono">MYBANK BERHAD · CASEZERO EVIDENCE WORKSPACE · AUGUST 2026</footer>
    </main>
  );
}
