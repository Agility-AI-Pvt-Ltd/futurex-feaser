from __future__ import annotations

from typing import Any

from core.json_utils import parse_json_from_text
from core.llm_factory import get_llm
from core.logging import get_logger
from project_reviewer.prompts import build_semantic_review_prompt

logger = get_logger(__name__)

CATEGORIES = [
    "readability",
    "maintainability",
    "architecture",
    "testing",
    "production_readiness",
    "scalability",
    "security",
    "industry_conventions",
]


def run_semantic_review(context: str, static_analysis: dict[str, Any]) -> dict[str, Any]:
    prompt = build_semantic_review_prompt(context)
    try:
        llm = get_llm(temperature=0.2)
        response = llm.invoke(prompt)
        content = response if isinstance(response, str) else getattr(response, "content", "")
        parsed = parse_json_from_text(content or "", expected_type=dict)
        return normalize_llm_review(parsed)
    except Exception as exc:
        logger.warning("project_reviewer.llm_review_failed: %s", exc, exc_info=True)
        return fallback_semantic_review(static_analysis, reason=str(exc))


def normalize_llm_review(value: dict[str, Any]) -> dict[str, Any]:
    scores = value.get("category_scores", {})
    normalized_scores = {
        category: _coerce_score(scores.get(category, 0))
        for category in CATEGORIES
    }
    findings = value.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    strengths = value.get("strengths", [])
    if not isinstance(strengths, list):
        strengths = []
    roadmap = value.get("improvement_roadmap", [])
    if not isinstance(roadmap, list):
        roadmap = []

    return {
        "category_scores": normalized_scores,
        "seniority_estimate": str(value.get("seniority_estimate") or "unknown"),
        "would_pass_strong_review": bool(value.get("would_pass_strong_review", False)),
        "summary": str(value.get("summary") or ""),
        "strengths": [str(item) for item in strengths[:10]],
        "findings": [_normalize_finding(item) for item in findings[:20] if isinstance(item, dict)],
        "improvement_roadmap": [str(item) for item in roadmap[:12]],
    }


def fallback_semantic_review(static_analysis: dict[str, Any], *, reason: str) -> dict[str, Any]:
    risk_flags = static_analysis.get("risk_flags", [])
    test_count = static_analysis.get("test_signals", {}).get("test_file_count", 0)
    security = static_analysis.get("security_signals", {})
    architecture = static_analysis.get("architecture_signals", {})

    scores = {category: 6 for category in CATEGORIES}
    if test_count == 0:
        scores["testing"] = 2
        scores["production_readiness"] = min(scores["production_readiness"], 4)
    if security.get("secret_matches") or security.get("env_files_committed"):
        scores["security"] = 2
        scores["production_readiness"] = min(scores["production_readiness"], 4)
    if architecture.get("controller_db_coupling"):
        scores["architecture"] = 4
        scores["maintainability"] = 4
    if static_analysis.get("feature_signals", {}).get("dummy_or_placeholder_signals"):
        scores["production_readiness"] = 3

    findings = [
        {
            "category": "static_analysis",
            "severity": "medium",
            "title": flag,
            "evidence": "Deterministic reviewer signal",
            "why_it_matters": "This signal usually prevents student code from passing a strong engineering review.",
            "recommendation": "Address the issue and add evidence through tests, clearer structure, or safer configuration.",
        }
        for flag in risk_flags[:8]
    ]
    if reason:
        findings.append(
            {
                "category": "llm",
                "severity": "low",
                "title": "Semantic LLM review was unavailable",
                "evidence": reason[:300],
                "why_it_matters": "The report used deterministic analysis only, so architecture judgment is less nuanced.",
                "recommendation": "Configure the LLM provider and rerun the review for deeper semantic feedback.",
            }
        )

    return {
        "category_scores": scores,
        "seniority_estimate": "junior",
        "would_pass_strong_review": False,
        "summary": "Deterministic review completed. The project needs stronger testing, configuration, and maintainability evidence before industry-level approval.",
        "strengths": ["Repository structure was readable enough for static inspection."],
        "findings": findings,
        "improvement_roadmap": [
            "Add meaningful tests for core features and edge cases.",
            "Separate API/controller code from business logic and persistence.",
            "Remove placeholder behavior and prove features with runnable checks.",
            "Harden configuration, secrets handling, errors, and logging.",
        ],
    }


def _normalize_finding(item: dict[str, Any]) -> dict[str, str]:
    return {
        "category": str(item.get("category") or "general"),
        "severity": str(item.get("severity") or "medium"),
        "title": str(item.get("title") or "Review finding"),
        "evidence": str(item.get("evidence") or ""),
        "why_it_matters": str(item.get("why_it_matters") or ""),
        "recommendation": str(item.get("recommendation") or ""),
    }


def _coerce_score(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = 0
    return max(0, min(10, score))
