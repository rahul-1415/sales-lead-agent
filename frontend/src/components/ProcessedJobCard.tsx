"use client";

import { useJobStatus } from "@/hooks/useJobStatus";
import clsx from "clsx";
import { CheckCircle, XCircle } from "lucide-react";

export function ProcessedJobCard({ jobId }: { jobId: string }) {
  const { job } = useJobStatus(jobId);

  if (!job) return null;

  const { stats, status, completed_at } = job;
  const isOk = status === "completed";

  const completedTime = completed_at
    ? new Date(completed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className={clsx(
      "flex items-center justify-between rounded-xl border px-5 py-4",
      isOk ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"
    )}>
      {/* Left — status + id + time */}
      <div className="flex items-center gap-3">
        {isOk
          ? <CheckCircle className="h-5 w-5 text-green-500 shrink-0" />
          : <XCircle    className="h-5 w-5 text-red-500 shrink-0" />
        }
        <div>
          <p className={clsx("text-sm font-semibold", isOk ? "text-green-800" : "text-red-800")}>
            {isOk ? "Completed" : "Failed"}
          </p>
          <p className="text-xs text-gray-400 font-mono">{jobId.slice(0, 8)}…
            {completedTime && <span className="ml-2 not-italic">{completedTime}</span>}
          </p>
        </div>
      </div>

      {/* Right — lead counts */}
      {isOk && (
        <div className="flex items-center gap-4 text-xs">
          <Stat label="Priority" value={stats.priority} color="text-green-700" />
          <Stat label="Standard" value={stats.standard} color="text-blue-700" />
          <Stat label="Research" value={stats.research} color="text-yellow-700" />
          <Stat label="Rejected" value={stats.rejected} color="text-red-500" />
          <span className="ml-2 text-gray-400">{stats.total} total</span>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  if (value === 0) return null;
  return (
    <span className={clsx("font-medium", color)}>
      {value} {label}
    </span>
  );
}
