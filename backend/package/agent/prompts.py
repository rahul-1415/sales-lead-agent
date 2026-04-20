from agent.models import CompanyEnrichment, ScoreBreakdown, SimilarityResult


def build_reasoning_prompt(
    company: str,
    enrichment: CompanyEnrichment,
    score_breakdown: ScoreBreakdown,
    similarity_results: list[SimilarityResult],
    email_valid: bool,
) -> str:
    """
    Constructs the user-turn prompt sent to Groq for final lead reasoning.
    All structured data is in the user turn; the system prompt stays static.
    """
    sim_block = ""
    if similarity_results:
        lines = "\n".join(
            f"  - {r.matched_company}: {r.similarity_score:.0%} similarity"
            for r in similarity_results
        )
        sim_block = f"\nSimilar ICP companies found:\n{lines}"

    funding_line = (
        f"Recent funding: {enrichment.recent_funding}"
        if enrichment.recent_funding
        else "No recent funding on record."
    )

    tech_line = (
        f"Tech stack: {', '.join(enrichment.technologies)}"
        if enrichment.technologies
        else "Tech stack: unknown"
    )

    return f"""You are evaluating a B2B sales lead for an enterprise workflow automation company.

Lead: {company}
Description: {enrichment.description or "No description available."}
Industry: {enrichment.industry_segment}
Size: {enrichment.company_size} ({enrichment.employee_count or "unknown"} employees)
Location: {enrichment.headquarters or "unknown"}
{funding_line}
{tech_line}
Contact email valid: {email_valid}

Score breakdown (0–1 scale):
  Industry fit:       {score_breakdown.industry_fit:.2f}
  Company size fit:   {score_breakdown.company_size_fit:.2f}
  Geographic fit:     {score_breakdown.geographic_fit:.2f}
  Recent activity:    {score_breakdown.recent_activity:.2f}
  ICP similarity:     {score_breakdown.similarity_to_icp:.2f}
  Weighted total:     {score_breakdown.weighted_total:.2f}
{sim_block}

In 2–3 sentences explain WHY this lead scored the way it did and what the sales team \
should do next. Be specific — reference the company's industry, size, funding, or tech \
stack. Do not restate the numbers."""


SYSTEM_PROMPT = """You are a senior sales analyst at an enterprise software company. \
Your job is to write concise, accurate reasoning for lead scores so sales reps understand \
exactly why a lead is worth pursuing or not. Be direct and specific. Never invent facts \
not present in the context."""
