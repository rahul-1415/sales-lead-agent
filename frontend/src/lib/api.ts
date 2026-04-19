import type {
  EnrichedLead,
  JobStatusResponse,
  LeadListResponse,
  UploadResponse,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Leads
// ---------------------------------------------------------------------------

export async function uploadLeads(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/leads/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
  return res.json();
}

export function getLeads(params: {
  score_min?: number;
  limit?: number;
  cursor?: string;
  page?: number;
}): Promise<LeadListResponse> {
  const q = new URLSearchParams();
  if (params.score_min != null) q.set("score_min", String(params.score_min));
  if (params.limit != null)     q.set("limit",     String(params.limit));
  if (params.cursor)            q.set("cursor",    params.cursor);
  if (params.page != null)      q.set("page",      String(params.page));
  return request<LeadListResponse>(`/leads?${q}`);
}

export function getLead(leadId: string): Promise<EnrichedLead> {
  return request<EnrichedLead>(`/leads/${leadId}`);
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/jobs/${jobId}`);
}

export function getDownloadUrl(jobId: string): Promise<{ download_url: string }> {
  return request(`/jobs/${jobId}/download`);
}

export async function exportLeads(scoreMin = 0): Promise<void> {
  const res = await fetch(`${BASE_URL}/leads/export?score_min=${scoreMin}`);
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "leads_export.ndjson";
  a.click();
  URL.revokeObjectURL(url);
}

export async function clearLeads(): Promise<{ cleared: number }> {
  const res = await fetch(`${BASE_URL}/leads`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Clear failed: ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Queue
// ---------------------------------------------------------------------------

export function getQueueDepth(): Promise<{ depth: number | null }> {
  return request("/queue/depth");
}
