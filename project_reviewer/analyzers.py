from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from core.config import settings
from project_reviewer.repository import IGNORED_DIRS

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".html": "html",
    ".css": "css",
    ".scss": "css",
    ".sql": "sql",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
}

TEXT_SUFFIXES = set(LANGUAGE_BY_SUFFIX) | {
    ".toml",
    ".ini",
    ".env",
    ".example",
    ".txt",
    ".dockerfile",
}

IMPORTANT_FILES = {
    "readme.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "dockerfile",
    "docker-compose.yml",
    "compose.yml",
    ".env.example",
    "alembic.ini",
    "manage.py",
    "app.py",
    "main.py",
}

COMMON_TYPOS = {
    "recieve",
    "seperate",
    "occured",
    "teh",
    "adress",
    "enviroment",
    "authentification",
    "succes",
    "responce",
    "databse",
    "databasee",
    "funtion",
    "lenght",
}

SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "generic_secret_assignment": re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"\n]{12,}['\"]"
    ),
    "database_url_with_password": re.compile(r"(?i)\b(postgres|mysql|mongodb)://[^:\s]+:[^@\s]+@"),
}


def build_repository_inventory(repository_path: str) -> dict[str, Any]:
    root = Path(repository_path).resolve()
    files: list[dict[str, Any]] = []
    language_counts: Counter[str] = Counter()
    total_bytes = 0

    for path in sorted(root.rglob("*")):
        if path.is_dir() or _is_ignored(path):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        relative = path.relative_to(root).as_posix()
        language = language_for_path(path)
        files.append({"path": relative, "bytes": size, "language": language})
        language_counts[language] += 1
        total_bytes += size
        if len(files) >= max(1, settings.PROJECT_REVIEWER_MAX_FILES):
            break

    key_files = [item["path"] for item in files if Path(item["path"]).name.lower() in IMPORTANT_FILES]
    return {
        "root": str(root),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "language_counts": dict(language_counts),
        "primary_language": language_counts.most_common(1)[0][0] if language_counts else "unknown",
        "key_files": key_files[:50],
        "files": files,
        "truncated": len(files) >= max(1, settings.PROJECT_REVIEWER_MAX_FILES),
    }


def run_static_analysis(repository_path: str, inventory: dict[str, Any]) -> dict[str, Any]:
    root = Path(repository_path).resolve()
    file_items = inventory.get("files", [])
    python_metrics = _analyze_python_files(root, file_items)
    feature_signals = _detect_feature_signals(root, file_items)
    security_signals = _scan_security(root, file_items)
    test_signals = _detect_testing(root, file_items)
    architecture_signals = _detect_architecture(root, file_items)
    git_signals = _inspect_git_history(root)
    spelling_signals = _scan_common_typos(root, file_items)

    return {
        "summary": {
            "file_count": inventory.get("file_count", 0),
            "total_bytes": inventory.get("total_bytes", 0),
            "primary_language": inventory.get("primary_language", "unknown"),
            "languages": inventory.get("language_counts", {}),
        },
        "python_metrics": python_metrics,
        "feature_signals": feature_signals,
        "security_signals": security_signals,
        "test_signals": test_signals,
        "architecture_signals": architecture_signals,
        "git_signals": git_signals,
        "spelling_signals": spelling_signals,
        "risk_flags": _derive_risk_flags(
            python_metrics=python_metrics,
            feature_signals=feature_signals,
            security_signals=security_signals,
            test_signals=test_signals,
            architecture_signals=architecture_signals,
            git_signals=git_signals,
            spelling_signals=spelling_signals,
        ),
    }


def language_for_path(path: Path) -> str:
    name = path.name.lower()
    if name in {"dockerfile", "makefile"}:
        return name
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "other")


def read_text_limited(path: Path, *, max_bytes: int | None = None) -> str:
    limit = max_bytes or settings.PROJECT_REVIEWER_MAX_FILE_BYTES
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def is_text_file(path: Path) -> bool:
    if path.name.lower() in IMPORTANT_FILES:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def _analyze_python_files(root: Path, file_items: list[dict[str, Any]]) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    worst_complexity: list[dict[str, Any]] = []

    for item in file_items:
        if item.get("language") != "python":
            continue
        relative = item["path"]
        path = root / relative
        text = read_text_limited(path)
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            modules.append({"path": relative, "syntax_error": str(exc)})
            totals["syntax_errors"] += 1
            continue

        visitor = PythonMetricsVisitor()
        visitor.visit(tree)
        module_metrics = {
            "path": relative,
            "functions": visitor.functions,
            "classes": visitor.classes,
            "imports": sorted(visitor.imports),
            "try_blocks": visitor.try_blocks,
            "bare_excepts": visitor.bare_excepts,
            "max_nesting": visitor.max_nesting,
            "high_complexity_functions": visitor.high_complexity_functions,
            "lines": len(text.splitlines()),
        }
        modules.append(module_metrics)
        totals["functions"] += len(visitor.functions)
        totals["classes"] += len(visitor.classes)
        totals["try_blocks"] += visitor.try_blocks
        totals["bare_excepts"] += visitor.bare_excepts
        totals["lines"] += module_metrics["lines"]
        worst_complexity.extend(visitor.high_complexity_functions)

    return {
        "module_count": len(modules),
        "totals": dict(totals),
        "modules": modules[:80],
        "worst_complexity": sorted(
            worst_complexity,
            key=lambda item: item.get("complexity", 0),
            reverse=True,
        )[:20],
    }


class PythonMetricsVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: list[str] = []
        self.classes: list[str] = []
        self.imports: set[str] = set()
        self.try_blocks = 0
        self.bare_excepts = 0
        self.max_nesting = 0
        self._nesting = 0
        self.high_complexity_functions: list[dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node)

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        if node.module:
            self.imports.add(node.module.split(".")[0])

    def visit_Try(self, node: ast.Try) -> Any:
        self.try_blocks += 1
        for handler in node.handlers:
            if handler.type is None:
                self.bare_excepts += 1
        self._visit_nested(node)

    def visit_If(self, node: ast.If) -> Any:
        self._visit_nested(node)

    def visit_For(self, node: ast.For) -> Any:
        self._visit_nested(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> Any:
        self._visit_nested(node)

    def visit_While(self, node: ast.While) -> Any:
        self._visit_nested(node)

    def visit_With(self, node: ast.With) -> Any:
        self._visit_nested(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> Any:
        self._visit_nested(node)

    def _visit_function(self, node: ast.AST) -> None:
        name = getattr(node, "name", "<unknown>")
        self.functions.append(name)
        complexity = estimate_python_complexity(node)
        if complexity >= 10:
            self.high_complexity_functions.append(
                {
                    "name": name,
                    "line": getattr(node, "lineno", None),
                    "complexity": complexity,
                }
            )
        self.generic_visit(node)

    def _visit_nested(self, node: ast.AST) -> None:
        self._nesting += 1
        self.max_nesting = max(self.max_nesting, self._nesting)
        self.generic_visit(node)
        self._nesting -= 1


def estimate_python_complexity(node: ast.AST) -> int:
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.With, ast.AsyncWith)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(1, len(child.values) - 1)
        elif isinstance(child, ast.comprehension):
            complexity += 1
    return complexity


def _detect_feature_signals(root: Path, file_items: list[dict[str, Any]]) -> dict[str, Any]:
    features: defaultdict[str, list[str]] = defaultdict(list)
    route_patterns = [
        re.compile(r"@\w+\.(get|post|put|patch|delete)\("),
        re.compile(r"\b(app|router)\.(get|post|put|patch|delete)\("),
        re.compile(r"\b(express|router)\.(get|post|put|patch|delete)\("),
    ]
    ui_patterns = [re.compile(r"\bfunction\s+[A-Z]\w+\("), re.compile(r"\bconst\s+[A-Z]\w+\s*=")]

    for item in file_items:
        path = root / item["path"]
        if not is_text_file(path):
            continue
        text = read_text_limited(path)
        if any(pattern.search(text) for pattern in route_patterns):
            features["api_routes"].append(item["path"])
        if "useState(" in text or "useEffect(" in text or any(pattern.search(text) for pattern in ui_patterns):
            features["frontend_components"].append(item["path"])
        if re.search(r"\b(fetch|axios|requests\.|httpx\.)\b", text):
            features["external_calls"].append(item["path"])
        if re.search(r"\bTODO\b|\bFIXME\b|dummy|placeholder|mock data", text, re.IGNORECASE):
            features["dummy_or_placeholder_signals"].append(item["path"])
        if re.search(r"\b(cron|celery|rq|bull|worker|queue)\b", text, re.IGNORECASE):
            features["background_jobs"].append(item["path"])

    return {key: sorted(set(value))[:40] for key, value in features.items()}


def _scan_security(root: Path, file_items: list[dict[str, Any]]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    env_files: list[str] = []

    for item in file_items:
        path = root / item["path"]
        lower_name = path.name.lower()
        if lower_name == ".env":
            env_files.append(item["path"])
        if not is_text_file(path):
            continue
        text = read_text_limited(path)
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                matches.append({"path": item["path"], "type": name})
                break

    return {
        "secret_matches": matches[:30],
        "env_files_committed": env_files[:20],
        "has_env_example": any(Path(item["path"]).name.lower() == ".env.example" for item in file_items),
    }


def _detect_testing(root: Path, file_items: list[dict[str, Any]]) -> dict[str, Any]:
    test_files = [
        item["path"]
        for item in file_items
        if _looks_like_test_file(item["path"])
    ]
    package_json = _read_json_file(root / "package.json")
    scripts = package_json.get("scripts", {}) if isinstance(package_json, dict) else {}
    has_pytest = (root / "pytest.ini").exists() or "pytest" in read_text_limited(root / "requirements.txt", max_bytes=20_000)
    has_ci = any(Path(item["path"]).parts[0:1] == (".github",) for item in file_items)

    return {
        "test_file_count": len(test_files),
        "test_files": test_files[:60],
        "package_test_script": scripts.get("test") if isinstance(scripts, dict) else None,
        "has_pytest_signal": bool(has_pytest),
        "has_ci_config": bool(has_ci),
    }


def _detect_architecture(root: Path, file_items: list[dict[str, Any]]) -> dict[str, Any]:
    top_level_dirs = sorted(
        {
            Path(item["path"]).parts[0]
            for item in file_items
            if len(Path(item["path"]).parts) > 1
        }
    )
    db_usage_files: list[str] = []
    controller_db_coupling: list[str] = []
    config_files: list[str] = []

    for item in file_items:
        path = root / item["path"]
        if not is_text_file(path):
            continue
        text = read_text_limited(path)
        if re.search(r"\b(sqlalchemy|mongoose|prisma|psycopg2|sqlite3|mysql|postgres|mongodb)\b", text, re.IGNORECASE):
            db_usage_files.append(item["path"])
            if re.search(r"\b(route|controller|view|handler|api)\b", item["path"], re.IGNORECASE):
                controller_db_coupling.append(item["path"])
        if "os.environ" in text or "process.env" in text or "BaseSettings" in text:
            config_files.append(item["path"])

    return {
        "top_level_dirs": top_level_dirs[:80],
        "db_usage_files": sorted(set(db_usage_files))[:50],
        "controller_db_coupling": sorted(set(controller_db_coupling))[:50],
        "config_files": sorted(set(config_files))[:50],
        "has_layered_dirs": any(name in top_level_dirs for name in {"api", "core", "services", "models", "domain", "repositories"}),
    }


def _inspect_git_history(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {"has_git": False, "commit_count": 0, "branch_count": 0, "notes": ["No git history found in submitted code."]}

    return {
        "has_git": True,
        "commit_count": _git_int(root, ["git", "rev-list", "--count", "HEAD"]),
        "branch_count": _git_branch_count(root),
        "latest_commit": _git_text(root, ["git", "log", "-1", "--pretty=%h %s"]),
    }


def _scan_common_typos(root: Path, file_items: list[dict[str, Any]]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for item in file_items:
        path = root / item["path"]
        if not is_text_file(path):
            continue
        text = read_text_limited(path, max_bytes=50_000).lower()
        found = sorted({typo for typo in COMMON_TYPOS if typo in text})
        if found:
            matches.append({"path": item["path"], "words": found[:8]})
    return {"matches": matches[:30], "match_count": len(matches)}


def _derive_risk_flags(**signals: Any) -> list[str]:
    flags: list[str] = []
    python_metrics = signals["python_metrics"]
    security = signals["security_signals"]
    tests = signals["test_signals"]
    architecture = signals["architecture_signals"]
    features = signals["feature_signals"]
    git = signals["git_signals"]
    spelling = signals["spelling_signals"]

    if security.get("secret_matches") or security.get("env_files_committed"):
        flags.append("Sensitive configuration or secrets may be committed.")
    if tests.get("test_file_count", 0) == 0 and not tests.get("package_test_script"):
        flags.append("No meaningful automated testing signal was found.")
    if architecture.get("controller_db_coupling"):
        flags.append("Database access appears coupled to controller/API files.")
    if features.get("dummy_or_placeholder_signals"):
        flags.append("Dummy, placeholder, or TODO signals appear in functional code.")
    if python_metrics.get("totals", {}).get("bare_excepts", 0) > 0:
        flags.append("Bare exception handling hides failure modes.")
    if python_metrics.get("worst_complexity"):
        flags.append("Some functions have high cyclomatic complexity.")
    if not git.get("has_git"):
        flags.append("No git metadata was submitted, so history discipline cannot be verified.")
    if spelling.get("match_count", 0) > 0:
        flags.append("Common spelling mistakes were found in code or identifiers.")
    return flags


def _looks_like_test_file(path: str) -> bool:
    lower = path.lower()
    return (
        lower.startswith("tests/")
        or "/tests/" in lower
        or lower.endswith("_test.py")
        or lower.endswith("test.py")
        or lower.endswith(".test.js")
        or lower.endswith(".spec.js")
        or lower.endswith(".test.ts")
        or lower.endswith(".spec.ts")
        or lower.endswith(".test.tsx")
        or lower.endswith(".spec.tsx")
    )


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(read_text_limited(path, max_bytes=100_000))
    except Exception:
        return {}


def _git_text(root: Path, command: list[str]) -> str:
    try:
        result = subprocess.run(command, cwd=str(root), check=True, capture_output=True, text=True, timeout=5)
    except Exception:
        return ""
    return result.stdout.strip()


def _git_int(root: Path, command: list[str]) -> int:
    try:
        return int(_git_text(root, command) or "0")
    except ValueError:
        return 0


def _git_branch_count(root: Path) -> int:
    output = _git_text(root, ["git", "branch", "-a"])
    return len([line for line in output.splitlines() if line.strip()])


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)
