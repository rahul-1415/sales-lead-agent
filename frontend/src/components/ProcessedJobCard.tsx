"use client";

import { useJobStatus } from "@/hooks/useJobStatus";
import clsx from "clsx";
import { CheckCircle, XCircle } from "lucide-react";

const statusColor = {
  completed: "text-green-600",
  failed:    "text-red-600",
};

export function ProcessedJobCard({ jobId }: { jobId: string }) {
  const { job } = useJobStatus(jobId);

  if (!job) return null;

  const { stats, status } = job;
  const isOk = status === "completed";
  const pct  = stats.total > 0 ? (stats.processed / stats.total) * 100 : 0;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isOk
            ? <CheckCircle className="h-4 w-4 text-green-500" />
            : <XCircle    className="h-4 w-4 text-red-500" />
          }
          <span className={clsx("text-sm font-semibold capitalize", statusColor[status as keyof typeof statusColor])}>
            {status}
          </span>
        </div>
        <span className="text-xs text-gray-400 font-mono">{jobId.slice(0, 8)}…</span>
      </div>

      {/* Progress bar — always full for completed */}
      <div>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>{stats.processed} / {stats.total} leads</span>
          <span>{pct.toFixed(0)}%</span>
        </div>
        <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
          <div
            className={clsx(
              "h-full rounded-full transition-all duration-500",
              isOk ? "bg-green-500" : "bg-red-400"
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Action breakdown */}
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
