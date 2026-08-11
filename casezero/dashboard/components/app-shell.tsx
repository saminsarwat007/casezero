"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { Fragment, useEffect, useState } from "react";
import { apiFetch, isRehearsal } from "@/lib/api";
import { Role, useOperator } from "@/hooks/use-operator";

const WajarDocket = dynamic(
  () => import("@/components/wajar-docket").then((module) => module.WajarDocket),
  { ssr: false },
);

type NavItem = { label: string; href: string; mode?: string; roles?: readonly Role[] };
type NavGroup = { label: string; roles?: readonly Role[]; items: readonly NavItem[] };

/** Three groups of plain-language destinations, in the order a shift uses them.
 *
 * Simple and Pro both survive, but as the first two entries of Operations rather
 * than a second switch in the topbar: one mechanism, two modes, named for what
 * they show instead of what they are called internally.
 *
 * `roles` hides a page an operator cannot act on. That is a usability control,
 * not a security one — Postgres RLS and the per-endpoint `require()` checks are
 * what actually enforce a role. This only stops a complaints officer from
 * wading through four administrative screens to reach their queue.
 */
const NAV: readonly NavGroup[] = [
  {
    label: "Operations",
    items: [
      { label: "Today", href: "/simple", mode: "Simple" },
      { label: "Dashboard", href: "/pro", mode: "Pro" },
      { label: "Review queue", href: "/review" },
    ],
  },
  {
    label: "Compliance",
    roles: ["INVESTIGATOR", "COMPLIANCE", "ADMIN"],
    items: [
      { label: "Audit trail", href: "/audit" },
      { label: "Blocked intake", href: "/quarantine" },
      { label: "Fraud patterns", href: "/radar" },
    ],
  },
  {
    label: "Setup",
    roles: ["COMPLIANCE", "ADMIN"],
    items: [
      { label: "Rules", href: "/policy" },
      { label: "Operators", href: "/admin/users", roles: ["ADMIN"] },
      { label: "Settings", href: "/settings" },
    ],
  },
];

/** An unknown role sees only what every role may use, so nothing appears and
 *  then vanishes once `/me` answers. */
const allows = (roles: readonly Role[] | undefined, role: Role | null) =>
  !roles || (role !== null && roles.includes(role));

function visibleSections(role: Role | null) {
  let index = 0;
  return NAV.filter((group) => allows(group.roles, role))
    .map((group) => ({
      label: group.label,
      items: group.items
        .filter((item) => allows(item.roles, role))
        .map((item) => ({ ...item, index: String(++index).padStart(2, "0") })),
    }))
    .filter((group) => group.items.length > 0);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { operator, role } = useOperator();
  const [rehearsal, setRehearsal] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [bankName, setBankName] = useState("MYBank Berhad");
  const [today, setToday] = useState("");
  useEffect(() => {
    const offline = isRehearsal();
    setRehearsal(offline);
    if (!offline) apiFetch<{ settings: { bank_display_name: string } }>("/settings").then((data) => setBankName(data.settings.bank_display_name)).catch(() => undefined);
  }, []);
  // Read after mount: the server and the operator's machine can disagree on the day.
  useEffect(() => setToday(new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Kuala_Lumpur" }).format(new Date()).replaceAll("/", "·")), []);
  useEffect(() => setMenuOpen(false), [pathname]);
  const sections = visibleSections(role);
  const active = (href: string) => pathname.startsWith(href);

  return (
    <div className="app-shell">
      <aside className={clsx("side-rail", menuOpen && "menu-open")} aria-label="CaseZero navigation">
        <div className="rail-brand-row">
          <div className="brand">
            <Link href="/" className="brand-word">CaseZero</Link>
            <span className="brand-mark" aria-hidden="true" />
          </div>
          <button className={clsx("mobile-menu", menuOpen && "open")} type="button" onClick={() => setMenuOpen((current) => !current)} aria-label={`${menuOpen ? "Close" : "Open"} workspace menu`} aria-expanded={menuOpen} aria-controls="casezero-navigation"><span aria-hidden="true" /><span aria-hidden="true" /></button>
        </div>
        <nav className="rail-nav" id="casezero-navigation">
          {sections.map((group) => (
            <Fragment key={group.label}>
              <p className="nav-group-label mono">{group.label}</p>
              {group.items.map((item) => (
                <Link key={item.href} href={item.href} aria-current={active(item.href) ? "page" : undefined} className={clsx("nav-link", active(item.href) && "active")}>
                  <span className="nav-index mono">{item.index}</span>
                  <span>{item.label}{item.mode ? <em className="nav-mode mono">{item.mode}</em> : null}</span>
                </Link>
              ))}
            </Fragment>
          ))}
        </nav>
        <div className="rail-foot">
          <div className={clsx("connection", rehearsal && "rehearsal")}>
            {rehearsal ? "Synthetic rehearsal register" : "Governance services online"}
          </div>
          {operator ? <div className="rail-operator"><strong>{operator.full_name}</strong><span className="mono">{operator.role}</span></div> : null}
          <Link className="muted" href="/login" style={{ fontSize: 12 }}>Change operator</Link>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="top-meta mono">
            <span>{bankName}</span><span>{today || "—"}</span><span>MYT / UTC+8</span>
          </div>
        </header>
        <main id="main-content">{children}</main>
      </div>
      <WajarDocket />
    </div>
  );
}
