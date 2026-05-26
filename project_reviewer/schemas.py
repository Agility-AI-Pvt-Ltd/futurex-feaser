from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


class GitHubReviewRequest(BaseModel):
    github_url: HttpUrl
    author_id: Optional[str] = None
    selected_repo: Optional[str] = None


class GitHubRepositoryListRequest(BaseModel):
    username: Optional[str] = None


class GitHubRepositoryOut(BaseModel):
    name: str
    full_name: str
    html_url: str
    private: bool = False
    default_branch: Optional[str] = None


class ProjectReviewReportOut(BaseModel):
    submission_id: int
    status: str
    source_type: str
    github_url: Optional[str] = None
    storage_backend: Optional[str] = None
    storage_bucket: Optional[str] = None
    storage_object_path: Optional[str] = None
    overall_score: int = 0
    readiness_level: str = "unknown"
    seniority_estimate: str = "unknown"
    would_pass_strong_review: bool = False
    summary: str = ""
    category_scores: dict[str, int] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvement_roadmap: list[str] = Field(default_factory=list)
    static_analysis: dict[str, Any] = Field(default_factory=dict)
    graph_trace: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class ProjectReviewListItem(BaseModel):
    submission_id: int
    status: str
    source_type: str
    github_url: Optional[str] = None
    overall_score: Optional[int] = None
    readiness_level: Optional[str] = None
    created_at: datetime
