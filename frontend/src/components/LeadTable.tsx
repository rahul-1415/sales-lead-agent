"use client";

import { useState } from "react";
import Link from "next/link";
import type { EnrichedLead } from "@/lib/types";
import { ActionBadge } from "./ActionBadge";
import { X } from "lucide-react";

interface Props {
  leads: EnrichedLead[];
  loading?: boolean;
}

export function LeadTable({ leads, loading }: Props) {
  const [expanded, setExpanded] = useState<{ company: string; reasoning: string } | null>(null);

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
    <>
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
                    <button
                      onClick={() => setExpanded({ company: lead.raw.company, reasoning: lead.reasoning })}
                      className="text-left text-xs text-gray-500 leading-relaxed line-clamp-2 hover:text-brand-600 cursor-pointer transition-colors"
                    >
                      {lead.reasoning}
                    </button>
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

      {/* Reasoning modal */}
      {expanded && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setExpanded(null)}
        >
          <div
            className="w-full max-w-lg rounded-2xl bg-white shadow-xl p-6 mx-4 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-600">AI Reasoning</p>
                <h2 className="mt-0.5 text-base font-semibold text-gray-900">{expanded.company}</h2>
              </div>
              <button
                onClick={() => setExpanded(null)}
                className="shrink-0 text-gray-400 hover:text-gray-700 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="text-sm text-gray-700 leading-relaxed">{expanded.reasoning}</p>
          </div>
        </div>
      )}
    </>
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
