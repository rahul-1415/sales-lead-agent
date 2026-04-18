"""
SalesLeadAgent — multi-step agent that processes a single RawLead through:

  Step 1  Validate email
  Step 2  Enrich company data
  Step 3  Embedding similarity search against ICP examples
  Step 4  Build deterministic score breakdown
  Step 5  LLM reasoning — Claude explains the score in plain English
  Step 6  Decide routing action
  Step 7  Return fully structured EnrichedLead

Each step is a discrete method so failures are localised and individually
retryable. The agent never raises — it always returns an EnrichedLead, using
graceful defaults when a tool fails, so a single bad lead never kills a batch.
"""

import logging
from datetime import datetime, timezone

import anthropic

from agent.models import (
    BatchJobStats,
    CompanyEnrichment,
    EmailValidationResult,
    EnrichedLead,
    LeadAction,
    RawLead,
    ScoreBreakdown,
    SimilarityResult,
)
from agent.prompts import SYSTEM_PROMPT, build_reasoning_prompt
from agent.scorer import adjust_for_email, build_score_breakdown, decide_action
from config import get_settings
from tools.company_lookup import enrich_company
from tools.email_validator import validate_email
from tools.embeddings import find_similar_leads

logger = logging.getLogger(__name__)
settings = get_settings()


class SalesLeadAgent:
    """
    Orchestrates the full lead enrichment pipeline for a single RawLead.
    Instantiate once per Lambda invocation (or once per app startup locally).
    The Anthropic client is created once and reused across leads.
    """

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process(self, raw: RawLead, batch_id: str) -> EnrichedLead:
        logger.info("processing lead", extra={"company": raw.company, "batch_id": batch_id})

        # Step 1 — email validation
        email_result = self._validate_email(raw.contact_email)

        # Step 2 — company enrichment
        enrichment = self._enrich_company(raw)

        # Step 3 — similarity search (RAG)
        similarity_results = self._find_similar(enrichment)

        # Step 4 — deterministic scoring
        score_breakdown = build_score_breakdown(enrichment, similarity_results)
        raw_score = score_breakdown.weighted_total
        confidence_score = adjust_for_email(raw_score, email_result)

        # Step 5 — LLM reasoning
        reasoning = self._generate_reasoning(
            raw.company, enrichment, score_breakdown, similarity_results, email_result
        )

        # Step 6 — routing decision
        action = decide_action(confidence_score, email_result)

        logger.info(
            "lead processed",
            extra={
                "company": raw.company,
                "score": confidence_score,
                "action": action,
            },
        )

        return EnrichedLead(
            batch_id=batch_id,
            raw=raw,
            email_validation=email_result,
            company_enrichment=enrichment,
            similarity_results=similarity_results,
            score_breakdown=score_breakdown,
            confidence_score=round(confidence_score, 4),
            recommended_action=action,
            reasoning=reasoning,
            tags=self._build_tags(enrichment, action),
        )

    # ------------------------------------------------------------------
    # Step implementations — each catches its own exceptions
    # ------------------------------------------------------------------

    def _validate_email(self, email: str | None) -> EmailValidationResult:
        try:
            return validate_email(email)
        except Exception:
            logger.warning("email validation failed", exc_info=True)
            return EmailValidationResult(email=email or "", is_valid=False, reason="tool_error")

    def _enrich_company(self, raw: RawLead) -> CompanyEnrichment:
        try:
            enrichment = enrich_company(raw.company)
            # Merge user-supplied data where enrichment has gaps
            if raw.industry and not enrichment.industry_segment:
                from tools.company_lookup import _classify_industry
                enrichment.industry_segment = _classify_industry(raw.industry)
            if raw.employee_count and not enrichment.employee_count:
                enrichment.employee_count = raw.employee_count
                from tools.company_lookup import _classify_size
                enrichment.company_size = _classify_size(raw.employee_count)
            if raw.location and not enrichment.headquarters:
                enrichment.headquarters = raw.location
            return enrichment
        except Exception:
            logger.warning("company enrichment failed", extra={"company": raw.company}, exc_info=True)
            return CompanyEnrichment(company_name=raw.company, source="fallback")

    def _find_similar(self, enrichment: CompanyEnrichment) -> list[SimilarityResult]:
        try:
            return find_similar_leads(
                company_name=enrichment.company_name,
                description=enrichment.description,
            )
        except Exception:
            logger.warning("similarity search failed", exc_info=True)
            return []

    def _generate_reasoning(
        self,
        company: str,
        enrichment: CompanyEnrichment,
        score_breakdown: ScoreBreakdown,
        similarity_results: list[SimilarityResult],
        email_result: EmailValidationResult,
    ) -> str:
        """
        Calls Claude with a structured prompt. Uses extended thinking disabled
        intentionally — we want fast, grounded reasoning, not open-ended exploration.
        Prompt caching is applied to the system prompt (static across all leads).
        """
        prompt = build_reasoning_prompt(
            company=company,
            enrichment=enrichment,
            score_breakdown=score_breakdown,
            similarity_results=similarity_results,
            email_valid=email_result.is_valid,
        )

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},  # cache system prompt across leads
                    }
                ],
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception:
            logger.warning("LLM reasoning failed — using fallback", exc_info=True)
            return (
                f"{company} scored {score_breakdown.weighted_total:.0%} overall. "
                f"Industry: {enrichment.industry_segment}, "
                f"Size: {enrichment.company_size}."
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tags(enrichment: CompanyEnrichment, action: LeadAction) -> list[str]:
        tags: list[str] = []
        if enrichment.industry_segment:
            tags.append(enrichment.industry_segment.value)
        if enrichment.company_size:
            tags.append(enrichment.company_size.value)
        if enrichment.recent_funding:
            tags.append("recently_funded")
        if action == LeadAction.PRIORITY:
            tags.append("priority")
        return tags


# ------------------------------------------------------------------
# Batch processor — called by the Lambda handler
# ------------------------------------------------------------------


def process_batch(
    leads: list[RawLead],
    batch_id: str,
    job_id: str,
    stats: BatchJobStats,
) -> list[EnrichedLead]:
    """
    Processes a list of leads sequentially within a single Lambda invocation.
    Updates the shared stats object in place so the caller can persist it.

    Sequential (not concurrent) within one Lambda — SQS parallelism comes
    from multiple Lambda invocations running simultaneously, each handling
    a chunk of the batch. This keeps the code simple and avoids thread-safety
    issues with the Anthropic client.
    """
    agent = SalesLeadAgent()
    results: list[EnrichedLead] = []

    for raw in leads:
        try:
            lead = agent.process(raw, batch_id)
            results.append(lead)
            stats.processed += 1
            _increment_action_stat(stats, lead.recommended_action)
        except Exception:
            logger.exception(
                "unhandled error processing lead",
                extra={"company": raw.company, "batch_id": batch_id},
            )
            stats.errors += 1

    return results


def _increment_action_stat(stats: BatchJobStats, action: LeadAction) -> None:
    if action == LeadAction.PRIORITY:
        stats.priority += 1
    elif action == LeadAction.STANDARD:
        stats.standard += 1
    elif action == LeadAction.RESEARCH:
        stats.research += 1
    elif action == LeadAction.REJECT:
        stats.rejected += 1
