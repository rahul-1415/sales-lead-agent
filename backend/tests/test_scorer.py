from agent.models import (
    CompanyEnrichment,
    IndustrySegment,
    CompanySize,
    SimilarityResult,
    ScoreBreakdown,
    compute_dedup_key,
)
from agent.scorer import build_score_breakdown


def _make_enrichment(**kwargs) -> CompanyEnrichment:
    defaults = dict(
        company_name="Acme Logistics",
        industry_segment=IndustrySegment.LOGISTICS,
        company_size=CompanySize.MID_MARKET,
        headquarters="Chicago, IL",
        recent_funding="Series A – $8M (2023)",
        technologies=["SAP", "Salesforce"],
        employee_count=150,
        founded_year=2015,
        description="Last-mile freight company.",
    )
    defaults.update(kwargs)
    return CompanyEnrichment(**defaults)


def _similarity(score: float) -> list[SimilarityResult]:
    return [
        SimilarityResult(
            matched_company="Apex Freight",
            similarity_score=score,
            match_reason=f"test {score}",
        )
    ]


def test_score_returns_breakdown():
    result = build_score_breakdown(_make_enrichment(), _similarity(0.8))
    assert isinstance(result, ScoreBreakdown)
    assert 0.0 <= result.weighted_total <= 1.0


def test_high_icp_similarity_boosts_score():
    high = build_score_breakdown(_make_enrichment(), _similarity(0.9))
    low = build_score_breakdown(_make_enrichment(), _similarity(0.1))
    assert high.weighted_total > low.weighted_total


def test_no_similarity_results_gives_zero_icp():
    result = build_score_breakdown(_make_enrichment(), [])
    assert result.similarity_to_icp == 0.0


def test_dedup_key_normalises_company_name():
    assert compute_dedup_key("Acme, Inc.", "jane@acme.com", None) == compute_dedup_key(
        "acme inc", "jane@acme.com", None
    )


def test_dedup_key_email_takes_precedence_over_website():
    key_email = compute_dedup_key("Acme", "jane@acme.com", "https://acme.com")
    key_website = compute_dedup_key("Acme", None, "https://acme.com")
    assert key_email != key_website


def test_dedup_key_is_16_chars():
    assert len(compute_dedup_key("Acme Logistics", "jane@acme.com", None)) == 16
