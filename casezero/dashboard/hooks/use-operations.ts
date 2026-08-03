"use client";

import { useEffect, useState } from "react";
import { apiFetch, isRehearsal } from "@/lib/api";

export type EvalRun = {
  id?: string;
  n_cases: number;
  accuracy: number;
  urgency_accuracy: number;
  p50_ms: number;
  p95_ms: number;
  cost_rm_per_case: number;
  injection_caught: number;
  injection_total: number;
  notes?: string;
};
export type Analytics = {
  metrics: Record<string, number | string>;
  category_volumes: Array<{ category: string; n: number; share: number }>;
  investigator_workload: Array<{ investigator: string; assigned: number; overdue: number }>;
  eval_runs: EvalRun[];
};
export type FraudRing = {
  signal_type: string;
  signal_value: string;
  case_count: number;
  total_rm: number;
  account_nos: string[];
};

export const rehearsalAnalytics: Analytics = {
  metrics: { total_cases: 5, resolved: 1, automation_rate: 0.2, cost_per_case_rm: 0.008713, awaiting_human: 1, sla_breached: 0 },
  category_volumes: [],
  investigator_workload: [{ investigator: "Faizal Rahman", assigned: 2, overdue: 0 }],
  eval_runs: [{ n_cases: 200, accuracy: 0.959, urgency_accuracy: 0.9897, p50_ms: 2616, p95_ms: 4626, cost_rm_per_case: 0.001025, injection_caught: 5, injection_total: 5, notes: "evaluator=gemini-production-classifier" }],
};

export function useAnalytics() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (isRehearsal()) { setData(rehearsalAnalytics); return; }
    apiFetch<Analytics>("/analytics/overview").then(setData).catch((reason) => setError(reason instanceof Error ? reason.message : "Analytics unavailable."));
  }, []);
  return { data, error };
}

export function useFraudRings() {
  const fallback: FraudRing[] = [{ signal_type: "merchant + device", signal_value: "TECHWORLD KL / dev_a91f77c204", case_count: 8, total_rm: 18215, account_nos: ["******1233", "******8812", "******4455", "******9900", "******7788", "******5566", "******2233", "******6890"] }];
  const [items, setItems] = useState<FraudRing[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (isRehearsal()) { setItems(fallback); return; }
    apiFetch<{ items: FraudRing[] }>("/fraud/rings?min_cases=3").then((data) => setItems(data.items)).catch((reason) => setError(reason instanceof Error ? reason.message : "Fraud signals unavailable."));
  }, []);
  return { items, error };
}
