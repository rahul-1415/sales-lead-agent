import type { ScoreBreakdown } from "@/lib/types";
import { ScoreBar } from "./ScoreBar";

export function ScoreBreakdownCard({ breakdown }: { breakdown: ScoreBreakdown }) {
  const rows: { label: string; key: keyof ScoreBreakdown }[] = [
    { label: "Industry fit",      key: "industry_fit" },
    { label: "Company size fit",  key: "company_size_fit" },
    { label: "Geographic fit",    key: "geographic_fit" },
    { label: "Recent activity",   key: "recent_activity" },
    { label: "ICP similarity",    key: "similarity_to_icp" },
  ];

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
      <h3 className="text-sm font-semibold text-gray-900">Score Breakdown</h3>
      {rows.map(({ label, key }) => (
        <ScoreBar key={key} label={label} value={breakdown[key] as number} />
      ))}
      <div className="pt-2 border-t border-gray-100">
        <ScoreBar label="Weighted total" value={breakdown.weighted_total} />
      </div>
    </div>
  );
}
