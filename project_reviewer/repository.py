from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from core.config import settings
from project_reviewer.storage import StoredArtifact, ensure_workdir_root, store_directory_snapshot

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".venv",
    "venv",
    ".uv-cache",
    ".crawl4ai-work",
    ".pycache_tmp",
    "project_reviewer_data",
    "project_reviewer_workdir",
}


@dataclass(frozen=True)
class RepositoryAcquisition:
    repository_path: str
    artifact: StoredArtifact | None
    file_count: int
    total_bytes: int


def is_supported_github_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        return parsed.netloc.lower() == "github.com" and bool(parsed.path.strip("/"))
    return bool(re.match(r"^git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$", url or ""))


def clean_github_url(url: str) -> str:
    value = (url or "").strip()
    if not is_supported_github_url(value):
        raise ValueError("Only GitHub repository URLs are supported.")
    if value.startswith("git@github.com:"):
        return value

    parsed = urlparse(value)
    path = parsed.path.strip("/")
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError("GitHub URL must include owner and repository name.")
    repo_path = "/".join(parts[:2])
    if repo_path.endswith(".git"):
        repo_path = repo_path[:-4]
    return f"https://github.com/{repo_path}.git"


def clone_github_repository(*, submission_id: int, github_url: str) -> RepositoryAcquisition:
    clone_url = clean_github_url(github_url)
    workdir = _fresh_submission_workdir(submission_id)
    target = workdir / "repo"

    command = [
        "git",
        "clone",
        "--depth",
        "1",
        "--filter=blob:none",
        clone_url,
        str(target),
    ]
    try:
        subprocess.run(
            command,
            cwd=str(workdir),
            check=True,
            capture_output=True,
            text=True,
            timeout=max(5, settings.PROJECT_REVIEWER_GIT_TIMEOUT_SECONDS),
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"Could not clone GitHub repository. {detail[:500]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub clone timed out.") from exc

    artifact = store_directory_snapshot(
        submission_id=submission_id,
        directory=target,
        file_name="github-source.zip",
    )
    file_count, total_bytes = count_source_files(target)
    return RepositoryAcquisition(str(target), artifact, file_count, total_bytes)


def extract_archive_repository(*, submission_id: int, archive_path: str) -> RepositoryAcquisition:
    archive = Path(archive_path).resolve()
    if not archive.is_file():
        raise ValueError("Uploaded code archive was not found.")
    if archive.suffix.lower() != ".zip":
        raise ValueError("Only .zip code archives are supported right now.")

    workdir = _fresh_submission_workdir(submission_id)
    target = workdir / "repo"
    target.mkdir(parents=True, exist_ok=True)
    _safe_extract_zip(archive, target)
    repo_root = _collapse_single_directory(target)
    file_count, total_bytes = count_source_files(repo_root)
    return RepositoryAcquisition(str(repo_root), None, file_count, total_bytes)


def count_source_files(repository_path: Path | str) -> tuple[int, int]:
    root = Path(repository_path)
    file_count = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_dir() or _is_ignored(path):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        file_count += 1
        total_bytes += size
    return file_count, total_bytes


def _fresh_submission_workdir(submission_id: int) -> Path:
    root = ensure_workdir_root()
    target = root / str(submission_id)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    return target


def _safe_extract_zip(archive_path: Path, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Archive contains an unsafe path: {member.filename}")
            destination = (target_root / member.filename).resolve()
            try:
                destination.relative_to(target_root)
            except ValueError as exc:
                raise ValueError(f"Archive contains an unsafe path: {member.filename}") from exc
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def _collapse_single_directory(path: Path) -> Path:
    entries = [entry for entry in path.iterdir() if entry.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return path


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts) or path.name.startswith(".DS_Store")
