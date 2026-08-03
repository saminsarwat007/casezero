"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Guilloche } from "@/components/design/guilloche";
import { MicroRule } from "@/components/design/micro-rule";
import { Stamp } from "@/components/design/stamp";

const route = [
  ["01", "Take the shift", "See the cases that need a person, already ordered by deadline risk.", "/simple"],
  ["02", "Read the operation", "Move from pipeline state to measured quality, latency, cost, and workload.", "/pro"],
  ["03", "Ask Axiom", "Use plain language to summarise, navigate, verify evidence, or prepare a governed Admin action.", "/pro"],
  ["04", "Set the controls", "Change operational settings directly; send regulated rule changes through simulation and Compliance approval.", "/settings"],
  ["05", "Prove the record", "Recompute any case chain and package its evidence for review or FMOS escalation.", "/audit"],
] as const;

export default function Home() {
  const router = useRouter();

  function openWorkspace() {
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
          <p className="eyebrow mono">Complaint operations / Malaysia</p>
          <h1 id="welcome-title" className="welcome-title">The complaint arrives.<br />The clock starts here.</h1>
          <p className="welcome-lede">CaseZero turns email complaints into verified, policy-governed resolutions—with every model call, bank check, financial gate, letter, and deadline preserved as evidence.</p>
          <div className="welcome-actions">
            <button className="btn primary" type="button" onClick={openWorkspace}>Explore the operating workspace <span aria-hidden="true">↗</span></button>
            <a className="btn ghost" href="#guide">See the first-shift guide</a>
          </div>
          <p className="safe-path mono">SAFE REHEARSAL · SYNTHETIC CUSTOMER DATA · ZERO BANK WRITES</p>
        </div>
        <div className="welcome-seal" aria-label="Operating system summary">
          <div><Stamp>Stakeholder ready</Stamp><p className="seal-line">Axiom by CaseZero</p><p className="muted">The operating agent that must show its authority before it acts.</p></div>
          <dl className="seal-facts">
            <div><dt>Baseline</dt><dd>90 min / case</dd></div>
            <div><dt>Target</dt><dd>&lt; 05 min PASS</dd></div>
            <div><dt>Team</dt><dd>05 operators</dd></div>
          </dl>
        </div>
      </section>

      <MicroRule />

      <section id="guide" className="welcome-section" aria-labelledby="guide-title">
        <div className="welcome-section-head">
          <div><p className="eyebrow mono">A first shift, already arranged</p><h2 id="guide-title" className="section-title">Know what needs you. Trust what does not.</h2></div>
          <p className="muted">The workspace starts with decisions, not agent internals. Rehearsal mode keeps every action synthetic while preserving the real operating vocabulary.</p>
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
