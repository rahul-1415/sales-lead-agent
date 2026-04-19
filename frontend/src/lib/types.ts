// Mirrors the Pydantic models in backend/agent/models.py

export type LeadAction = "priority" | "standard" | "research" | "reject";
export type JobStatus = "pending" | "processing" | "completed" | "failed";
export type IndustrySegment =
  | "logistics" | "manufacturing" | "retail" | "healthcare"
  | "financial_services" | "technology" | "energy" | "other";
export type CompanySize = "startup" | "smb" | "mid_market" | "enterprise";

export interface RawLead {
  company: string;
  contact_name?: string;
  contact_email?: string;
  website?: string;
  industry?: string;
  employee_count?: number;
  location?: string;
  notes?: string;
}

export interface EmailValidationResult {
  email: string;
  is_valid: boolean;
  is_deliverable?: boolean;
  reason?: string;
}

export interface CompanyEnrichment {
  company_name: string;
  website?: string;
  industry_segment?: IndustrySegment;
  employee_count?: number;
  company_size?: CompanySize;
  founded_year?: number;
  headquarters?: string;
  description?: string;
  recent_funding?: string;
  technologies: string[];
  source: string;
}

export interface SimilarityResult {
  matched_company: string;
  similarity_score: number;
  match_reason?: string;
}

export interface ScoreBreakdown {
  industry_fit: number;
  company_size_fit: number;
  geographic_fit: number;
  recent_activity: number;
  similarity_to_icp: number;
  weighted_total: number;
}

export interface EnrichedLead {
  lead_id: string;
  dedup_key?: string;
  batch_id: string;
  processed_at: string;
  raw: RawLead;
  email_validation?: EmailValidationResult;
  company_enrichment?: CompanyEnrichment;
  similarity_results: SimilarityResult[];
  score_breakdown?: ScoreBreakdown;
  confidence_score: number;
  recommended_action: LeadAction;
  reasoning: string;
  assigned_to?: string;
  tags: string[];
}

export interface BatchJobStats {
  total: number;
  processed: number;
  duplicates: number;
  priority: number;
  standard: number;
  research: number;
  rejected: number;
  errors: number;
  success_rate: number;
}

export interface JobStatusResponse {
  job_id: string;
  batch_id: string;
  status: JobStatus;
  stats: BatchJobStats;
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

export interface UploadResponse {
  job_id: string;
  batch_id: string;
  lead_count: number;
  duplicate_count: number;
  message: string;
}

export interface LeadListResponse {
  leads: EnrichedLead[];
  total: number;
  page: number;
  page_size: number;
}
