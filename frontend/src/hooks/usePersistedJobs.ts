import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "sla:processed_jobs";

function readFromStorage(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function writeToStorage(ids: string[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch { /* ignore quota errors */ }
}

export function usePersistedJobs() {
  const [completedIds, setCompletedIds] = useState<string[]>([]);

  // Hydrate from localStorage after mount (avoids SSR mismatch)
  useEffect(() => {
    setCompletedIds(readFromStorage());
  }, []);

  const addCompletedJob = useCallback((jobId: string) => {
    setCompletedIds((prev) => {
      if (prev.includes(jobId)) return prev;
      const next = [jobId, ...prev];
      writeToStorage(next);
      return next;
    });
  }, []);

  const clearCompletedJobs = useCallback(() => {
    writeToStorage([]);
    setCompletedIds([]);
  }, []);

  return { completedIds, addCompletedJob, clearCompletedJobs };
}
