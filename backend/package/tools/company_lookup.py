import logging
import re
from typing import Optional

import httpx

from agent.models import CompanyEnrichment, CompanySize, IndustrySegment
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Industry keyword map — used by both mock and real enrichment paths
# ---------------------------------------------------------------------------

_INDUSTRY_KEYWORDS: dict[IndustrySegment, list[str]] = {
    IndustrySegment.LOGISTICS: [
        "logistics",
        "freight",
        "shipping",
        "supply chain",
        "transport",
        "warehouse",
    ],
    IndustrySegment.MANUFACTURING: [
        "manufacturing",
        "factory",
        "industrial",
        "fabrication",
        "assembly",
    ],
    IndustrySegment.RETAIL: [
        "retail",
        "ecommerce",
        "e-commerce",
        "consumer goods",
        "wholesale",
    ],
    IndustrySegment.HEALTHCARE: [
        "healthcare",
        "health",
        "medical",
        "pharma",
        "biotech",
        "clinical",
    ],
    IndustrySegment.FINANCIAL_SERVICES: [
        "finance",
        "banking",
        "insurance",
        "fintech",
        "investment",
        "payments",
    ],
    IndustrySegment.TECHNOLOGY: [
        "software",
        "saas",
        "technology",
        "tech",
        "cloud",
        "ai",
        "data",
    ],
    IndustrySegment.ENERGY: [
        "energy",
        "oil",
        "gas",
        "utilities",
        "renewables",
        "power",
    ],
}


def _classify_industry(text: str) -> Optional[IndustrySegment]:
    lowered = text.lower()
    for segment, keywords in _INDUSTRY_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return segment
    return IndustrySegment.OTHER


def _classify_size(employee_count: Optional[int]) -> Optional[CompanySize]:
    if employee_count is None:
        return None
    if employee_count <= 50:
        return CompanySize.STARTUP
    if employee_count <= 500:
        return CompanySize.SMB
    if employee_count <= 5000:
        return CompanySize.MID_MARKET
    return CompanySize.ENTERPRISE


# ---------------------------------------------------------------------------
# Mock enrichment (no external API key required)
# ---------------------------------------------------------------------------

_MOCK_DB: dict[str, dict] = {
    "acme logistics": {
        "website": "https://acmelogistics.com",
        "description": "Global freight and supply chain management company.",
        "employee_count": 1200,
        "founded_year": 2005,
        "headquarters": "Chicago, IL",
        "recent_funding": None,
        "technologies": ["SAP", "Oracle TMS"],
    },
    "nova health": {
        "website": "https://novahealth.io",
        "description": "Digital health platform for clinical workflow automation.",
        "employee_count": 340,
        "founded_year": 2018,
        "headquarters": "Boston, MA",
        "recent_funding": "Series B – $28M (2023)",
        "technologies": ["AWS", "Epic EHR"],
    },
    "bright retail": {
        "website": "https://brightretail.com",
        "description": "Omnichannel retail solutions for mid-market brands.",
        "employee_count": 80,
        "founded_year": 2015,
        "headquarters": "Austin, TX",
        "recent_funding": "Seed – $4M (2022)",
        "technologies": ["Shopify", "Salesforce"],
    },
}


def _mock_enrich(company_name: str) -> CompanyEnrichment:
    key = company_name.strip().lower()
    data = _MOCK_DB.get(key, {})

    employee_count: Optional[int] = data.get("employee_count")
    description: str = data.get(
        "description", f"{company_name} — no description available."
    )
    industry = _classify_industry(description)
    size = _classify_size(employee_count)

    return CompanyEnrichment(
        company_name=company_name,
        website=data.get("website"),
        industry_segment=industry,
        employee_count=employee_count,
        company_size=size,
        founded_year=data.get("founded_year"),
        headquarters=data.get("headquarters"),
        description=description,
        recent_funding=data.get("recent_funding"),
        technologies=data.get("technologies", []),
        source="mock",
    )


# ---------------------------------------------------------------------------
# Clearbit enrichment (real path, used when API key is configured)
# ---------------------------------------------------------------------------

_CLEARBIT_BASE = "https://company.clearbit.com/v2/companies/find"


def _clearbit_enrich(company_name: str) -> CompanyEnrichment:
    """
    Calls Clearbit Company API. Requires CLEARBIT_API_KEY in env.
    Falls back to mock on any error so the agent always gets a result.
    """
    api_key = getattr(settings, "clearbit_api_key", "")
    if not api_key:
        logger.debug("no Clearbit key — using mock enrichment")
        return _mock_enrich(company_name)

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                _CLEARBIT_BASE,
                params={"name": company_name},
                auth=(api_key, ""),
            )
            response.raise_for_status()
            data = response.json()

        employee_count: Optional[int] = data.get("metrics", {}).get("employees")
        description: str = data.get("description") or ""
        industry_text: str = data.get("category", {}).get("industry") or description

        return CompanyEnrichment(
            company_name=data.get("name", company_name),
            website=data.get("domain"),
            industry_segment=_classify_industry(industry_text),
            employee_count=employee_count,
            company_size=_classify_size(employee_count),
            founded_year=data.get("foundedYear"),
            headquarters=_format_location(data.get("geo", {})),
            description=description,
            recent_funding=None,  # Clearbit does not expose funding in free tier
            technologies=[t.get("tag", "") for t in data.get("tech", [])],
            source="clearbit",
        )
    except Exception:
        logger.warning(
            "Clearbit enrichment failed — falling back to mock", exc_info=True
        )
        return _mock_enrich(company_name)


def _format_location(geo: dict) -> Optional[str]:
    city = geo.get("city")
    state = geo.get("stateCode")
    country = geo.get("countryCode")
    parts = [p for p in [city, state] if p]
    if country and country != "US":
        parts.append(country)
    return ", ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def enrich_company(company_name: str) -> CompanyEnrichment:
    """
    Entry point for the agent tool. Chooses real vs mock path based on config.
    Always returns a CompanyEnrichment — never raises.
    """
    if not company_name or not company_name.strip():
        return CompanyEnrichment(company_name="unknown", source="mock")

    logger.info("enriching company", extra={"company": company_name})
    return _clearbit_enrich(company_name)
