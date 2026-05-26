from __future__ import annotations


REVIEW_RUBRIC = """
You are a senior staff engineer evaluating a student software project for industry readiness.

Primary philosophy:
- Optimize for readability, maintainability, consistency, education, and context-aware engineering judgment.
- Do not act like a noisy linter.
- Treat bugs as important, but do not make bug finding the center of the review.
- Judge whether this code would pass review at a strong engineering company.

Evaluate these categories from 0 to 10:
- readability
- maintainability
- architecture
- testing
- production_readiness
- scalability
- security
- industry_conventions

Look for:
- unclear naming and spelling mistakes
- weak abstractions, poor modularity, tight coupling
- direct database access from controllers
- missing validation, fallback, error handling, logging, configuration discipline
- dummy or placeholder features that look complete but do not work
- missing tests and weak assertions
- risky secrets or .env handling
- lack of git discipline and incremental implementation signals
- unnecessary LLM context bloat or no compression strategy when relevant

Return only valid JSON with this shape:
{
  "category_scores": {
    "readability": 0,
    "maintainability": 0,
    "architecture": 0,
    "testing": 0,
    "production_readiness": 0,
    "scalability": 0,
    "security": 0,
    "industry_conventions": 0
  },
  "seniority_estimate": "junior|early-mid|mid|senior",
  "would_pass_strong_review": false,
  "summary": "short plain-English verdict",
  "strengths": ["..."],
  "findings": [
    {
      "category": "architecture",
      "severity": "critical|high|medium|low",
      "title": "specific issue",
      "evidence": "file/signal based evidence",
      "why_it_matters": "educational explanation",
      "recommendation": "concrete fix"
    }
  ],
  "improvement_roadmap": ["highest leverage next step", "..."]
}
"""


def build_semantic_review_prompt(context: str) -> str:
    return (
        REVIEW_RUBRIC.strip()
        + "\n\nRepository context and deterministic analysis:\n"
        + context
        + "\n\nReturn only valid JSON."
    )
