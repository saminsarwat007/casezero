"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { useEffect, useState } from "react";
import { apiFetch, isRehearsal } from "@/lib/api";

const WajarDocket = dynamic(
  () => import("@/components/wajar-docket").then((module) => module.WajarDocket),
  { ssr: false },
);

const nav = [
  ["00", "Start here", "/"],
  ["01", "Today", "/simple"],
  ["02", "Mission control", "/pro"],
  ["03", "Review queue", "/review"],
  ["04", "Policy studio", "/policy"],
  ["05", "Fraud radar", "/radar"],
  ["06", "Audit explorer", "/audit"],
  ["07", "Quarantine", "/quarantine"],
  ["08", "Customer alert", "/proactive/demo-proactive-techworld-2026"],
  ["09", "Operators", "/admin/users"],
  ["10", "Settings", "/settings"],
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [rehearsal, setRehearsal] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [bankName, setBankName] = useState("MYBank Berhad");
  useEffect(() => {
    const offline = isRehearsal();
    setRehearsal(offline);
    if (!offline) apiFetch<{ settings: { bank_display_name: string } }>("/settings").then((data) => setBankName(data.settings.bank_display_name)).catch(() => undefined);
  }, []);
  useEffect(() => setMenuOpen(false), [pathname]);
  const simple = pathname.startsWith("/simple");
  const active = (href: string) => href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div className="app-shell">
      <aside className={clsx("side-rail", menuOpen && "menu-open")} aria-label="CaseZero navigation">
        <div className="rail-brand-row">
          <div className="brand">
            <Link href="/" className="brand-word">CaseZero</Link>
            <span className="brand-mark" aria-hidden="true" />
          </div>
          <button className={clsx("mobile-menu", menuOpen && "open")} type="button" onClick={() => setMenuOpen((current) => !current)} aria-expanded={menuOpen} aria-controls="casezero-navigation"><span /><span /><span className="sr-only">{menuOpen ? "Close" : "Open"} workspace menu</span></button>
        </div>
        <nav className="rail-nav" id="casezero-navigation">
          {nav.map(([index, label, href]) => (
            <Link key={href} href={href} aria-current={active(href) ? "page" : undefined} className={clsx("nav-link", active(href) && "active")}>
              <span className="nav-index mono">{index}</span>
              <span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="rail-foot">
          <div className={clsx("connection", rehearsal && "rehearsal")}>
            {rehearsal ? "Synthetic rehearsal register" : "Governance services online"}
          </div>
          <Link className="muted" href="/login" style={{ fontSize: 12 }}>Change operator</Link>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="top-meta mono">
            <span>{bankName}</span><span>04·08·2026</span><span>MYT / UTC+8</span>
          </div>
          <div className="mode-switch" aria-label="Workspace mode">
            <Link href="/simple" className={clsx("mode-option", simple && "active")}>Simple</Link>
            <Link href="/pro" className={clsx("mode-option", !simple && pathname.startsWith("/pro") && "active")}>Pro</Link>
          </div>
        </header>
        <main id="main-content">{children}</main>
      </div>
      <WajarDocket />
    </div>
  );
}
