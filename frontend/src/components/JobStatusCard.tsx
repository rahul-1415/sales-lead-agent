"use client";

import { useEffect } from "react";
import { useJobStatus } from "@/hooks/useJobStatus";
import type { JobStatus } from "@/lib/types";
import clsx from "clsx";
import { CheckCircle, Clock, Loader2, XCircle } from "lucide-react";

const statusIcon: Record<JobStatus, React.ReactNode> = {
  pending:    <Clock className="h-4 w-4 text-gray-400" />,
  processing: <Loader2 className="h-4 w-4 text-brand-500 animate-spin" />,
  completed:  <CheckCircle className="h-4 w-4 text-green-500" />,
  failed:     <XCircle className="h-4 w-4 text-red-500" />,
};

const statusColor: Record<JobStatus, string> = {
  pending:    "text-gray-500",
  processing: "text-brand-600",
  completed:  "text-green-600",
  failed:     "text-red-600",
};

interface Props {
  jobId: string;
  onComplete?: (jobId: string) => void;
}

export function JobStatusCard({ jobId, onComplete }: Props) {
  const { job, error } = useJobStatus(jobId);

  useEffect(() => {
    if ((job?.status === "completed" || job?.status === "failed") && onComplete) {
      onComplete(jobId);
    }
  }, [job?.status, jobId, onComplete]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (!job) {
    return <div className="rounded-xl border border-gray-200 bg-white p-4 animate-pulse h-28" />;
  }

  const { stats, status } = job;
  const pct = stats.total > 0 ? (stats.processed / stats.total) * 100 : 0;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {statusIcon[status]}
          <span className={clsx("text-sm font-semibold capitalize", statusColor[status])}>
            {status}
          </span>
        </div>
        <span className="text-xs text-gray-400 font-mono">{jobId.slice(0, 8)}…</span>
      </div>

      <div>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>{stats.processed} / {stats.total} leads</span>
          <span>{pct.toFixed(0)}%</span>
        </div>
        <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
          <div
            className="h-full rounded-full bg-brand-500 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2 text-center">
        {[
          { label: "Priority", value: stats.priority, color: "text-green-600" },
          { label: "Standard", value: stats.standard, color: "text-blue-600" },
          { label: "Research", value: stats.research, color: "text-yellow-600" },
          { label: "Rejected", value: stats.rejected, color: "text-red-500" },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-lg bg-gray-50 py-2">
            <div className={clsx("text-lg font-bold", color)}>{value}</div>
            <div className="text-xs text-gray-500">{label}</div>
          </div>
        ))}
      </div>

      {stats.errors > 0 && (
        <p className="text-xs text-red-600">{stats.errors} lead(s) failed to process</p>
      )}
    </div>
  );
}
