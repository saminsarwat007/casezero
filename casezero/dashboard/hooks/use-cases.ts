"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, isRehearsal } from "@/lib/api";
import { demoCases } from "@/lib/demo-data";
import type { CaseRecord } from "@/lib/types";

export function useCases(status?: string) {
  const [cases, setCases] = useState<CaseRecord[]>(demoCases);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rehearsal, setRehearsal] = useState(false);

  const refresh = useCallback(async () => {
    if (isRehearsal()) {
      setRehearsal(true);
      setCases(status ? demoCases.filter((item) => item.status === status) : demoCases);
      setLoading(false);
      return;
    }
    try {
      const query = status ? `?status=${encodeURIComponent(status)}` : "";
      const data = await apiFetch<{ items: CaseRecord[] }>(`/cases${query}`);
      setCases(data.items);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Case register unavailable.");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { cases, loading, error, refresh, rehearsal };
}
