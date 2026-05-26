from __future__ import annotations

import requests
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from api.dependencies import enforce_api_rate_limit, get_db
from project_reviewer.graph import get_graph_mermaid
from project_reviewer.schemas import (
    GitHubRepositoryListRequest,
    GitHubRepositoryOut,
    GitHubReviewRequest,
    ProjectReviewListItem,
    ProjectReviewReportOut,
)
from project_reviewer.service import get_report_out, list_report_items, run_github_review, run_uploaded_archive_review

router = APIRouter(
    prefix="/project-reviewer",
    tags=["Project Reviewer"],
    dependencies=[Depends(enforce_api_rate_limit)],
)


@router.post("/github-url", response_model=ProjectReviewReportOut)
def review_github_url(payload: GitHubReviewRequest, db: Session = Depends(get_db)):
    return run_github_review(db, payload)


@router.post("/upload", response_model=ProjectReviewReportOut)
async def review_uploaded_archive(
    file: UploadFile = File(...),
    author_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Archive filename is required.")
    content = await file.read()
    return run_uploaded_archive_review(
        db,
        file_name=file.filename,
        content=content,
        author_id=author_id,
    )


@router.get("/reports", response_model=list[ProjectReviewListItem])
def list_project_review_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return list_report_items(db, limit=limit, offset=offset)


@router.get("/reports/{submission_id}", response_model=ProjectReviewReportOut)
def get_project_review_report(submission_id: int, db: Session = Depends(get_db)):
    return get_report_out(db, submission_id)


@router.post("/github/repositories", response_model=list[GitHubRepositoryOut])
def list_github_repositories(
    payload: GitHubRepositoryListRequest,
    github_token: str | None = Header(default=None, alias="X-GitHub-Token"),
):
    return _list_github_repositories(payload, github_token=github_token)


@router.get("/graph", response_model=str)
def project_reviewer_graph():
    return get_graph_mermaid()


def _list_github_repositories(
    payload: GitHubRepositoryListRequest,
    *,
    github_token: str | None,
) -> list[GitHubRepositoryOut]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
        url = "https://api.github.com/user/repos"
        params = {"per_page": 100, "sort": "updated"}
    elif payload.username:
        url = f"https://api.github.com/users/{payload.username}/repos"
        params = {"per_page": 100, "sort": "updated"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either a public GitHub username or X-GitHub-Token header.",
        )

    try:
        response = requests.get(url, headers=headers, params=params, timeout=8)
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="GitHub is temporarily unavailable.") from exc

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="GitHub token is invalid.")
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text[:500])

    repos = response.json()
    if not isinstance(repos, list):
        raise HTTPException(status_code=502, detail="Unexpected GitHub API response.")

    return [
        GitHubRepositoryOut(
            name=str(repo.get("name") or ""),
            full_name=str(repo.get("full_name") or ""),
            html_url=str(repo.get("html_url") or ""),
            private=bool(repo.get("private", False)),
            default_branch=repo.get("default_branch"),
        )
        for repo in repos
    ]
