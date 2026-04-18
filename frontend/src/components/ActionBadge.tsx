import clsx from "clsx";
import type { LeadAction } from "@/lib/types";

const styles: Record<LeadAction, string> = {
  priority: "bg-green-100 text-green-800",
  standard: "bg-blue-100  text-blue-800",
  research: "bg-yellow-100 text-yellow-800",
  reject:   "bg-red-100   text-red-800",
};

const labels: Record<LeadAction, string> = {
  priority: "Priority",
  standard: "Standard",
  research: "Research",
  reject:   "Reject",
};

export function ActionBadge({ action }: { action: LeadAction }) {
  return (
    <span className={clsx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", styles[action])}>
      {labels[action]}
    </span>
  );
}
