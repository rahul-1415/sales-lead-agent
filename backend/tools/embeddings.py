"""
Keyword-based ICP similarity search (stdlib only — no onnxruntime/fastembed).

Uses Jaccard similarity over normalised word sets. Sufficient for lead scoring
demos and keeps the Lambda ZIP well under the 250 MB unzipped limit.
"""

import logging
import re
from typing import Optional

from agent.models import SimilarityResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ICP seed examples
# ---------------------------------------------------------------------------

_ICP_EXAMPLES: list[dict] = [
    {
        "company": "Apex Freight Solutions",
        "description": (
            "Mid-market logistics company specialising in last-mile freight "
            "and warehouse management across the US midwest. Uses SAP TMS."
        ),
    },
    {
        "company": "MedCore Systems",
        "description": (
            "Healthcare technology provider building workflow automation tools "
            "for hospital supply chains and clinical operations."
        ),
    },
    {
        "company": "Ironbridge Manufacturing",
        "description": (
            "Enterprise contract manufacturer with facilities in Ohio and Texas. "
            "Recently raised Series B to expand ERP capabilities."
        ),
    },
    {
        "company": "TradeLink Global",
        "description": (
            "International trade and customs brokerage firm serving enterprise "
            "importers. Heavy document-processing workflow requirements."
        ),
    },
]

# Stop words excluded from keyword matching
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "for", "in", "on", "at", "to", "of",
    "with", "by", "is", "are", "was", "were", "be", "been", "has", "have",
    "its", "it", "this", "that", "across", "uses", "use", "recently",
}


def _tokenise(text: str) -> set[str]:
    words = re.sub(r"[^\w\s]", "", text.lower()).split()
    return {w for w in words if w not in _STOP_WORDS and len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Index — pre-tokenised ICP examples (built once at startup)
# ---------------------------------------------------------------------------

_icp_index: list[tuple[str, set[str]]] = []


def build_icp_index() -> None:
    global _icp_index
    _icp_index = [
        (ex["company"], _tokenise(f"{ex['company']} {ex['description']}"))
        for ex in _ICP_EXAMPLES
    ]
    logger.info("ICP keyword index ready", extra={"count": len(_icp_index)})


def _ensure_index() -> None:
    if not _icp_index:
        build_icp_index()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def find_similar_leads(
    company_name: str,
    description: Optional[str],
    top_k: int = 3,
) -> list[SimilarityResult]:
    _ensure_index()

    if not description:
        return []

    query_tokens = _tokenise(f"{company_name} {description}")

    scored = [
        (_jaccard(query_tokens, icp_tokens), icp_company)
        for icp_company, icp_tokens in _icp_index
    ]
    scored.sort(reverse=True)

    return [
        SimilarityResult(
            matched_company=company,
            similarity_score=round(sim, 4),
            match_reason=f"Keyword similarity: {sim:.2%}",
        )
        for sim, company in scored[:top_k]
        if sim > 0
    ]


def top_similarity_score(results: list[SimilarityResult]) -> float:
    if not results:
        return 0.0
    return max(r.similarity_score for r in results)
