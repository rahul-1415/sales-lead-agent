"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getLead } from "@/lib/api";
import type { EnrichedLead } from "@/lib/types";
import { ActionBadge } from "@/components/ActionBadge";
import { ScoreBreakdownCard } from "@/components/ScoreBreakdownCard";
import { ArrowLeft, Building2, Mail, MapPin, Zap } from "lucide-react";

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [lead, setLead] = useState<EnrichedLead | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLead(id)
      .then(setLead)
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (!lead) {
    return <div className="space-y-4">{Array.from({ length: 4 }).map((_, i) => (
      <div key={i} className="h-24 rounded-xl bg-gray-100 animate-pulse" />
    ))}</div>;
  }

  const enrich = lead.company_enrichment;

  return (
    <div className="space-y-6">
      {/* Back */}
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-brand-600">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{lead.raw.company}</h1>
          <p className="mt-1 text-sm text-gray-500">
            Lead ID: <span className="font-mono">{lead.lead_id}</span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <ActionBadge action={lead.recommended_action} />
          <span className="text-3xl font-bold text-gray-900">
            {Math.round(lead.confidence_score * 100)}%
          </span>
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        {/* Company info */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
          <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <Building2 className="h-4 w-4 text-gray-400" /> Company
          </h3>
          {enrich?.description && (
            <p className="text-sm text-gray-600">{enrich.description}</p>
          )}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <InfoRow label="Industry"  value={enrich?.industry_segment?.replace("_", " ")} />
            <InfoRow label="Size"      value={enrich?.company_size?.replace("_", " ")} />
            <InfoRow label="Employees" value={enrich?.employee_count?.toLocaleString()} />
            <InfoRow label="Founded"   value={enrich?.founded_year?.toString()} />
            <InfoRow label="HQ"        value={enrich?.headquarters} icon={<MapPin className="h-3 w-3" />} />
            <InfoRow label="Website"   value={enrich?.website} />
          </dl>
          {enrich?.recent_funding && (
            <div className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2 text-xs text-green-700">
              <Zap className="h-3.5 w-3.5" />
              {enrich.recent_funding}
            </div>
          )}
          {enrich?.technologies && enrich.technologies.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {enrich.technologies.map((t) => (
                <span key={t} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{t}</span>
              ))}
            </div>
          )}
        </div>

        {/* Score breakdown */}
        {lead.score_breakdown && (
          <ScoreBreakdownCard breakdown={lead.score_breakdown} />
        )}
      </div>

      {/* Agent reasoning */}
      <div className="rounded-xl border border-brand-200 bg-brand-50 p-5">
        <h3 className="mb-2 text-sm font-semibold text-brand-700">AI Reasoning</h3>
        <p className="text-sm text-gray-700 leading-relaxed">{lead.reasoning}</p>
      </div>

      {/* Contact */}
      {(lead.raw.contact_name || lead.raw.contact_email) && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-2">
          <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <Mail className="h-4 w-4 text-gray-400" /> Contact
          </h3>
          {lead.raw.contact_name && <p className="text-sm text-gray-700">{lead.raw.contact_name}</p>}
          {lead.raw.contact_email && (
            <div className="flex items-center gap-2">
              <a href={`mailto:${lead.raw.contact_email}`} className="text-sm text-brand-600 hover:underline">
                {lead.raw.contact_email}
              </a>
              {lead.email_validation && (
                <span className={`text-xs ${lead.email_validation.is_valid ? "text-green-600" : "text-red-500"}`}>
                  {lead.email_validation.is_valid ? "✓ valid" : "✗ invalid"}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Similar ICP matches */}
      {lead.similarity_results.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
          <h3 className="text-sm font-semibold text-gray-900">Similar ICP Companies</h3>
          {lead.similarity_results.map((r) => (
            <div key={r.matched_company} className="flex items-center justify-between text-sm">
              <span className="text-gray-700">{r.matched_company}</span>
              <span className="font-medium text-gray-500">
                {Math.round(r.similarity_score * 100)}% match
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value, icon }: { label: string; value?: string; icon?: React.ReactNode }) {
  if (!value) return null;
  return (
    <>
      <dt className="text-gray-400">{label}</dt>
      <dd className="text-gray-700 capitalize flex items-center gap-1">{icon}{value}</dd>
    </>
  );
}
