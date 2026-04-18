"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useJobStatus } from "@/hooks/useJobStatus";
import { getDownloadUrl } from "@/lib/api";
import { useState } from "react";
import { ArrowLeft, Download } from "lucide-react";
import { JobStatusCard } from "@/components/JobStatusCard";

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const { job, error } = useJobStatus(id);
  const [downloading, setDownloading] = useState(false);

  async function downloadResults() {
    setDownloading(true);
    try {
      const { download_url } = await getDownloadUrl(id);
      window.open(download_url, "_blank");
    } catch (e) {
      alert(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="space-y-6 max-w-lg">
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-brand-600">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Link>

      <div>
        <h1 className="text-2xl font-bold text-gray-900">Batch Job</h1>
        <p className="mt-1 font-mono text-xs text-gray-400">{id}</p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
      )}

      <JobStatusCard jobId={id} />

      {job?.status === "completed" && (
        <button
          onClick={downloadResults}
          disabled={downloading}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
        >
          <Download className="h-4 w-4" />
          {downloading ? "Generating link…" : "Download Results (NDJSON)"}
        </button>
      )}
    </div>
  );
}
