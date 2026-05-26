from __future__ import annotations

import datetime
from typing import Any

from langgraph.graph import END, START, StateGraph

from core.config import settings
from core.database import SessionLocal
from core.observability import ls_traceable
from models import ProjectReviewCodeArtifact, ProjectReviewReport, ProjectReviewSubmission
from project_reviewer.analyzers import build_repository_inventory, run_static_analysis
from project_reviewer.context_builder import build_llm_context
from project_reviewer.llm_review import run_semantic_review
from project_reviewer.repository import clone_github_repository, extract_archive_repository
from project_reviewer.scoring import aggregate_verdict
from project_reviewer.state import ReviewState


def build_graph():
    workflow = StateGraph(ReviewState)
    workflow.add_node("prepare_submission", prepare_submission_node)
    workflow.add_node("acquire_repository", acquire_repository_node)
    workflow.add_node("inventory_repository", inventory_repository_node)
    workflow.add_node("static_analysis", static_analysis_node)
    workflow.add_node("runtime_assessment", runtime_assessment_node)
    workflow.add_node("context_builder", context_builder_node)
    workflow.add_node("llm_semantic_review", llm_semantic_review_node)
    workflow.add_node("verdict_aggregator", verdict_aggregator_node)
    workflow.add_node("persist_report", persist_report_node)

    workflow.add_edge(START, "prepare_submission")
    workflow.add_edge("prepare_submission", "acquire_repository")
    workflow.add_edge("acquire_repository", "inventory_repository")
    workflow.add_edge("inventory_repository", "static_analysis")
    workflow.add_edge("static_analysis", "runtime_assessment")
    workflow.add_edge("runtime_assessment", "context_builder")
    workflow.add_edge("context_builder", "llm_semantic_review")
    workflow.add_edge("llm_semantic_review", "verdict_aggregator")
    workflow.add_edge("verdict_aggregator", "persist_report")
    workflow.add_edge("persist_report", END)
    return workflow.compile()


@ls_traceable(run_type="tool", name="reviewer_prepare_submission", tags=["project_reviewer", "node"])
def prepare_submission_node(state: ReviewState) -> dict[str, Any]:
    updates = _with_trace(state, "prepare_submission", "completed")
    return updates


@ls_traceable(run_type="tool", name="reviewer_acquire_repository", tags=["project_reviewer", "node"])
def acquire_repository_node(state: ReviewState) -> dict[str, Any]:
    if state.get("errors"):
        return _with_trace(state, "acquire_repository", "skipped")

    try:
        source_type = state.get("source_type")
        if source_type == "github_url":
            acquisition = clone_github_repository(
                submission_id=state["submission_id"],
                github_url=state.get("github_url") or "",
            )
        elif source_type == "uploaded_archive":
            acquisition = extract_archive_repository(
                submission_id=state["submission_id"],
                archive_path=state.get("archive_path") or "",
            )
        else:
            raise ValueError(f"Unsupported project review source_type: {source_type}")

        updates: dict[str, Any] = {
            "repository_path": acquisition.repository_path,
        }
        if acquisition.artifact:
            updates.update(
                {
                    "storage_backend": acquisition.artifact.backend,
                    "storage_bucket": acquisition.artifact.bucket_name,
                    "storage_object_path": acquisition.artifact.object_path,
                }
            )
            _record_artifact(
                submission_id=state["submission_id"],
                backend=acquisition.artifact.backend,
                bucket_name=acquisition.artifact.bucket_name,
                object_path=acquisition.artifact.object_path,
                file_count=acquisition.file_count,
                total_bytes=acquisition.total_bytes,
            )
        return updates | _with_trace(state, "acquire_repository", "completed")
    except Exception as exc:
        return _error(state, "acquire_repository", exc)


@ls_traceable(run_type="tool", name="reviewer_inventory_repository", tags=["project_reviewer", "node"])
def inventory_repository_node(state: ReviewState) -> dict[str, Any]:
    if state.get("errors") or not state.get("repository_path"):
        return _with_trace(state, "inventory_repository", "skipped")
    try:
        inventory = build_repository_inventory(state["repository_path"])
        return {"inventory": inventory} | _with_trace(state, "inventory_repository", "completed")
    except Exception as exc:
        return _error(state, "inventory_repository", exc)


@ls_traceable(run_type="tool", name="reviewer_static_analysis", tags=["project_reviewer", "node"])
def static_analysis_node(state: ReviewState) -> dict[str, Any]:
    if state.get("errors") or not state.get("repository_path"):
        return _with_trace(state, "static_analysis", "skipped")
    try:
        static_analysis = run_static_analysis(
            state["repository_path"],
            state.get("inventory", {}),
        )
        return {"static_analysis": static_analysis} | _with_trace(state, "static_analysis", "completed")
    except Exception as exc:
        return _error(state, "static_analysis", exc)


@ls_traceable(run_type="tool", name="reviewer_runtime_assessment", tags=["project_reviewer", "node"])
def runtime_assessment_node(state: ReviewState) -> dict[str, Any]:
    static_analysis = dict(state.get("static_analysis", {}))
    runtime_signals = {
        "enabled": bool(settings.PROJECT_REVIEWER_RUNTIME_SANDBOX_ENABLED),
        "executed": False,
        "notes": [
            "Untrusted student code execution is disabled. This node records runtime readiness signals only."
        ],
    }
    static_analysis["runtime_signals"] = runtime_signals
    return {"static_analysis": static_analysis} | _with_trace(state, "runtime_assessment", "completed")


@ls_traceable(run_type="tool", name="reviewer_context_builder", tags=["project_reviewer", "node"])
def context_builder_node(state: ReviewState) -> dict[str, Any]:
    if state.get("errors") or not state.get("repository_path"):
        return _with_trace(state, "context_builder", "skipped")
    try:
        context = build_llm_context(
            state["repository_path"],
            state.get("inventory", {}),
            state.get("static_analysis", {}),
        )
        return {"context": context} | _with_trace(state, "context_builder", "completed")
    except Exception as exc:
        return _error(state, "context_builder", exc)


@ls_traceable(run_type="tool", name="reviewer_llm_semantic_review", tags=["project_reviewer", "node"])
def llm_semantic_review_node(state: ReviewState) -> dict[str, Any]:
    if state.get("errors"):
        return _with_trace(state, "llm_semantic_review", "skipped")
    llm_analysis = run_semantic_review(
        state.get("context", ""),
        state.get("static_analysis", {}),
    )
    return {"llm_analysis": llm_analysis} | _with_trace(state, "llm_semantic_review", "completed")


@ls_traceable(run_type="tool", name="reviewer_verdict_aggregator", tags=["project_reviewer", "node"])
def verdict_aggregator_node(state: ReviewState) -> dict[str, Any]:
    if state.get("errors"):
        return _with_trace(state, "verdict_aggregator", "skipped")
    verdict = aggregate_verdict(
        state.get("static_analysis", {}),
        state.get("llm_analysis", {}),
    )
    return {"verdict": verdict} | _with_trace(state, "verdict_aggregator", "completed")


@ls_traceable(run_type="tool", name="reviewer_persist_report", tags=["project_reviewer", "node"])
def persist_report_node(state: ReviewState) -> dict[str, Any]:
    db = SessionLocal()
    try:
        submission = db.query(ProjectReviewSubmission).filter_by(id=state["submission_id"]).first()
        if not submission:
            raise ValueError(f"Submission {state['submission_id']} not found.")

        if state.get("storage_backend"):
            submission.storage_backend = state.get("storage_backend")
            submission.storage_bucket = state.get("storage_bucket")
            submission.storage_object_path = state.get("storage_object_path")

        if state.get("errors"):
            submission.status = "failed"
            submission.error_message = "; ".join(state.get("errors", []))[:2000]
        else:
            verdict = state.get("verdict", {})
            report = submission.report or ProjectReviewReport(submission_id=submission.id)
            report.overall_score = int(verdict.get("overall_score", 0))
            report.readiness_level = str(verdict.get("readiness_level", "unknown"))
            report.seniority_estimate = str(verdict.get("seniority_estimate", "unknown"))
            report.would_pass_strong_review = bool(verdict.get("would_pass_strong_review", False))
            report.summary = str(verdict.get("summary", ""))
            report.category_scores = verdict.get("category_scores", {})
            report.findings = verdict.get("findings", [])
            report.strengths = verdict.get("strengths", [])
            report.improvement_roadmap = verdict.get("improvement_roadmap", [])
            report.static_analysis = verdict.get("static_analysis", {})
            report.llm_analysis = verdict.get("llm_analysis", {})
            report.graph_trace = state.get("graph_trace", [])
            submission.status = "completed"
            submission.error_message = None
            db.add(report)

        submission.updated_at = datetime.datetime.utcnow()
        db.commit()
        return _with_trace(state, "persist_report", "completed")
    except Exception as exc:
        db.rollback()
        return _error(state, "persist_report", exc)
    finally:
        db.close()


def get_graph_mermaid() -> str:
    graph = reviewer_app.get_graph()
    try:
        return graph.draw_mermaid()
    except Exception:
        return "graph TD\n  start --> prepare_submission --> acquire_repository --> inventory_repository --> static_analysis --> runtime_assessment --> context_builder --> llm_semantic_review --> verdict_aggregator --> persist_report --> end"


def _record_artifact(
    *,
    submission_id: int,
    backend: str,
    bucket_name: str | None,
    object_path: str,
    file_count: int,
    total_bytes: int,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            ProjectReviewCodeArtifact(
                submission_id=submission_id,
                artifact_type="source_archive",
                storage_backend=backend,
                bucket_name=bucket_name,
                object_path=object_path,
                file_count=file_count,
                total_bytes=total_bytes,
            )
        )
        submission = db.query(ProjectReviewSubmission).filter_by(id=submission_id).first()
        if submission:
            submission.storage_backend = backend
            submission.storage_bucket = bucket_name
            submission.storage_object_path = object_path
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _with_trace(state: ReviewState, node: str, status: str) -> dict[str, Any]:
    trace = list(state.get("graph_trace", []))
    trace.append({"node": node, "status": status, "timestamp": datetime.datetime.utcnow().isoformat()})
    return {"graph_trace": trace}


def _error(state: ReviewState, node: str, exc: Exception) -> dict[str, Any]:
    errors = list(state.get("errors", []))
    errors.append(f"{node}: {exc}")
    trace_update = _with_trace(state, node, "failed")
    return {"errors": errors, **trace_update}


reviewer_app = build_graph()
