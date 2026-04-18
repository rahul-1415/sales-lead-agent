import { useCallback, useEffect, useState } from "react";
import { getLeads } from "@/lib/api";
import type { EnrichedLead } from "@/lib/types";

export function useLeads(scoreMin: number = 0, limit: number = 20) {
  const [leads, setLeads] = useState<EnrichedLead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getLeads({ score_min: scoreMin, limit });
      setLeads(data.leads);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load leads");
    } finally {
      setLoading(false);
    }
  }, [scoreMin, limit]);

  useEffect(() => { load(); }, [load]);

  return { leads, total, loading, error, refresh: load };
}
