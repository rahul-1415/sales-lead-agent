"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { UploadForm } from "@/components/UploadForm";
import { JobStatusCard } from "@/components/JobStatusCard";
import { ProcessedJobCard } from "@/components/ProcessedJobCard";
import { LeadTable } from "@/components/LeadTable";
import { Analytics } from "@/components/Analytics";
import { useLeads } from "@/hooks/useLeads";
import { usePersistedJobs } from "@/hooks/usePersistedJobs";
import type { UploadResponse } from "@/lib/types";
import { Archive, ChevronDown, RefreshCw, SlidersHorizontal, Trash2 } from "lucide-react";
import { clearLeads, exportLeads } from "@/lib/api";
import { ConfirmDialog } from "@/components/ConfirmDialog";

const MIN_PROCESSING_MS = 2500;

export default function DashboardPage() {
  const [processingIds, setProcessingIds] = useState<string[]>([]);
  const [processingCounts, setProcessingCounts] = useState<Record<string, number>>({});
  const jobStartTimes = useRef<Record<string, number>>({});
  const [scoreMin, setScoreMin] = useState(0);
  const { leads, total, page, hasNext, hasPrev, loading, error, refresh, nextPage, prevPage } = useLeads(scoreMin);
  const { completedIds, addCompletedJob, clearCompletedJobs } = usePersistedJobs();
  const [clearing, setClearing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const [showClearDialog, setShowClearDialog] = useState(false);

  useEffect(() => {
    if (!showExportMenu) return;
    function handleClick(e: MouseEvent) {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setShowExportMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showExportMenu]);
  const [dupSummary, setDupSummary] = useState<string | null>(null);

  function onUploaded(res: UploadResponse) {
    jobStartTimes.current[res.job_id] = Date.now();
    setProcessingIds((prev) => [res.job_id, ...prev]);
    setProcessingCounts((prev) => ({ ...prev, [res.job_id]: res.lead_count }));
    setDupSummary(res.duplicate_count > 0
      ? `${res.lead_count - res.duplicate_count} lead${res.lead_count - res.duplicate_count !== 1 ? "s" : ""} processed, ${res.duplicate_count} duplicate${res.duplicate_count !== 1 ? "s" : ""} skipped.`
      : null
    );
    setTimeout(() => refresh(), 4000);
  }

  async function handleExport(format: "csv" | "ndjson" = "csv") {
    setExporting(true);
    setShowExportMenu(false);
    try {
      await exportLeads(scoreMin, format);
    } finally {
      setExporting(false);
    }
  }

  async function handleClearConfirmed() {
    setClearing(true);
    try {
      await clearLeads();
      refresh();
      setShowClearDialog(false);
    } finally {
      setClearing(false);
    }
  }

  async function handleDownloadAndDelete() {
    setClearing(true);
    try {
      await exportLeads(scoreMin, "csv");
      await clearLeads();
      refresh();
      setShowClearDialog(false);
    } finally {
      setClearing(false);
    }
  }

  const onJobComplete = useCallback((jobId: string) => {
    const elapsed = Date.now() - (jobStartTimes.current[jobId] ?? 0);
    const delay = Math.max(0, MIN_PROCESSING_MS - elapsed);
    setTimeout(() => {
      setProcessingIds((prev) => prev.filter((id) => id !== jobId));
      setProcessingCounts((prev) => { const next = { ...prev }; delete next[jobId]; return next; });
      delete jobStartTimes.current[jobId];
      addCompletedJob(jobId);
      refresh();
    }, delay);
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
        <UploadForm
          onUploaded={onUploaded}
          isProcessing={processingIds.length > 0}
          processingCount={processingIds.reduce((sum, id) => sum + (processingCounts[id] ?? 0), 0)}
        />
        {dupSummary && (
          <div className="mt-3 flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-700">
            <span>⚠️ {dupSummary}</span>
            <button
              onClick={() => setDupSummary(null)}
              className="ml-4 shrink-0 text-amber-500 hover:text-amber-800 transition-colors"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        )}
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
          <div className="grid gap-4 sm:grid-cols-2">
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
            Leads {total > 0 && <span className="normal-case font-normal text-gray-400">(showing: {leads.length} / {total})</span>}
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
            <div className="relative" ref={exportMenuRef}>
              <div className="flex items-stretch rounded-md border border-gray-200 bg-white text-sm text-gray-600 overflow-hidden">
                <button
                  onClick={() => handleExport("csv")}
                  disabled={exporting || total === 0}
                  className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                >
                  <Archive className="h-3.5 w-3.5" />
                  {exporting ? "Exporting…" : "Export CSV"}
                </button>
                <button
                  onClick={() => setShowExportMenu((v) => !v)}
                  disabled={exporting || total === 0}
                  className="px-1.5 border-l border-gray-200 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                  aria-label="More export options"
                >
                  <ChevronDown className="h-3.5 w-3.5" />
                </button>
              </div>
              {showExportMenu && (
                <div className="absolute right-0 z-20 mt-1 w-36 rounded-lg border border-gray-200 bg-white shadow-lg py-1">
                  <button
                    onClick={() => handleExport("csv")}
                    className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
                  >
                    Export CSV
                  </button>
                  <button
                    onClick={() => handleExport("ndjson")}
                    className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
                  >
                    Export NDJSON
                  </button>
                </div>
              )}
            </div>
            {total > 0 && (
              <button
                onClick={() => setShowClearDialog(true)}
                className="flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-sm text-red-500 hover:bg-red-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear
              </button>
            )}
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

        {/* Pagination controls — always visible when there are leads */}
        {total > 0 && (
          <div className="mt-4 flex items-center justify-between">
            <button
              onClick={prevPage}
              disabled={!hasPrev || loading}
              className="flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ← Previous
            </button>
            <span className="text-sm text-gray-400">Page {page}</span>
            <button
              onClick={nextPage}
              disabled={!hasNext || loading}
              className="flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next →
            </button>
          </div>
        )}
      </section>

      <ConfirmDialog
        open={showClearDialog}
        title="Delete all leads?"
        description={`This will permanently delete all ${total} lead${total !== 1 ? "s" : ""} from the system.`}
        warning="This action cannot be undone. All enrichment data, scores, and AI reasoning will be lost."
        confirmLabel="Delete all leads"
        loading={clearing}
        onConfirm={handleClearConfirmed}
        onCancel={() => setShowClearDialog(false)}
        onDownloadAndDelete={handleDownloadAndDelete}
      />
    </div>
  );
}
