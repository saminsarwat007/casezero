import Link from "next/link";
import type { CaseRecord } from "@/lib/types";
import { StatusBadge } from "./status-badge";
import { SlaStrip } from "./design/sla-strip";

const labels: Record<string, string> = {
  unauthorized_transaction: "Unauthorised transaction",
  billing_error: "Billing error",
  mis_selling: "Mis-selling",
  atm_debit_card: "ATM / debit card",
  insurance_takaful: "Insurance / takaful",
  loan_financing: "Loan / financing",
  emoney_digital: "E-money / digital payment",
};

export const categoryLabel = (value?: string | null) => (value ? labels[value] ?? value.replaceAll("_", " ") : "Unclassified");

export function CaseRegister({ cases }: { cases: CaseRecord[] }) {
  if (!cases.length) return <div className="empty">No cases match this register. Change the filter or inject a complaint.</div>;
  return (
    <div className="register">
      {cases.map((item) => (
        <Link className="register-row" href={`/case/${item.case_ref}`} key={item.id}>
          <span className="mono" style={{ fontSize: 12 }}>{item.case_ref}</span>
          <span className="case-summary">
            <strong>{categoryLabel(item.category)}</strong>
            <span>{item.summary || "No summary recorded."}</span>
          </span>
          <span>
            <span className="mono" style={{ fontSize: 12 }}>{item.urgency || "—"} urgency</span>
            <SlaStrip urgency={item.urgency} elapsed={item.status === "COMMUNICATED" ? 2 : item.urgency === "High" ? 4 : 7} />
          </span>
          <StatusBadge status={item.status} />
        </Link>
      ))}
    </div>
  );
}
