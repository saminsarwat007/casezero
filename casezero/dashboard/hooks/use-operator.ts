"use client";

import { useEffect, useState } from "react";
import { apiFetch, isRehearsal } from "@/lib/api";

export type Role = "OPS" | "INVESTIGATOR" | "COMPLIANCE" | "ADMIN";

export type Operator = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
};

/** The offline rehearsal is a tour of the whole product, so it carries the widest
 *  role. Nothing is protected by narrowing it — the register is synthetic and makes
 *  no bank or model call — while narrowing it would hide the governance surfaces
 *  (rules, audit trail, blocked intake, operators) the tour exists to show. */
const REHEARSAL_OPERATOR: Operator = {
  id: "rehearsal",
  email: "ops@casezero.my",
  full_name: "Rehearsal operator",
  role: "ADMIN",
};

/** The signed-in operator, used to hide pages a role cannot act on.
 *
 * This is a usability control, not a security control: Postgres RLS and the
 * `require()` checks on each endpoint are what actually enforce the role. Hiding
 * an unusable page just stops a complaints officer from wading through four admin
 * screens to reach their queue.
 */
export function useOperator() {
  const [operator, setOperator] = useState<Operator | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    if (isRehearsal()) {
      setOperator(REHEARSAL_OPERATOR);
      setLoading(false);
      return;
    }
    apiFetch<Operator>("/me")
      .then((data) => {
        if (live) setOperator(data);
      })
      .catch(() => {
        if (live) setOperator(null);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);

  return { operator, role: operator?.role ?? null, loading };
}
