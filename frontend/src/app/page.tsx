"use client";

import { useState } from "react";
import { UploadForm } from "@/components/UploadForm";
import { JobStatusCard } from "@/components/JobStatusCard";
import { LeadTable } from "@/components/LeadTable";
import { Analytics } from "@/components/Analytics";
import { useLeads } from "@/hooks/useLeads";
import type { UploadResponse } from "@/lib/types";
import { RefreshCw, SlidersHorizontal } from "lucide-react";

export default function DashboardPage() {
  const [activeJobIds, setActiveJobIds] = useState<string[]>([]);
  const [scoreMin, setScoreMin] = useState(0);
  const { leads, total, loading, error, refresh } = useLeads(scoreMin);

  function onUploaded(res: UploadResponse) {
    setActiveJobIds((prev) => [res.job_id, ...prev]);
    // Refresh the lead table after a short delay to pick up new results
    setTimeout(() => refresh(), 4000);
  }

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

      {/* Active jobs */}
      {activeJobIds.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Processing Jobs
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {activeJobIds.slice(0, 4).map((id) => (
              <JobStatusCard key={id} jobId={id} />
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
            {/* Score filter */}
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
