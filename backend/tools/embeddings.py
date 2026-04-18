"""
Embedding-based similarity search.

Architecture:
  - Company descriptions are embedded using the Anthropic Embeddings API
    (or a local sentence-transformers model for offline dev).
  - Embeddings for known "ideal" customers (ICP examples) are stored in
    DynamoDB / an in-memory index at startup.
  - At runtime, a new lead's description is embedded and compared against
    the ICP index using cosine similarity.
  - The similarity score feeds into ScoreBreakdown.similarity_to_icp.

This is the RAG component of the system — retrieving the most similar
known-good leads gives the LLM grounding for its final reasoning step.
"""

import logging
import math
from typing import Optional

import anthropic

from agent.models import SimilarityResult
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# ICP seed examples — embedded once at module load
# The agent scores new leads by similarity to these known good fits.
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

# Module-level cache: list of (company_name, embedding_vector)
_icp_index: list[tuple[str, list[float]]] = []


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _embed(text: str) -> list[float]:
    """
    Calls the Anthropic Embeddings API.
    Falls back to a deterministic pseudo-embedding in local mode so the
    system runs end-to-end without an API key during development.
    """
    if settings.is_local and not settings.anthropic_api_key:
        return _pseudo_embed(text)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.embeddings.create(
        model="voyage-2",
        input=[text],
    )
    return response.embeddings[0].values


def _pseudo_embed(text: str) -> list[float]:
    """
    Deterministic character-frequency vector — useful for local dev and tests.
    Not semantically meaningful, but preserves the pipeline interface.
    """
    vec = [0.0] * 128
    for i, ch in enumerate(text.lower()):
        vec[ord(ch) % 128] += 1.0
    magnitude = math.sqrt(sum(x ** 2 for x in vec)) or 1.0
    return [x / magnitude for x in vec]


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def build_icp_index() -> None:
    """
    Embeds all ICP examples and caches them in memory.
    Called once at Lambda cold start (or app startup in local dev).
    """
    global _icp_index
    logger.info("building ICP embedding index", extra={"count": len(_ICP_EXAMPLES)})
    _icp_index = []
    for example in _ICP_EXAMPLES:
        text = f"{example['company']}. {example['description']}"
        try:
            vector = _embed(text)
            _icp_index.append((example["company"], vector))
        except Exception:
            logger.warning(
                "failed to embed ICP example",
                extra={"company": example["company"]},
                exc_info=True,
            )
    logger.info("ICP index ready", extra={"indexed": len(_icp_index)})


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
    """
    Embeds the incoming lead's description and returns the top-k most similar
    ICP examples with their cosine similarity scores.

    Used by the orchestrator to populate ScoreBreakdown.similarity_to_icp
    and to give the LLM concrete comparisons in its reasoning prompt.
    """
    _ensure_index()

    if not description:
        logger.debug("no description — skipping similarity search", extra={"company": company_name})
        return []

    text = f"{company_name}. {description}"
    try:
        query_vector = _embed(text)
    except Exception:
        logger.warning("embedding failed for lead", extra={"company": company_name}, exc_info=True)
        return []

    scored: list[tuple[float, str]] = []
    for icp_company, icp_vector in _icp_index:
        if len(query_vector) != len(icp_vector):
            continue
        sim = _cosine_similarity(query_vector, icp_vector)
        scored.append((sim, icp_company))

    scored.sort(reverse=True)

    return [
        SimilarityResult(
            matched_company=company,
            similarity_score=round(sim, 4),
            match_reason=f"Embedding cosine similarity: {sim:.2%}",
        )
        for sim, company in scored[:top_k]
    ]


def top_similarity_score(results: list[SimilarityResult]) -> float:
    """Extracts the highest similarity score for use in ScoreBreakdown."""
    if not results:
        return 0.0
    return max(r.similarity_score for r in results)
