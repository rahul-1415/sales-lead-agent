"""
ICP similarity search using Voyage AI multimodal embeddings.

Primary: voyage-multimodal-3.5 → voyage-multimodal-3 (fallback order).
If VOYAGE_API_KEY is unset or any API call fails, falls back to Jaccard
keyword similarity over normalised word sets (stdlib only, zero deps).
"""

import logging
import math
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

# Voyage model preference order
_VOYAGE_MODELS = ["voyage-multimodal-3.5", "voyage-multimodal-3"]

# ---------------------------------------------------------------------------
# Jaccard fallback (stdlib)
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "in",
    "on",
    "at",
    "to",
    "of",
    "with",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "has",
    "have",
    "its",
    "it",
    "this",
    "that",
    "across",
    "uses",
    "use",
    "recently",
}


def _tokenise(text: str) -> set[str]:
    words = re.sub(r"[^\w\s]", "", text.lower()).split()
    return {w for w in words if w not in _STOP_WORDS and len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Cosine similarity (for embedding vectors)
# ---------------------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Voyage AI client — initialised once at cold start
# ---------------------------------------------------------------------------

_voyage_client = None
_voyage_model: Optional[str] = None  # whichever model responded successfully


def _init_voyage() -> bool:
    """Try to initialise Voyage AI client. Returns True on success."""
    global _voyage_client, _voyage_model

    try:
        from config import get_settings

        api_key = get_settings().voyage_api_key
        if not api_key:
            logger.info("VOYAGE_API_KEY not set — using Jaccard similarity")
            return False

        import voyageai

        client = voyageai.Client(api_key=api_key)

        # Probe models in preference order with a short test input
        for model in _VOYAGE_MODELS:
            try:
                client.embed(["test"], model=model, input_type="document")
                _voyage_client = client
                _voyage_model = model
                logger.info("Voyage AI ready", extra={"model": model})
                return True
            except Exception as e:
                logger.warning(
                    "Voyage model unavailable", extra={"model": model, "error": str(e)}
                )

        logger.warning("No Voyage model available — falling back to Jaccard")
        return False

    except ImportError:
        logger.info("voyageai package not installed — using Jaccard similarity")
        return False
    except Exception as e:
        logger.warning(
            "Voyage AI init failed — using Jaccard similarity", extra={"error": str(e)}
        )
        return False


def _voyage_embed(texts: list[str], input_type: str) -> Optional[list[list[float]]]:
    """Return embeddings via Voyage AI, or None on any failure."""
    if _voyage_client is None or _voyage_model is None:
        return None
    try:
        result = _voyage_client.embed(texts, model=_voyage_model, input_type=input_type)
        return result.embeddings
    except Exception as e:
        logger.warning(
            "Voyage embed call failed — falling back to Jaccard",
            extra={"error": str(e)},
        )
        return None


# ---------------------------------------------------------------------------
# Index — built once at cold start
# ---------------------------------------------------------------------------

# Voyage index: list of (company, embedding_vector)
_voyage_index: list[tuple[str, list[float]]] = []
# Jaccard index: list of (company, token_set)
_jaccard_index: list[tuple[str, set[str]]] = []
_index_built = False


def build_icp_index() -> None:
    global _voyage_index, _jaccard_index, _index_built

    # Always build the Jaccard index (free fallback)
    _jaccard_index = [
        (ex["company"], _tokenise(f"{ex['company']} {ex['description']}"))
        for ex in _ICP_EXAMPLES
    ]

    # Attempt Voyage index
    if _init_voyage():
        texts = [f"{ex['company']} {ex['description']}" for ex in _ICP_EXAMPLES]
        embeddings = _voyage_embed(texts, input_type="document")
        if embeddings:
            _voyage_index = list(
                zip([ex["company"] for ex in _ICP_EXAMPLES], embeddings)
            )
            logger.info(
                "ICP Voyage index ready",
                extra={"model": _voyage_model, "count": len(_voyage_index)},
            )
        else:
            logger.warning("Voyage embed returned None — Jaccard index active")
    else:
        logger.info("ICP Jaccard index ready", extra={"count": len(_jaccard_index)})

    _index_built = True


def _ensure_index() -> None:
    if not _index_built:
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

    query_text = f"{company_name} {description}"

    # --- Voyage path ---
    if _voyage_index:
        query_emb = _voyage_embed([query_text], input_type="query")
        if query_emb:
            scored = [
                (_cosine(query_emb[0], icp_emb), icp_company)
                for icp_company, icp_emb in _voyage_index
            ]
            scored.sort(reverse=True)
            return [
                SimilarityResult(
                    matched_company=company,
                    similarity_score=round(sim, 4),
                    match_reason=f"Semantic similarity ({_voyage_model}): {sim:.2%}",
                )
                for sim, company in scored[:top_k]
                if sim > 0
            ]

    # --- Jaccard fallback ---
    query_tokens = _tokenise(query_text)
    scored = [
        (_jaccard(query_tokens, icp_tokens), icp_company)
        for icp_company, icp_tokens in _jaccard_index
    ]
    scored.sort(reverse=True)
    return [
        SimilarityResult(
            matched_company=company,
            similarity_score=round(sim, 4),
            match_reason=f"Keyword similarity (Jaccard): {sim:.2%}",
        )
        for sim, company in scored[:top_k]
        if sim > 0
    ]


def top_similarity_score(results: list[SimilarityResult]) -> float:
    if not results:
        return 0.0
    return max(r.similarity_score for r in results)
