import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ddgs import DDGS
from crawl4ai import AsyncWebCrawler
from core.config import settings
from core.logging import configure_logging, get_logger, log_event, log_exception
from core.observability import ls_traceable

configure_logging()
event_logger = get_logger(__name__)

root_logger = logging.getLogger()
if not any(getattr(handler, "_futurex_scraper_file", False) for handler in root_logger.handlers):
    scraper_file_handler = logging.FileHandler("scraper.log")
    scraper_file_handler._futurex_scraper_file = True
    scraper_file_handler.setLevel(logging.INFO)
    scraper_file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    root_logger.addHandler(scraper_file_handler)

LOG_DIR = "log"
NOISE_REMOVER_LOG_PATH = os.path.join(LOG_DIR, "noise_remover.log")
os.makedirs(LOG_DIR, exist_ok=True)

noise_remover_logger = logging.getLogger("noise_remover")
if not noise_remover_logger.handlers:
    noise_remover_logger.setLevel(logging.INFO)
    noise_remover_logger.propagate = False
    noise_remover_handler = logging.FileHandler(NOISE_REMOVER_LOG_PATH)
    noise_remover_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    noise_remover_logger.addHandler(noise_remover_handler)


def _safe_get_result_html(result: Any) -> str:
    for attr in ("html", "cleaned_html", "fit_html"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return ""


class ScrapeRunLogger:
    def __init__(self, conversation_id: str, idea: str):
        log_dir = Path(settings.scrape_run_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        full_log_dir = Path(settings.scraped_logx_dir)
        full_log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_conversation_id = _sanitize_filename(conversation_id or "unknown")
        safe_idea = _sanitize_filename(idea or "idea")[:80]
        filename = f"{timestamp}_{safe_conversation_id}_{safe_idea}.txt"
        full_text_filename = f"{safe_conversation_id}.txt"

        self.path = log_dir / filename
        self._fh = self.path.open("w", encoding="utf-8")
        self.full_text_path = full_log_dir / full_text_filename
        self._full_fh = self.full_text_path.open("w", encoding="utf-8")

    def write(self, text: str = "") -> None:
        self._fh.write(f"{text}\n")
        self._fh.flush()

    def write_full_text(self, text: str = "") -> None:
        self._full_fh.write(f"{text}\n")
        self._full_fh.flush()

    def section(self, title: str) -> None:
        self.write("=" * 100)
        self.write(title)
        self.write("=" * 100)

    def full_text_section(self, title: str) -> None:
        self.write_full_text("=" * 100)
        self.write_full_text(title)
        self.write_full_text("=" * 100)

    def close(self) -> None:
        self._fh.close()
        self._full_fh.close()


def _sanitize_filename(value: str) -> str:
    normalized = re.sub(r"\s+", "_", value.strip())
    normalized = re.sub(r"[^A-Za-z0-9._-]", "", normalized)
    return normalized or "run"


def create_scrape_run_logger(conversation_id: str, idea: str) -> ScrapeRunLogger:
    run_logger = ScrapeRunLogger(conversation_id=conversation_id, idea=idea)
    run_logger.section("SCRAPE RUN START")
    run_logger.write(f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}")
    run_logger.write(f"conversation_id: {conversation_id}")
    run_logger.write(f"idea: {idea}")
    run_logger.write(f"log_file: {run_logger.path}")
    run_logger.write("")
    run_logger.full_text_section("COMPLETE SCRAPED TEXT LOG START")
    run_logger.write_full_text(f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}")
    run_logger.write_full_text(f"conversation_id: {conversation_id}")
    run_logger.write_full_text(f"idea: {idea}")
    run_logger.write_full_text(f"log_file: {run_logger.full_text_path}")
    run_logger.write_full_text("")
    return run_logger


@ls_traceable(run_type="tool", name="ddgs_search", tags=["scraper", "ddgs"])
def ddgs_url_scrapper(query, run_logger: ScrapeRunLogger | None = None):
    logging.info(f"Searching DDGS for query: {query}")
    if run_logger:
        run_logger.section(f"DDGS QUERY: {query}")

    with DDGS() as ddgs:
        # Enforce in-en region so we get Indian/English market results
        results = list(ddgs.text(query, region="in-en" , max_results=10))

    urls = []
    for item in results:
        data = {
            "title": item["title"],
            "url": item["href"],
            "snippet": item["body"]
        }

        urls.append(data)

        logging.info(
            f"Found result | Title: {data['title']} | URL: {data['url']}"
        )
        if run_logger:
            run_logger.write(f"title: {data['title']}")
            run_logger.write(f"url: {data['url']}")
            run_logger.write(f"snippet: {data['snippet']}")
            run_logger.write("")

    return urls


def strip_links(text: str) -> str:
    """
    Remove all hyperlinks from markdown/crawled text so the LLM only
    receives clean prose.  Three passes:
      1. Markdown images  ![alt](url)  → removed entirely
      2. Markdown links   [text](url)  → kept as  text
      3. Bare URLs        http(s)://…  → removed
    """
    # 1. Remove markdown images completely
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # 2. Collapse markdown hyperlinks to their display text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # 3. Remove bare http / https URLs
    text = re.sub(r'https?://\S+', '', text)
    # 4. Remove common bare www URLs and domain-like tokens that survive markdown cleanup
    text = re.sub(r'\bwww\.\S+\b', '', text)
    text = re.sub(r'\b(?:[A-Za-z0-9-]+\.)+(?:com|in|co|ai|io|org|net|app|dev|tech|shop|store)\b(?:/\S*)?', '', text)
    return text


def basic_clean(text: str) -> str:
    text = re.sub(r"(?m)^\*\s.*$", "", text)
    text = re.sub(r"Privacy Overview.*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"(?m)^\|.*\|$", "", text)
    text = re.sub(r"\[\]\(.*?\)", "", text)
    return text.strip()


NOISE_LINE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^\s*(sign in|join|log in|login)\s*$",
        r"^\s*sign up\s*$",
        r"^\s*toggle child menu\s*$",
        r"^\s*toggle\s*$",
        r"^\s*search\s*$",
        r"^\s*read the news\s*$",
        r"^\s*loading\.\.\.\s*$",
        r"^\s*table of contents\s*$",
        r"^\s*interview shortcut\s*$",
        r"^\s*share on (facebook|twitter|linkedin|whatsapp).*$",
        r"^\s*tweet on twitter\s*$",
        r"^\s*whatsapp://send.*$",
        r"^\s*jki-facebook-light\s*$",
        r"^\s*status:\s*.*$",
        r"^\s*expand section\s*[↓-]?\s*$",
        r"^\s*also read\s*$",
        r"^\s*advertisement\s*$",
        r"^\s*(related articles|trending updates|latest updates|latest stories)\s*$",
        r"^\s*(follow us|subscribe|newsletter|social media follow)\s*$",
        r"^\s*(home|about|contact|privacy policy|terms of use)\s*$",
        r"^\s*(founder first|just in|in-focus|discover|stories|reports|brands|resources|ystv|events)\s*$",
        r"^\s*henof\s*$",
        r"^\s*back to the article list\s*$",
        r"^\s*google preferred\s*$",
        r"^\s*(timestamp_utc|conversation_id|url|log_file):.*$",
    ]
]

TRAILING_SECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^\s*#{1,6}\s*related\b.*$",
        r"^\s*#{1,6}\s*latest\b.*$",
        r"^\s*#{1,6}\s*trending\b.*$",
        r"^\s*#{1,6}\s*more from\b.*$",
        r"^\s*#{1,6}\s*recommended\b.*$",
        r"^\s*#{1,6}\s*you may also like\b.*$",
        r"^\s*#{1,6}\s*worth the attention\b.*$",
        r"^\s*#{1,6}\s*quick links\b.*$",
        r"^\s*#{1,6}\s*categories\b.*$",
        r"^\s*#{1,6}\s*ys buzz\b.*$",
        r"^\s*#{1,6}\s*follow us\b.*$",
        r"^\s*follow us\s*$",
        r"^\s*read our terms\b.*$",
        r"^\s*back to the article list\s*$",
        r"^\s*conclusion\s*$",
        r"^\s*references\s*$",
        r"^\s*copyright\s+©.*$",
        r"^\s*©\s*.*$",
    ]
]


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True

    if any(pattern.match(stripped) for pattern in NOISE_LINE_PATTERNS):
        return True

    if re.match(r"^\*?\s*\[[^\]]+\]\([^)]+\)\s*$", stripped):
        return True

    if re.match(r"^\*+\s*$", stripped):
        return True

    if re.match(r"^[#>*\-\s]{0,3}[A-Za-z0-9&+/_ -]{1,40}$", stripped):
        lowered = stripped.lower()
        if any(
            token in lowered
            for token in ("share", "menu", "search", "follow", "subscribe", "login", "sign in")
        ):
            return True

    return False


def _remove_ui_artifacts(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[\s*\]\([^)]+\)", "", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def extract_main_content(raw_html: str, fallback_text: str) -> str:
    if raw_html.strip():
        try:
            import trafilatura

            extracted = trafilatura.extract(
                raw_html,
                output_format="txt",
                include_links=False,
                include_images=False,
                include_formatting=False,
                favor_recall=True,
                deduplicate=True,
            )
            if extracted and len(extracted.strip()) >= 200:
                return extracted.strip()
        except Exception as exc:
            logging.warning("Trafilatura extraction failed, falling back to markdown cleanup: %s", exc)

    return fallback_text


def _looks_like_short_menu_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True

    words = stripped.split()
    if len(words) >= 3:
        return False

    if stripped.startswith("#"):
        return False

    if re.search(r"[.!?]\s*$", stripped):
        return False

    return True


def _drop_promo_link_runs(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) <= 120:
            j = i
            while (
                j < len(lines)
                and lines[j].strip().startswith("**")
                and lines[j].strip().endswith("**")
                and len(lines[j].strip()) <= 120
            ):
                j += 1
                if j < len(lines) and lines[j].strip().lower().startswith("by "):
                    j += 1
            if j - i >= 2:
                i = j
                continue
        cleaned.append(lines[i])
        i += 1
    return cleaned


def _truncate_at_sentence_boundary(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text.strip()

    candidate = text[:max_chars].rstrip()
    boundary_matches = list(re.finditer(r"(?<=[.!?])\s+", candidate))
    if boundary_matches:
        candidate = candidate[: boundary_matches[-1].end()].rstrip()
    else:
        newline_index = candidate.rfind("\n")
        if newline_index > max_chars * 0.6:
            candidate = candidate[:newline_index].rstrip()

    return candidate.strip()


def _drop_short_line_blocks(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        if _looks_like_short_menu_line(lines[i]):
            j = i
            short_count = 0
            while j < len(lines) and _looks_like_short_menu_line(lines[j]):
                short_count += 1
                j += 1
            if short_count >= 4:
                i = j
                continue
        cleaned.append(lines[i])
        i += 1
    return cleaned


def clean_scraped_text(text: str) -> str:
    text = _remove_ui_artifacts(text)
    raw_lines = [line.strip() for line in text.splitlines()]
    raw_lines = [line for line in raw_lines if line]

    first_h1_index = next(
        (idx for idx, line in enumerate(raw_lines) if re.match(r"^#\s+\S+", line)),
        None,
    )
    if first_h1_index is not None:
        raw_lines = raw_lines[first_h1_index:]

    cleaned_lines: list[str] = []
    for line in raw_lines:
        if any(pattern.match(line) for pattern in TRAILING_SECTION_PATTERNS):
            break

        if _is_noise_line(line):
            continue

        cleaned_lines.append(line)

    cleaned_lines = _drop_short_line_blocks(cleaned_lines)
    cleaned_lines = _drop_promo_link_runs(cleaned_lines)

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
    cleaned_text = re.sub(r"\n(?:\*\s*){3,}\n", "\n", cleaned_text)
    return cleaned_text.strip()


def extract_core(markdown: str, max_chars: int = 1500) -> str:
    """
    Strip boilerplate from a crawled page's markdown.
    Keeps only lines longer than 40 chars (skips nav/header noise),
    then returns the first 30 such lines joined together.
    """
    markdown = clean_scraped_text(markdown)
    lines = markdown.strip().splitlines()
    content_lines = [l for l in lines if len(l.strip()) > 40]
    selected_lines: list[str] = []
    current_length = 0
    for line in content_lines[:30]:
        projected_length = current_length + len(line) + (1 if selected_lines else 0)
        if selected_lines and projected_length > max_chars:
            break
        selected_lines.append(line)
        current_length = projected_length

    core = "\n".join(selected_lines) if selected_lines else "\n".join(content_lines[:30])
    core = _truncate_at_sentence_boundary(core, max_chars)
    return clean_scraped_text(core)


def _should_use_openrouter_cleaner(text: str) -> tuple[bool, str]:
    if not settings.OPENROUTER_LLM_CLEANER_ENABLED:
        return False, "disabled"

    if not settings.OPENROUTER_API_KEY:
        return False, "missing_key"

    stripped = text.strip()
    if len(stripped) < 250:
        return False, "too_short"

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if not lines:
        return False, "empty"

    short_lines = sum(1 for line in lines if len(line.split()) <= 3)
    heading_like_lines = sum(
        1
        for line in lines
        if len(line) <= 70 and not re.search(r"[.!?]\s*$", line)
    )
    repeated_lines = len(lines) - len(set(lines))

    suspicious_tokens = (
        "follow us",
        "related articles",
        "latest stories",
        "trending updates",
        "sign in",
        "sign up",
        "privacy policy",
        "terms of use",
        "advertisement",
        "expand section",
        "newsletter",
    )
    suspicious_hits = sum(stripped.lower().count(token) for token in suspicious_tokens)

    noise_score = 0
    if short_lines >= 4:
        noise_score += 1
    if heading_like_lines >= 6:
        noise_score += 1
    if repeated_lines >= 2:
        noise_score += 1
    if suspicious_hits >= 2:
        noise_score += 2

    if noise_score >= 2:
        return True, f"noisy_score_{noise_score}"

    return False, "clean_enough"


def _clean_with_openrouter(
    text: str,
    *,
    source_rank: int,
    openrouter_enabled_for_run: bool,
) -> tuple[str, str]:
    should_clean, reason = _should_use_openrouter_cleaner(text)
    if not should_clean:
        log_event(
            event_logger,
            "openrouter_cleaner_skipped",
            provider="openrouter",
            model=settings.OPENROUTER_MODEL_NAME,
            input_chars=len(text),
            reason=reason,
            source_rank=source_rank,
        )
        return text, f"skipped_{reason}"

    if not openrouter_enabled_for_run:
        log_event(
            event_logger,
            "openrouter_cleaner_skipped",
            provider="openrouter",
            model=settings.OPENROUTER_MODEL_NAME,
            input_chars=len(text),
            reason="run_disabled_after_slow_or_failed_call",
            source_rank=source_rank,
        )
        return text, "skipped_run_disabled_after_slow_or_failed_call"

    if source_rank > max(settings.OPENROUTER_LLM_CLEANER_MAX_SOURCES, 0):
        log_event(
            event_logger,
            "openrouter_cleaner_skipped",
            provider="openrouter",
            model=settings.OPENROUTER_MODEL_NAME,
            input_chars=len(text),
            reason="source_rank_limit",
            source_rank=source_rank,
        )
        return text, "skipped_source_rank_limit"

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            timeout=max(settings.OPENROUTER_LLM_CLEANER_TIMEOUT_SECONDS, 1),
        )
        trimmed_text = _truncate_at_sentence_boundary(
            text,
            settings.OPENROUTER_LLM_CLEANER_MAX_CHARS,
        )
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_NAME,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You clean scraped article text for downstream embeddings. "
                        "Remove leftover UI text, repeated phrases, and broken formatting. "
                        "Preserve meaning and important details. Do not summarize."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Clean this noisy text:\n\n{trimmed_text}",
                },
            ],
        )
        cleaned = response.choices[0].message.content or ""
        cleaned = cleaned.strip() or text
        log_event(
            event_logger,
            "openrouter_cleaner_success",
            provider="openrouter",
            model=settings.OPENROUTER_MODEL_NAME,
            input_chars=len(text),
            sent_chars=len(trimmed_text),
            output_chars=len(cleaned),
            reason=reason,
            source_rank=source_rank,
        )
        return cleaned, "success"
    except Exception as exc:
        log_exception(
            event_logger,
            "openrouter_cleaner_error",
            provider="openrouter",
            model=settings.OPENROUTER_MODEL_NAME,
            input_chars=len(text),
            reason=reason,
            error=str(exc),
            status="fallback_to_rule_based_cleaning",
            source_rank=source_rank,
        )
        return text, "fallback_to_rule_based_cleaning"


# Domains that rarely yield crawlable, meaningful content for market research
BLOCKED_DOMAINS = {"reddit.com", "zhihu.com", "quora.com"}


def filter_urls(urls: list, max_results: int = 6, run_logger: ScrapeRunLogger | None = None) -> list:
    """
    Remove results from low-value / uncrawlable domains and
    cap the list to max_results to keep crawl time reasonable.
    NOTE: Apply to general-query results only — Reddit results have
    their own dedicated search lane and should NOT be filtered here.
    """
    filtered = [
        u for u in urls
        if not any(domain in u["url"] for domain in BLOCKED_DOMAINS)
    ]
    logging.info(f"filter_urls: {len(urls)} → {len(filtered[:max_results])} URLs after filtering")
    if run_logger:
        run_logger.section("FILTERED URLS")
        run_logger.write(f"input_count: {len(urls)}")
        run_logger.write(f"returned_count: {len(filtered[:max_results])}")
        run_logger.write("")
        for item in filtered[:max_results]:
            run_logger.write(f"title: {item['title']}")
            run_logger.write(f"url: {item['url']}")
            run_logger.write(f"snippet: {item['snippet']}")
            run_logger.write("")
    return filtered[:max_results]


JUNK_SIGNALS = [
    "ERR_TIMED_OUT",
    "Log in to Reddit",
    "Log In to Reddit",
    "Get the Reddit app",
    "Go to Reddit Home",
    "Complete the challenge",
    "Enable JavaScript",
    "Please verify you are a human",
    "Access denied",
    "Subscribe to continue",
]


def is_useful_content(text: str) -> bool:
    """
    Returns False if the crawled page is too short or contains well-known
    junk signals (login walls, CAPTCHA pages, timeout errors).
    """
    if len(text.strip()) < 200:
        return False
    return not any(signal in text for signal in JUNK_SIGNALS)


def _is_reddit_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return "reddit.com" in hostname or "redd.it" in hostname


def _create_reddit_client():
    if not settings.REDDIT_CLIENT_ID or not settings.REDDIT_CLIENT_SECRET:
        raise ValueError("Reddit API credentials are not configured.")

    import praw

    return praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
    )


def _fetch_reddit_submission_text(url: str) -> tuple[str, dict[str, Any]]:
    reddit = _create_reddit_client()
    submission = reddit.submission(url=url)
    submission.comments.replace_more(limit=None)

    lines = [
        f"Subreddit: r/{submission.subreddit.display_name}",
        f"Title: {submission.title}",
        f"Author: {submission.author}",
        f"Score: {submission.score}",
        f"Upvote Ratio: {getattr(submission, 'upvote_ratio', 'n/a')}",
        f"Comment Count: {submission.num_comments}",
        "",
        "POST BODY:",
        submission.selftext or "[No selftext]",
        "",
        "ALL COMMENTS:",
    ]

    flattened_comments = submission.comments.list()
    for index, comment in enumerate(flattened_comments, start=1):
        author = getattr(comment.author, "name", "[deleted]") if comment.author else "[deleted]"
        body = (comment.body or "").strip()
        lines.extend(
            [
                f"Comment {index}",
                f"Author: {author}",
                f"Score: {comment.score}",
                f"Depth: {getattr(comment, 'depth', 0)}",
                body or "[deleted]",
                "",
            ]
        )

    metadata = {
        "subreddit": submission.subreddit.display_name,
        "title": submission.title,
        "comment_count": submission.num_comments,
        "expanded_comment_count": len(flattened_comments),
        "score": submission.score,
    }
    return "\n".join(lines).strip(), metadata


async def _fetch_reddit_submission_text_async(url: str) -> tuple[str, dict[str, Any]]:
    return await asyncio.wait_for(
        asyncio.to_thread(_fetch_reddit_submission_text, url),
        timeout=max(settings.REDDIT_PRAW_TIMEOUT_SECONDS, 1),
    )


def _apply_noise_remover(content_items: list[dict], seed_texts: list[str] | None) -> list[dict]:
    if not settings.NOISE_REMOVER_ENABLED:
        return content_items

    usable_seed_texts = [text.strip() for text in (seed_texts or []) if text and text.strip()]
    if not usable_seed_texts or not content_items:
        noise_remover_logger.info("Noise remover skipped: missing seed texts or content items")
        return content_items

    try:
        from noiseremover import ChunkFilter

        noise_remover_logger.info(
            "Noise remover starting | python=%s | model=%s | threshold=%.4f | items=%s",
            sys.executable,
            settings.NOISE_REMOVER_MODEL,
            settings.NOISE_REMOVER_THRESHOLD,
            len(content_items),
        )

        chunk_filter = ChunkFilter(
            threshold=settings.NOISE_REMOVER_THRESHOLD,
            model_name=settings.NOISE_REMOVER_MODEL,
        )
        chunk_filter.set_seed(usable_seed_texts)

        content_texts = [item["content"] for item in content_items]
        scored_texts = chunk_filter.score_texts(content_texts, show_progress_bar=False)

        scores_by_content = {text: score for text, score in scored_texts}
        filtered_items = []
        dropped_items = []

        for item in content_items:
            score = scores_by_content.get(item["content"], 0.0)
            if score >= settings.NOISE_REMOVER_THRESHOLD:
                filtered_items.append(item)
                noise_remover_logger.info(
                    "[NOISE_REMOVER][KEEP] score=%.4f | url=%s | title=%s | chunk=%s",
                    score,
                    item["url"],
                    item["title"],
                    item["content"][:500].replace("\n", " "),
                )
            else:
                dropped_items.append(item)
                noise_remover_logger.info(
                    "[NOISE_REMOVER][DROP] score=%.4f | url=%s | title=%s | chunk=%s",
                    score,
                    item["url"],
                    item["title"],
                    item["content"][:500].replace("\n", " "),
                )

        noise_remover_logger.info(
            "Noise remover kept %s/%s crawled items and dropped %s",
            len(filtered_items),
            len(content_items),
            len(dropped_items),
        )
        return filtered_items
    except Exception as exc:
        noise_remover_logger.warning(
            "Noise remover failed; returning unfiltered content. "
            "python=%s | model=%s | Error: %s",
            sys.executable,
            settings.NOISE_REMOVER_MODEL,
            exc,
        )
        return content_items


async def crawler_service(urls, seed_texts=None):
    return await crawler_service_with_logging(urls, seed_texts=seed_texts, run_logger=None)


@ls_traceable(run_type="tool", name="crawler_service_with_logging", tags=["scraper", "crawler"])
async def crawler_service_with_logging(
    urls: list[dict[str, Any]],
    seed_texts: list[str] | None = None,
    run_logger: ScrapeRunLogger | None = None,
):
    content_items = []
    openrouter_enabled_for_run = True
    if run_logger:
        run_logger.section("CRAWL INPUT")
        run_logger.write(f"url_count: {len(urls)}")
        run_logger.write(f"seed_texts: {seed_texts or []}")
        run_logger.write("")
    async with AsyncWebCrawler() as crawler:
        for index, item in enumerate(urls, start=1):
            title = item["title"]
            url = item["url"]

            print(f"\n=== {title} ===")
            print(f"URL: {url}\n")

            logging.info(f"Starting crawl for: {url}")
            if run_logger:
                run_logger.section(f"CRAWL START: {title}")
                run_logger.write(f"url: {url}")
                run_logger.write("")
                run_logger.full_text_section(f"SCRAPED TEXT: {title}")
                run_logger.write_full_text(f"url: {url}")
                run_logger.write_full_text("")

            try:
                if _is_reddit_url(url):
                    try:
                        reddit_text, reddit_meta = await _fetch_reddit_submission_text_async(url)
                        logging.info(
                            "Extracted Reddit post via PRAW: %s | expanded_comments=%s",
                            url,
                            reddit_meta["expanded_comment_count"],
                        )
                        if run_logger:
                            run_logger.write("REDDIT_EXTRACTION_METHOD: praw")
                            run_logger.write(f"subreddit: {reddit_meta['subreddit']}")
                            run_logger.write(f"expanded_comment_count: {reddit_meta['expanded_comment_count']}")
                            run_logger.write("FULL_REDDIT_POST_AND_COMMENTS:")
                            run_logger.write(reddit_text)
                            run_logger.write("")
                            run_logger.write_full_text("EXTRACTION_METHOD: praw")
                            run_logger.write_full_text(f"subreddit: {reddit_meta['subreddit']}")
                            run_logger.write_full_text(
                                f"expanded_comment_count: {reddit_meta['expanded_comment_count']}"
                            )
                            run_logger.write_full_text("FULL_REDDIT_POST_AND_COMMENTS:")
                            run_logger.write_full_text(reddit_text)
                            run_logger.write_full_text("")

                        content_items.append(
                            {
                                "title": title,
                                "url": url,
                                "content": reddit_text,
                            }
                        )
                        print("[REDDIT] Extracted via PRAW")
                        print("-" * 80)
                        continue
                    except Exception as reddit_exc:
                        log_exception(
                            event_logger,
                            "reddit_api_error",
                            url=url,
                            title=title,
                            extraction_method="praw",
                            fallback_method="crawler",
                            severity="error",
                            error=str(reddit_exc),
                        )
                        if run_logger:
                            run_logger.write("REDDIT_EXTRACTION_METHOD: praw_failed_fallback_to_crawler")
                            run_logger.write(f"error: {reddit_exc}")
                            run_logger.write("")
                            run_logger.write_full_text("EXTRACTION_METHOD: praw_failed_fallback_to_crawler")
                            run_logger.write_full_text(f"error: {reddit_exc}")
                            run_logger.write_full_text("")
                        if settings.REDDIT_SKIP_CRAWLER_FALLBACK:
                            logging.warning(
                                "Skipping Reddit URL after PRAW failure because REDDIT_SKIP_CRAWLER_FALLBACK is enabled: %s",
                                url,
                            )
                            if run_logger:
                                run_logger.write("STATUS: skipped_after_praw_failure")
                                run_logger.write("")
                                run_logger.write_full_text("STATUS: skipped_after_praw_failure")
                                run_logger.write_full_text("")
                            print(f"[REDDIT] Skipped after PRAW failure: {url}")
                            print("-" * 80)
                            continue
                        log_event(
                            event_logger,
                            "reddit_api_fallback",
                            url=url,
                            title=title,
                            extraction_method="praw",
                            fallback_method="crawler",
                            severity="error",
                            status="fallback_started",
                        )

                result = await asyncio.wait_for(
                    crawler.arun(url=url),
                    timeout=max(settings.CRAWLER_URL_TIMEOUT_SECONDS, 1),
                )

                markdown = result.markdown or ""
                raw_markdown = markdown
                raw_html = _safe_get_result_html(result)
                if run_logger:
                    run_logger.write("FULL_MARKDOWN_BEFORE_LINK_STRIP:")
                    run_logger.write(raw_markdown)
                    run_logger.write("")
                    run_logger.write_full_text("FULL_MARKDOWN_BEFORE_LINK_STRIP:")
                    run_logger.write_full_text(raw_markdown)
                    run_logger.write_full_text("")
                    if raw_html:
                        run_logger.write_full_text("RAW_HTML_BEFORE_EXTRACTION:")
                        run_logger.write_full_text(raw_html)
                        run_logger.write_full_text("")

                # Stage 1: extract the main article body before deeper cleaning
                markdown_without_links = strip_links(raw_markdown)
                extracted_main_content = extract_main_content(raw_html, markdown_without_links)
                pre_llm_cleaned = clean_scraped_text(basic_clean(strip_links(extracted_main_content)))
                if run_logger:
                    run_logger.write("FULL_MARKDOWN_AFTER_LINK_STRIP:")
                    run_logger.write(markdown_without_links)
                    run_logger.write("")
                    run_logger.write_full_text("FULL_MARKDOWN_AFTER_LINK_STRIP:")
                    run_logger.write_full_text(markdown_without_links)
                    run_logger.write_full_text("")
                    run_logger.full_text_section("RAW_VS_CLEANED_AFTER_LINK_STRIP")
                    run_logger.write_full_text("RAW_AFTER_LINK_STRIP:")
                    run_logger.write_full_text(markdown_without_links)
                    run_logger.write_full_text("")
                    run_logger.write_full_text("CLEANED_AFTER_LINK_STRIP:")
                    run_logger.write_full_text(pre_llm_cleaned)
                    run_logger.write_full_text("")
                    run_logger.write_full_text("TRAFILATURA_MAIN_CONTENT:")
                    run_logger.write_full_text(extracted_main_content)
                    run_logger.write_full_text("")

                markdown = pre_llm_cleaned

                # ── Early junk check on the FULL raw markdown ──────────────
                # Catches signals that appear outside the first 30 lines
                # (e.g. Reddit login walls buried deep in the page)
                if not is_useful_content(markdown):
                    logging.warning(f"[SKIP-EARLY] Junk page detected: {url}")
                    print(f"[SKIP] Junk page (early check): {url}")
                    if run_logger:
                        run_logger.write("STATUS: skipped_early_junk_check")
                        run_logger.write("")
                        run_logger.write_full_text("STATUS: skipped_early_junk_check")
                        run_logger.write_full_text("")
                    continue

                logging.info(
                    f"Successfully crawled: {url} | "
                    f"Markdown length: {len(markdown)}"
                )

                print(markdown[:1000])
                print("\n" + "-" * 80)

                # Stage 2: keep only the main body, then optionally let an LLM
                # do a final formatting cleanup after rule-based extraction.
                core_content = extract_core(markdown)
                llm_cleaned_content, llm_cleaner_status = _clean_with_openrouter(
                    core_content,
                    source_rank=index,
                    openrouter_enabled_for_run=openrouter_enabled_for_run,
                )
                if llm_cleaner_status == "fallback_to_rule_based_cleaning":
                    openrouter_enabled_for_run = False
                final_cleaned_content = clean_scraped_text(llm_cleaned_content)
                if run_logger:
                    run_logger.write("EXTRACTED_CORE_CONTENT:")
                    run_logger.write(core_content)
                    run_logger.write("")
                    run_logger.write(f"SOURCE_RANK: {index}")
                    run_logger.write("")
                    run_logger.write(f"OPENROUTER_LLM_CLEANER_STATUS: {llm_cleaner_status}")
                    run_logger.write("")
                    run_logger.write_full_text("EXTRACTED_CORE_CONTENT_USED_FOR_LLM:")
                    run_logger.write_full_text(core_content)
                    run_logger.write_full_text("")
                    run_logger.write_full_text(f"SOURCE_RANK: {index}")
                    run_logger.write_full_text("")
                    run_logger.write_full_text(f"OPENROUTER_LLM_CLEANER_STATUS: {llm_cleaner_status}")
                    run_logger.write_full_text("")
                    run_logger.write_full_text("POST_LLM_CLEANED_CONTENT:")
                    run_logger.write_full_text(final_cleaned_content)
                    run_logger.write_full_text("")
                    run_logger.full_text_section("RAW_VS_CLEANED_CORE_CONTENT")
                    run_logger.write_full_text("RAW_INPUT_TO_EXTRACT_CORE:")
                    run_logger.write_full_text(markdown)
                    run_logger.write_full_text("")
                    run_logger.write_full_text("FINAL_CORE_CONTENT_USED_FOR_LLM:")
                    run_logger.write_full_text(final_cleaned_content)
                    run_logger.write_full_text("")

                # ── Second quality check on the extracted core ─────────────
                # Catches pages that become too short after boilerplate removal
                if not is_useful_content(final_cleaned_content):
                    logging.warning(f"[SKIP-CORE] Low-quality core for: {url}")
                    print(f"[SKIP] Low-quality core content: {url}")
                    if run_logger:
                        run_logger.write("STATUS: skipped_low_quality_core")
                        run_logger.write("")
                        run_logger.write_full_text("STATUS: skipped_low_quality_core")
                        run_logger.write_full_text("")
                    continue

                logging.info(
                    f"Crawled content for {url}:\n{final_cleaned_content}"
                )
                if run_logger:
                    run_logger.write("STATUS: kept")
                    run_logger.write("")
                    run_logger.write_full_text("STATUS: kept")
                    run_logger.write_full_text("")

                content_items.append(
                    {
                        "title": title,
                        "url": url,
                        "content": final_cleaned_content,
                    }
                )

            except Exception as e:
                print(f"Failed to crawl {url}")
                print(e)

                logging.error(
                    f"Failed to crawl {url} | Error: {str(e)}",
                    exc_info=True
                )
                if run_logger:
                    if _is_reddit_url(url):
                        run_logger.write("REDDIT_EXTRACTION_METHOD: praw_failed_fallback_or_error")
                    run_logger.write("STATUS: crawl_error")
                    run_logger.write(f"error: {e}")
                    run_logger.write("")
                    if _is_reddit_url(url):
                        run_logger.write_full_text("EXTRACTION_METHOD: praw_failed_fallback_or_error")
                    run_logger.write_full_text("STATUS: crawl_error")
                    run_logger.write_full_text(f"error: {e}")
                    run_logger.write_full_text("")
                if _is_reddit_url(url):
                    log_exception(
                        event_logger,
                        "reddit_extraction_final_error",
                        url=url,
                        title=title,
                        extraction_method="praw_or_crawler",
                        severity="error",
                        error=str(e),
                    )

            print("-" * 80)

    content_items = _apply_noise_remover(content_items, seed_texts)

    content_results = [
        f"Source: {item['title']} ({item['url']})\nContent:\n{item['content']}"
        for item in content_items
    ]
    final_text = "\n\n---\n\n".join(content_results)
    if not final_text:
        final_text = "No relevant data found on the web."
    if run_logger:
        run_logger.full_text_section("FINAL_TEXT_SENT_DOWNSTREAM")
        run_logger.write_full_text(final_text)
        run_logger.write_full_text("")
        run_logger.full_text_section("COMPLETE SCRAPED TEXT LOG END")
        run_logger.section("FINAL_AGGREGATED_SEARCH_RESULTS")
        run_logger.write(final_text)
        run_logger.write("")
        run_logger.section("SCRAPE RUN END")
    return final_text


if __name__ == "__main__":
    logging.info("Program started")

    while True:
        query = input("Idea: ").strip()

        if query.lower() == "exit":
            logging.info("User exited program")
            break

        reddit_query = f"{query} site:reddit.com"

        try:
            urls = ddgs_url_scrapper(reddit_query)

            if not urls:
                print("No results found.")
                logging.warning(f"No results found for query: {reddit_query}")
                continue

            asyncio.run(crawler_service(urls))

        except Exception as e:
            print(f"Unexpected error: {e}")
            logging.error(
                f"Unexpected error for query '{reddit_query}': {str(e)}",
                exc_info=True
            )

        command = input("\nDo you want to continue? (yes/no): ").strip().lower()

        if command in ["no", "n", "exit"]:
            logging.info("User chose to stop")
            break

    logging.info("Program ended")
