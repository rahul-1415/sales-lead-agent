"""
Embedding-based similarity search using fastembed.

fastembed uses ONNX Runtime instead of PyTorch, making it Lambda-compatible:
  - Package size: ~40 MB model + ~15 MB library (fits in Lambda ZIP)
  - No GPU required, fast CPU inference
  - Model: BAAI/bge-small-en-v1.5 — 384-dim, strong quality/size tradeoff

Architecture:
  - ICP seed examples are embedded once at Lambda cold start via build_icp_index()
  - Vectors are cached in memory — free on warm invocations
  - At runtime, a new lead's description is embedded and compared via cosine similarity
  - The top score feeds into ScoreBreakdown.similarity_to_icp
"""

import logging
import math
from typing import Optional

from fastembed import TextEmbedding

from agent.models import SimilarityResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model — loaded once per Lambda container lifetime
# ---------------------------------------------------------------------------

_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_embedding_model: Optional[TextEmbedding] = None


def _get_model() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        logger.info("loading fastembed model", extra={"model": _MODEL_NAME})
        _embedding_model = TextEmbedding(model_name=_MODEL_NAME)
        logger.info("fastembed model ready")
    return _embedding_model


def _embed(text: str) -> list[float]:
    model = _get_model()
    vectors = list(model.embed([text]))
    return vectors[0].tolist()


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

_icp_index: list[tuple[str, list[float]]] = []


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def build_icp_index() -> None:
    """
    Embeds all ICP examples and caches vectors in memory.
    Called once at Lambda cold start — free on every warm invocation after.
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
    Embeds the incoming lead description and returns the top-k most similar
    ICP examples by cosine similarity.
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

    scored = [
        (_cosine_similarity(query_vector, icp_vec), icp_company)
        for icp_company, icp_vec in _icp_index
    ]
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
    if not results:
        return 0.0
    return max(r.similarity_score for r in results)
