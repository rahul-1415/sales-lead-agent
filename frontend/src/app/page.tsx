"use client";

import { useCallback, useState } from "react";
import { UploadForm } from "@/components/UploadForm";
import { JobStatusCard } from "@/components/JobStatusCard";
import { ProcessedJobCard } from "@/components/ProcessedJobCard";
import { LeadTable } from "@/components/LeadTable";
import { Analytics } from "@/components/Analytics";
import { useLeads } from "@/hooks/useLeads";
import { usePersistedJobs } from "@/hooks/usePersistedJobs";
import type { UploadResponse } from "@/lib/types";
import { RefreshCw, SlidersHorizontal, Trash2 } from "lucide-react";

export default function DashboardPage() {
  const [processingIds, setProcessingIds] = useState<string[]>([]);
  const [scoreMin, setScoreMin] = useState(0);
  const { leads, total, loading, error, refresh } = useLeads(scoreMin);
  const { completedIds, addCompletedJob, clearCompletedJobs } = usePersistedJobs();

  function onUploaded(res: UploadResponse) {
    setProcessingIds((prev) => [res.job_id, ...prev]);
    setTimeout(() => refresh(), 4000);
  }

  const onJobComplete = useCallback((jobId: string) => {
    setProcessingIds((prev) => prev.filter((id) => id !== jobId));
    addCompletedJob(jobId);
    refresh();
  }, [addCompletedJob, refresh]);

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Lead Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload a CSV or JSON file to enrich and score your leads with AI.
        </p>
      </div>

      {/* Upload */}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Upload Leads
        </h2>
        <UploadForm onUploaded={onUploaded} />
      </section>

      {/* Processing jobs */}
      {processingIds.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Processing Jobs
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {processingIds.map((id) => (
              <JobStatusCard key={id} jobId={id} onComplete={onJobComplete} />
            ))}
          </div>
        </section>
      )}

      {/* Processed jobs — persisted in localStorage */}
      {completedIds.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Processed Jobs{" "}
              <span className="normal-case font-normal text-gray-400">({completedIds.length})</span>
            </h2>
            <button
              onClick={clearCompletedJobs}
              className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-500 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear history
            </button>
          </div>
          <div className="space-y-2">
            {completedIds.map((id) => (
              <ProcessedJobCard key={id} jobId={id} />
            ))}
          </div>
        </section>
      )}

      {/* Analytics */}
      {leads.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Analytics
          </h2>
          <Analytics leads={leads} />
        </section>
      )}

      {/* Lead feed */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            Leads {total > 0 && <span className="normal-case font-normal text-gray-400">({total})</span>}
          </h2>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <SlidersHorizontal className="h-4 w-4" />
              <label htmlFor="score-filter">Min score</label>
              <select
                id="score-filter"
                value={scoreMin}
                onChange={(e) => setScoreMin(Number(e.target.value))}
                className="rounded-md border border-gray-200 bg-white px-2 py-1 text-sm"
              >
                {[0, 0.25, 0.5, 0.75].map((v) => (
                  <option key={v} value={v}>{Math.round(v * 100)}%</option>
                ))}
              </select>
            </div>
            <button
              onClick={refresh}
              className="flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 mb-3">
            {error}
          </div>
        )}

        <LeadTable leads={leads} loading={loading} />
      </section>
    </div>
  );
}
