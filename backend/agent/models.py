from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LeadAction(str, Enum):
    PRIORITY = "priority"
    STANDARD = "standard"
    RESEARCH = "research"
    REJECT = "reject"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class IndustrySegment(str, Enum):
    LOGISTICS = "logistics"
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    HEALTHCARE = "healthcare"
    FINANCIAL_SERVICES = "financial_services"
    TECHNOLOGY = "technology"
    ENERGY = "energy"
    OTHER = "other"


class CompanySize(str, Enum):
    STARTUP = "startup"        # 1–50
    SMB = "smb"                # 51–500
    MID_MARKET = "mid_market"  # 501–5000
    ENTERPRISE = "enterprise"  # 5000+


# ---------------------------------------------------------------------------
# Input models (what comes in from the user / CSV / API)
# ---------------------------------------------------------------------------


class RawLead(BaseModel):
    """A single unvalidated lead as submitted by the user."""

    company: str = Field(..., min_length=1)
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[int] = Field(None, ge=0)
    location: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("contact_email")
    @classmethod
    def normalise_email(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if v else None


class LeadBatch(BaseModel):
    """A batch of raw leads submitted together."""

    batch_id: str = Field(default_factory=lambda: str(uuid4()))
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    leads: list[RawLead]
    source: Optional[str] = None  # "csv_upload" | "api" | "webhook"

    @property
    def size(self) -> int:
        return len(self.leads)


# ---------------------------------------------------------------------------
# Enrichment models (data added by tools)
# ---------------------------------------------------------------------------


class EmailValidationResult(BaseModel):
    email: str
    is_valid: bool
    is_deliverable: Optional[bool] = None
    reason: Optional[str] = None


class CompanyEnrichment(BaseModel):
    """Data returned by the company lookup tool."""

    company_name: str
    website: Optional[str] = None
    industry_segment: Optional[IndustrySegment] = None
    employee_count: Optional[int] = None
    company_size: Optional[CompanySize] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    description: Optional[str] = None
    recent_funding: Optional[str] = None  # e.g. "Series B – $40M (2024)"
    technologies: list[str] = Field(default_factory=list)
    source: str = "mock"  # "clearbit" | "apollo" | "mock"


class SimilarityResult(BaseModel):
    """Result from embedding-based similarity search against known good leads."""

    matched_company: str
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    match_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Scoring models (agent reasoning output)
# ---------------------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    """Granular score components so the agent's reasoning is explainable."""

    industry_fit: float = Field(..., ge=0.0, le=1.0)
    company_size_fit: float = Field(..., ge=0.0, le=1.0)
    geographic_fit: float = Field(..., ge=0.0, le=1.0)
    recent_activity: float = Field(..., ge=0.0, le=1.0)    # funding, hiring signals
    similarity_to_icp: float = Field(..., ge=0.0, le=1.0)  # ideal customer profile

    @property
    def weighted_total(self) -> float:
        weights = {
            "industry_fit": 0.30,
            "company_size_fit": 0.25,
            "geographic_fit": 0.15,
            "recent_activity": 0.15,
            "similarity_to_icp": 0.15,
        }
        return round(
            self.industry_fit * weights["industry_fit"]
            + self.company_size_fit * weights["company_size_fit"]
            + self.geographic_fit * weights["geographic_fit"]
            + self.recent_activity * weights["recent_activity"]
            + self.similarity_to_icp * weights["similarity_to_icp"],
            4,
        )


# ---------------------------------------------------------------------------
# Enriched / processed lead (the core domain object)
# ---------------------------------------------------------------------------


class EnrichedLead(BaseModel):
    """A fully processed lead with enrichment data, score, and agent decision."""

    lead_id: str = Field(default_factory=lambda: str(uuid4()))
    batch_id: str
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Original input (preserved verbatim)
    raw: RawLead

    # Enrichment layers
    email_validation: Optional[EmailValidationResult] = None
    company_enrichment: Optional[CompanyEnrichment] = None
    similarity_results: list[SimilarityResult] = Field(default_factory=list)

    # Agent decision
    score_breakdown: Optional[ScoreBreakdown] = None
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    recommended_action: LeadAction
    reasoning: str  # natural-language explanation of the decision

    # Routing metadata
    assigned_to: Optional[str] = None  # sales rep email / queue name
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Job tracking models (DynamoDB batch_jobs table)
# ---------------------------------------------------------------------------


class BatchJobStats(BaseModel):
    total: int = 0
    processed: int = 0
    priority: int = 0
    standard: int = 0
    research: int = 0
    rejected: int = 0
    errors: int = 0

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.processed - self.errors) / self.total, 4)


class BatchJob(BaseModel):
    """Tracks the lifecycle of a lead processing batch."""

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    batch_id: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    stats: BatchJobStats = Field(default_factory=BatchJobStats)
    s3_input_key: Optional[str] = None   # raw input file in S3
    s3_output_key: Optional[str] = None  # enriched output file in S3
    error_message: Optional[str] = None

    def mark_completed(self) -> None:
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.updated_at = self.completed_at

    def mark_failed(self, reason: str) -> None:
        self.status = JobStatus.FAILED
        self.error_message = reason
        self.updated_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# API response models
# ---------------------------------------------------------------------------


class UploadResponse(BaseModel):
    job_id: str
    batch_id: str
    lead_count: int
    message: str


class LeadListResponse(BaseModel):
    leads: list[EnrichedLead]
    total: int
    page: int
    page_size: int


class JobStatusResponse(BaseModel):
    job_id: str
    batch_id: str
    status: JobStatus
    stats: BatchJobStats
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
