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
}): Promise<LeadListResponse> {
  const q = new URLSearchParams();
  if (params.score_min != null) q.set("score_min", String(params.score_min));
  if (params.limit != null)     q.set("limit",     String(params.limit));
  if (params.cursor)            q.set("cursor",    params.cursor);
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

// ---------------------------------------------------------------------------
// Queue
// ---------------------------------------------------------------------------

export function getQueueDepth(): Promise<{ depth: number | null }> {
  return request("/queue/depth");
}
