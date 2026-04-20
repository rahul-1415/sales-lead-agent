import logging
from typing import Optional

from agent.models import CompanySize, IndustrySegment
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Ideal Customer Profile (ICP) — tweak these to match Eranova's target market
# ---------------------------------------------------------------------------

ICP_INDUSTRIES = frozenset(
    {
        IndustrySegment.LOGISTICS,
        IndustrySegment.MANUFACTURING,
        IndustrySegment.HEALTHCARE,
    }
)

ICP_SIZES = frozenset(
    {
        CompanySize.MID_MARKET,
        CompanySize.ENTERPRISE,
    }
)

ICP_GEOGRAPHIES = frozenset(
    {
        "us",
        "usa",
        "united states",
        "ca",
        "canada",
        "uk",
        "united kingdom",
    }
)

# ---------------------------------------------------------------------------
# Scoring functions — each returns 0.0–1.0
# ---------------------------------------------------------------------------


def score_industry_fit(segment: Optional[IndustrySegment]) -> float:
    if segment is None:
        return 0.2
    if segment in ICP_INDUSTRIES:
        return 1.0
    if segment == IndustrySegment.FINANCIAL_SERVICES:
        return 0.6  # adjacent — worth researching
    if segment == IndustrySegment.TECHNOLOGY:
        return 0.5
    if segment == IndustrySegment.OTHER:
        return 0.2
    return 0.4


def score_company_size_fit(size: Optional[CompanySize]) -> float:
    if size is None:
        return 0.3
    if size in ICP_SIZES:
        return 1.0
    if size == CompanySize.SMB:
        return 0.5  # smaller but worth standard follow-up
    return 0.1  # startup — too early stage


def score_geographic_fit(location: Optional[str]) -> float:
    if not location:
        return 0.5  # unknown — give benefit of the doubt
    lowered = location.lower()
    if any(geo in lowered for geo in ICP_GEOGRAPHIES):
        return 1.0
    # European markets — secondary priority
    eu_terms = ["germany", "france", "netherlands", "sweden", "uk", "united kingdom"]
    if any(term in lowered for term in eu_terms):
        return 0.7
    return 0.3


def score_recent_activity(
    recent_funding: Optional[str], technologies: list[str]
) -> float:
    """
    Funding recency and tech stack are signals that a company is actively investing.
    A recent funding round often precedes a buying decision for enterprise software.
    """
    score = 0.0

    if recent_funding:
        funding_lower = recent_funding.lower()
        if "series c" in funding_lower or "series d" in funding_lower:
            score += 0.6
        elif "series b" in funding_lower:
            score += 0.5
        elif "series a" in funding_lower:
            score += 0.3
        else:
            score += 0.2

    # Enterprise tech stack signals existing budget and integration readiness
    enterprise_tech = {
        "sap",
        "oracle",
        "salesforce",
        "servicenow",
        "workday",
        "aws",
        "azure",
    }
    tech_lower = {t.lower() for t in technologies}
    if tech_lower & enterprise_tech:
        score += 0.4

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def classify_and_score(
    industry_segment: Optional[IndustrySegment],
    company_size: Optional[CompanySize],
    location: Optional[str],
    recent_funding: Optional[str],
    technologies: list[str],
) -> dict[str, float]:
    """
    Returns a dict of named sub-scores consumed by the agent's ScoreBreakdown.
    Keeps scoring logic fully deterministic and unit-testable without an LLM.
    """
    return {
        "industry_fit": score_industry_fit(industry_segment),
        "company_size_fit": score_company_size_fit(company_size),
        "geographic_fit": score_geographic_fit(location),
        "recent_activity": score_recent_activity(recent_funding, technologies),
    }
