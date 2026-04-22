import { useCallback, useEffect, useRef, useState } from "react";
import { getLeads } from "@/lib/api";
import type { EnrichedLead } from "@/lib/types";

const PAGE_SIZE = 20;

interface UseLeadsOptions {
  scoreMin?: number;
  action?: string;
  sortBy?: string;
  sortOrder?: string;
}

export function useLeads({ scoreMin = 0, action, sortBy = "processed_at", sortOrder = "desc" }: UseLeadsOptions = {}) {
  const [leads, setLeads] = useState<EnrichedLead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // cursors[0] = undefined (page 1), cursors[1] = cursor to reach page 2, etc.
  const cursors = useRef<(string | undefined)[]>([undefined]);

  const load = useCallback(async (targetPage: number) => {
    setLoading(true);
    setError(null);
    try {
      const cursor = cursors.current[targetPage - 1];
      const data = await getLeads({
        score_min: scoreMin,
        limit: PAGE_SIZE,
        cursor,
        page: targetPage,
        action: action || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      setLeads(data.leads);
      setTotal(data.total);
      setPage(targetPage);
      setHasNext(!!data.next_cursor);
      if (data.next_cursor && !cursors.current[targetPage]) {
        cursors.current[targetPage] = data.next_cursor;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load leads");
    } finally {
      setLoading(false);
    }
  }, [scoreMin, action, sortBy, sortOrder]);

  // Reset to page 1 when any filter/sort changes
  useEffect(() => {
    cursors.current = [undefined];
    setPage(1);
    load(1);
  }, [load]);

  const nextPage = useCallback(() => { if (hasNext) load(page + 1); }, [hasNext, load, page]);
  const prevPage = useCallback(() => { if (page > 1) load(page - 1); }, [load, page]);
  const refresh  = useCallback(() => { cursors.current = [undefined]; load(1); }, [load]);

  return { leads, total, page, hasNext, hasPrev: page > 1, loading, error, refresh, nextPage, prevPage };
}
