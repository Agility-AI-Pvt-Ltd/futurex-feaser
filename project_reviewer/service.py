from __future__ import annotations

import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import ProjectReviewCodeArtifact, ProjectReviewReport, ProjectReviewSubmission
from project_reviewer.graph import reviewer_app
from project_reviewer.schemas import GitHubReviewRequest, ProjectReviewListItem, ProjectReviewReportOut
from project_reviewer.storage import ensure_storage_root, store_bytes


def run_github_review(db: Session, request: GitHubReviewRequest) -> ProjectReviewReportOut:
    submission = ProjectReviewSubmission(
        author_id=request.author_id,
        source_type="github_url",
        github_url=str(request.github_url),
        selected_repo=request.selected_repo,
        status="running",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    reviewer_app.invoke(
        {
            "submission_id": submission.id,
            "source_type": "github_url",
            "github_url": str(request.github_url),
            "selected_repo": request.selected_repo,
            "graph_trace": [],
            "errors": [],
        }
    )
    db.expire_all()
    return get_report_out(db, submission.id)


def run_uploaded_archive_review(
    db: Session,
    *,
    file_name: str,
    content: bytes,
    author_id: str | None = None,
) -> ProjectReviewReportOut:
    if not file_name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip code archives are supported.")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded archive is empty.")

    submission = ProjectReviewSubmission(
        author_id=author_id,
        source_type="uploaded_archive",
        status="running",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    stored = store_bytes(submission_id=submission.id, file_name=file_name, content=content)
    local_archive = stored.local_path or _write_incoming_archive(submission.id, file_name, content)
    submission.storage_backend = stored.backend
    submission.storage_bucket = stored.bucket_name
    submission.storage_object_path = stored.object_path
    db.add(
        ProjectReviewCodeArtifact(
            submission_id=submission.id,
            artifact_type="uploaded_archive",
            storage_backend=stored.backend,
            bucket_name=stored.bucket_name,
            object_path=stored.object_path,
            file_count=0,
            total_bytes=stored.total_bytes,
        )
    )
    db.commit()

    reviewer_app.invoke(
        {
            "submission_id": submission.id,
            "source_type": "uploaded_archive",
            "archive_path": local_archive,
            "storage_backend": stored.backend,
            "storage_bucket": stored.bucket_name,
            "storage_object_path": stored.object_path,
            "graph_trace": [],
            "errors": [],
        }
    )
    db.expire_all()
    return get_report_out(db, submission.id)


def get_report_out(db: Session, submission_id: int) -> ProjectReviewReportOut:
    submission = db.query(ProjectReviewSubmission).filter_by(id=submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Project review submission not found.")
    report = submission.report
    return _to_report_out(submission, report)


def list_report_items(db: Session, *, limit: int = 50, offset: int = 0) -> list[ProjectReviewListItem]:
    rows = (
        db.query(ProjectReviewSubmission)
        .order_by(ProjectReviewSubmission.created_at.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [
        ProjectReviewListItem(
            submission_id=row.id,
            status=row.status,
            source_type=row.source_type,
            github_url=row.github_url,
            overall_score=row.report.overall_score if row.report else None,
            readiness_level=row.report.readiness_level if row.report else None,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _to_report_out(
    submission: ProjectReviewSubmission,
    report: ProjectReviewReport | None,
) -> ProjectReviewReportOut:
    if not report:
        return ProjectReviewReportOut(
            submission_id=submission.id,
            status=submission.status,
            source_type=submission.source_type,
            github_url=submission.github_url,
            storage_backend=submission.storage_backend,
            storage_bucket=submission.storage_bucket,
            storage_object_path=submission.storage_object_path,
            summary=submission.error_message or "",
            created_at=submission.created_at,
        )

    return ProjectReviewReportOut(
        submission_id=submission.id,
        status=submission.status,
        source_type=submission.source_type,
        github_url=submission.github_url,
        storage_backend=submission.storage_backend,
        storage_bucket=submission.storage_bucket,
        storage_object_path=submission.storage_object_path,
        overall_score=report.overall_score,
        readiness_level=report.readiness_level,
        seniority_estimate=report.seniority_estimate,
        would_pass_strong_review=report.would_pass_strong_review,
        summary=report.summary,
        category_scores=report.category_scores or {},
        findings=report.findings or [],
        strengths=report.strengths or [],
        improvement_roadmap=report.improvement_roadmap or [],
        static_analysis=report.static_analysis or {},
        graph_trace=report.graph_trace or [],
        created_at=report.created_at,
    )


def _write_incoming_archive(submission_id: int, file_name: str, content: bytes) -> str:
    incoming_dir = ensure_storage_root() / "_incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file_name).name or "source.zip"
    path = incoming_dir / f"{submission_id}-{datetime.datetime.utcnow().timestamp()}-{safe_name}"
    path.write_bytes(content)
    return str(path)
