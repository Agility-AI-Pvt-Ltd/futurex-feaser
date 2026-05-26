from __future__ import annotations

from typing import Any

WEIGHTS = {
    "readability": 0.12,
    "maintainability": 0.16,
    "architecture": 0.18,
    "testing": 0.14,
    "production_readiness": 0.16,
    "scalability": 0.08,
    "security": 0.08,
    "industry_conventions": 0.08,
}


def aggregate_verdict(static_analysis: dict[str, Any], llm_analysis: dict[str, Any]) -> dict[str, Any]:
    category_scores = {
        category: _score(llm_analysis.get("category_scores", {}).get(category, 0))
        for category in WEIGHTS
    }
    adjusted_scores = _apply_static_penalties(category_scores, static_analysis)
    overall_score = round(sum(adjusted_scores[category] * weight for category, weight in WEIGHTS.items()) * 10)
    readiness_level = _readiness_level(overall_score)
    would_pass = bool(llm_analysis.get("would_pass_strong_review")) and overall_score >= 75

    findings = list(llm_analysis.get("findings", []))
    for flag in static_analysis.get("risk_flags", []):
        if not _finding_exists(findings, flag):
            findings.append(
                {
                    "category": "deterministic_signal",
                    "severity": "medium",
                    "title": flag,
                    "evidence": "Static analysis signal",
                    "why_it_matters": "Strong code reviews expect this risk to be resolved or explicitly justified.",
                    "recommendation": "Fix the underlying issue and add tests or documentation that prove the behavior.",
                }
            )

    return {
        "overall_score": max(0, min(100, overall_score)),
        "readiness_level": readiness_level,
        "seniority_estimate": llm_analysis.get("seniority_estimate", "unknown"),
        "would_pass_strong_review": would_pass,
        "summary": llm_analysis.get("summary", ""),
        "category_scores": adjusted_scores,
        "findings": _rank_findings(findings)[:25],
        "strengths": llm_analysis.get("strengths", [])[:10],
        "improvement_roadmap": llm_analysis.get("improvement_roadmap", [])[:12],
        "static_analysis": static_analysis,
        "llm_analysis": llm_analysis,
    }


def _apply_static_penalties(scores: dict[str, int], static_analysis: dict[str, Any]) -> dict[str, int]:
    adjusted = dict(scores)
    tests = static_analysis.get("test_signals", {})
    security = static_analysis.get("security_signals", {})
    architecture = static_analysis.get("architecture_signals", {})
    features = static_analysis.get("feature_signals", {})
    python_metrics = static_analysis.get("python_metrics", {})
    spelling = static_analysis.get("spelling_signals", {})

    if tests.get("test_file_count", 0) == 0 and not tests.get("package_test_script"):
        adjusted["testing"] = min(adjusted["testing"], 3)
    if security.get("secret_matches") or security.get("env_files_committed"):
        adjusted["security"] = min(adjusted["security"], 3)
        adjusted["production_readiness"] = min(adjusted["production_readiness"], 5)
    if architecture.get("controller_db_coupling"):
        adjusted["architecture"] = min(adjusted["architecture"], 5)
        adjusted["maintainability"] = min(adjusted["maintainability"], 6)
    if features.get("dummy_or_placeholder_signals"):
        adjusted["production_readiness"] = min(adjusted["production_readiness"], 4)
    if python_metrics.get("worst_complexity"):
        adjusted["readability"] = min(adjusted["readability"], 7)
        adjusted["maintainability"] = min(adjusted["maintainability"], 7)
    if spelling.get("match_count", 0) > 0:
        adjusted["readability"] = min(adjusted["readability"], 7)

    return adjusted


def _readiness_level(score: int) -> str:
    if score >= 85:
        return "strong-company-ready"
    if score >= 70:
        return "reviewable-with-fixes"
    if score >= 50:
        return "student-prototype"
    return "not-industry-ready"


def _rank_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(
        findings,
        key=lambda item: severity_rank.get(str(item.get("severity", "medium")).lower(), 2),
    )


def _finding_exists(findings: list[dict[str, Any]], title: str) -> bool:
    normalized = title.strip().lower()
    return any(str(item.get("title", "")).strip().lower() == normalized for item in findings)


def _score(value: Any) -> int:
    try:
        return max(0, min(10, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0
