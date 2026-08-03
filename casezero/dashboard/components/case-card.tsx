import Link from "next/link";
import type { CaseRecord } from "@/lib/types";
import { StatusBadge } from "./status-badge";
import { SlaStrip } from "./design/sla-strip";
import { categoryLabel } from "./case-register";

export function CaseCard({ item }: { item: CaseRecord }) {
  return (
    <Link href={`/case/${item.case_ref}`} className="case-card">
      <div className="case-card-top">
        <span className="mono" style={{ fontSize: 10 }}>{item.case_ref}</span>
        <StatusBadge status={item.verification_result ?? item.status} />
      </div>
      <div>
        <div className="case-amount mono">RM {Number(item.amount_rm || 0).toLocaleString("en-MY", { minimumFractionDigits: 2 })}</div>
        <div className="muted" style={{ fontSize: 12 }}>{categoryLabel(item.category)}</div>
      </div>
      <SlaStrip urgency={item.urgency} elapsed={item.urgency === "High" ? 4 : 7} />
      <div className="case-meta"><span>{item.urgency || "—"}</span><span>{item.channel}</span></div>
    </Link>
  );
}
