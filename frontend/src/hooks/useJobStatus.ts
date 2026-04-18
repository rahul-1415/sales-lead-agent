import { useCallback, useEffect, useRef, useState } from "react";
import { getJobStatus } from "@/lib/api";
import type { JobStatusResponse } from "@/lib/types";

const POLL_INTERVAL_MS = 3000;

export function useJobStatus(jobId: string | null) {
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetch = useCallback(async (id: string) => {
    try {
      const data = await getJobStatus(id);
      setJob(data);
      setError(null);
      // Keep polling while the job is still active
      if (data.status === "pending" || data.status === "processing") {
        timerRef.current = setTimeout(() => fetch(id), POLL_INTERVAL_MS);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch job status");
    }
  }, []);

  useEffect(() => {
    if (!jobId) return;
    fetch(jobId);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [jobId, fetch]);

  return { job, error };
}
