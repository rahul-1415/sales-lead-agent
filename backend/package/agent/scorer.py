import logging

from agent.models import (
    CompanyEnrichment,
    EmailValidationResult,
    LeadAction,
    ScoreBreakdown,
    SimilarityResult,
)
from config import get_settings
from tools.embeddings import top_similarity_score
from tools.industry_classifier import classify_and_score

logger = logging.getLogger(__name__)
settings = get_settings()


def build_score_breakdown(
    enrichment: CompanyEnrichment,
    similarity_results: list[SimilarityResult],
) -> ScoreBreakdown:
    """
    Combines deterministic sub-scores from the classifier tool and the
    embedding similarity search into a single ScoreBreakdown.

    Keeping this separate from the orchestrator means it's fully unit-testable
    without mocking LLM calls or AWS clients.
    """
    sub_scores = classify_and_score(
        industry_segment=enrichment.industry_segment,
        company_size=enrichment.company_size,
        location=enrichment.headquarters,
        recent_funding=enrichment.recent_funding,
        technologies=enrichment.technologies,
    )

    return ScoreBreakdown(
        industry_fit=sub_scores["industry_fit"],
        company_size_fit=sub_scores["company_size_fit"],
        geographic_fit=sub_scores["geographic_fit"],
        recent_activity=sub_scores["recent_activity"],
        similarity_to_icp=top_similarity_score(similarity_results),
    )


def decide_action(
    score: float,
    email_result: EmailValidationResult,
) -> LeadAction:
    """
    Maps a weighted score + email validity to a routing action.

    Decision rules (explicit, not learned — easy to explain in an interview):
      - Score >= priority threshold AND valid email  → PRIORITY
      - Score >= priority threshold, bad email       → RESEARCH (find contact)
      - Score >= standard threshold                  → STANDARD
      - Score >= 0.25                                → RESEARCH
      - Below 0.25                                   → REJECT
    """
    priority_threshold = settings.lead_score_priority_threshold
    standard_threshold = settings.lead_score_standard_threshold

    if score >= priority_threshold:
        if email_result.is_valid:
            return LeadAction.PRIORITY
        return LeadAction.RESEARCH  # great company, need to find a contact

    if score >= standard_threshold:
        return LeadAction.STANDARD

    if score >= 0.25:
        return LeadAction.RESEARCH

    return LeadAction.REJECT


def adjust_for_email(score: float, email_result: EmailValidationResult) -> float:
    """
    Small penalty/boost based on email validity — keeps the confidence score
    honest without letting a bad email completely tank a strong company score.
    """
    if email_result.is_valid and email_result.is_deliverable:
        return min(score + 0.03, 1.0)
    if not email_result.is_valid:
        return max(score - 0.05, 0.0)
    return score
