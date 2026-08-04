"use client";

import Link from "next/link";
import { Guilloche } from "@/components/design/guilloche";
import { MicroRule } from "@/components/design/micro-rule";
import { Stamp } from "@/components/design/stamp";

const route = [
  ["01", "Run one complaint", "Axiom provisions a fresh sanitized transaction and executes the deployed pipeline.", "/live"],
  ["02", "Read the receipts", "See actual model calls, MCP evidence, the financial gate, balanced posting, and the chain hash.", "/live"],
  ["03", "Enter operations", "Staff sign in to work the queue, invite colleagues, change controls, and handle human-review cases.", "/login"],
] as const;

export default function Home() {
  function markRehearsal() {
    localStorage.setItem("casezero_rehearsal", "1");
    localStorage.setItem("casezero_tour", "1");
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
          <p className="eyebrow mono">Complaint operations / Malaysia</p>
          <h1 id="welcome-title" className="welcome-title">The complaint arrives.<br />Watch Axiom prove every action.</h1>
          <p className="welcome-lede">Run one complaint through the live stack first. Then enter the operating workspace only when you understand the evidence, authority, and outcome.</p>
          <div className="welcome-actions">
            <Link className="btn primary" href="/live">Run a Live Complaint <span aria-hidden="true">↗</span></Link>
            <Link className="btn ghost" href="/simple?tour=1" onClick={markRehearsal}>Explore the Operations Workspace</Link>
          </div>
          <p className="safe-path mono">SYNTHETIC CUSTOMER · LIVE MODEL + MCP + SUPABASE + JOURNAL</p>
        </div>
        <div className="welcome-seal" aria-label="Operating system summary">
          <div><Stamp>Stakeholder ready</Stamp><p className="seal-line">Axiom by CaseZero</p><p className="muted">The operating agent that must show its authority before it acts.</p></div>
          <dl className="seal-facts"><div><dt>Input</dt><dd>Synthetic</dd></div><div><dt>Execution</dt><dd>Live</dd></div><div><dt>Proof</dt><dd>Fresh + hashed</dd></div></dl>
        </div>
      </section>

      <MicroRule />

      <section id="guide" className="welcome-section" aria-labelledby="guide-title">
        <div className="welcome-section-head">
          <div><p className="eyebrow mono">One path / no mode decision</p><h2 id="guide-title" className="section-title">See it work. Verify it. Then operate it.</h2></div>
          <p className="muted">The public path has one job: prove a fresh case. Simple and Pro remain inside the staff workspace, where they belong.</p>
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
          <p className="eyebrow mono">Bring the operating team in</p>
          <h2 id="access-title" className="section-title">One work email. One role. No shared access.</h2>
          <p className="muted">An Admin invites each colleague once. Supabase establishes the identity; Postgres row-level security decides which cases and controls that person can see.</p>
          <Link className="btn ghost" href="/login">Sign in with a work email</Link>
        </div>
        <ol className="access-steps">
          <li><span className="mono">A</span><div><strong>Admin enters a work email</strong><p>Public registration stays closed; no team shares a password.</p></div></li>
          <li><span className="mono">B</span><div><strong>The colleague accepts once</strong><p>The single-use link lands on CaseZero&apos;s password setup page.</p></div></li>
          <li><span className="mono">C</span><div><strong>The database enforces the role</strong><p>OPS, Investigator, Compliance, and Admin access remain distinct on every request.</p></div></li>
        </ol>
      </section>

      <footer className="welcome-foot mono">CASEZERO · AXIOM OPERATING AGENT · BUILT FOR MALAYSIAN BANK COMPLAINT OPERATIONS</footer>
    </main>
  );
}
