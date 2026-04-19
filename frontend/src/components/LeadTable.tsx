"use client";

import Link from "next/link";
import type { EnrichedLead } from "@/lib/types";
import { ActionBadge } from "./ActionBadge";

interface Props {
  leads: EnrichedLead[];
  loading?: boolean;
}

export function LeadTable({ leads, loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-14 rounded-lg bg-gray-100 animate-pulse" />
        ))}
      </div>
    );
  }

  if (leads.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-200 p-12 text-center text-sm text-gray-400">
        No leads yet. Upload a file to get started.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {["Company", "Industry", "Size", "Score", "Action", "AI Reasoning", "Tags"].map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {leads.map((lead) => {
            const enrich = lead.company_enrichment;
            return (
              <tr key={lead.lead_id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 font-medium text-gray-900">
                  <Link href={`/leads/${lead.lead_id}`} className="hover:text-brand-600 hover:underline">
                    {lead.raw.company}
                  </Link>
                </td>
                <td className="px-4 py-3 text-gray-500 capitalize">
                  {enrich?.industry_segment?.replace("_", " ") ?? "—"}
                </td>
                <td className="px-4 py-3 text-gray-500 capitalize">
                  {enrich?.company_size?.replace("_", " ") ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <ScoreChip score={lead.confidence_score} />
                </td>
                <td className="px-4 py-3">
                  <ActionBadge action={lead.recommended_action} />
                </td>
                <td className="px-4 py-3 max-w-xs">
                  <p className="text-xs text-gray-500 leading-relaxed line-clamp-2" title={lead.reasoning}>
                    {lead.reasoning}
                  </p>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {lead.tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600 capitalize">
                        {tag.replace("_", " ")}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ScoreChip({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 75 ? "text-green-700 bg-green-50" :
    pct >= 50 ? "text-yellow-700 bg-yellow-50" :
                "text-red-700 bg-red-50";
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${color}`}>
      {pct}%
    </span>
  );
}
