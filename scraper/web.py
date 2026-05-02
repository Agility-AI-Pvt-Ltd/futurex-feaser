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


class ScrapeRunLogger:
    def __init__(self, conversation_id: str, idea: str):
        log_dir = Path(settings.scrape_run_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_conversation_id = _sanitize_filename(conversation_id or "unknown")
        safe_idea = _sanitize_filename(idea or "idea")[:80]
        filename = f"{timestamp}_{safe_conversation_id}_{safe_idea}.txt"

        self.path = log_dir / filename
        self._fh = self.path.open("w", encoding="utf-8")

    def write(self, text: str = "") -> None:
        self._fh.write(f"{text}\n")
        self._fh.flush()

    def section(self, title: str) -> None:
        self.write("=" * 100)
        self.write(title)
        self.write("=" * 100)

    def close(self) -> None:
        self._fh.close()


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
    return run_logger


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
    return text


def extract_core(markdown: str, max_chars: int = 1500) -> str:
    """
    Strip boilerplate from a crawled page's markdown.
    Keeps only lines longer than 40 chars (skips nav/header noise),
    then returns the first 30 such lines joined together.
    """
    lines = markdown.strip().splitlines()
    content_lines = [l for l in lines if len(l.strip()) > 40]
    core = "\n".join(content_lines[:30])
    # Hard cap — safety net for very dense pages
    return core[:max_chars]


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


async def crawler_service_with_logging(
    urls: list[dict[str, Any]],
    seed_texts: list[str] | None = None,
    run_logger: ScrapeRunLogger | None = None,
):
    content_items = []
    if run_logger:
        run_logger.section("CRAWL INPUT")
        run_logger.write(f"url_count: {len(urls)}")
        run_logger.write(f"seed_texts: {seed_texts or []}")
        run_logger.write("")
    async with AsyncWebCrawler() as crawler:
        for item in urls:
            title = item["title"]
            url = item["url"]

            print(f"\n=== {title} ===")
            print(f"URL: {url}\n")

            logging.info(f"Starting crawl for: {url}")
            if run_logger:
                run_logger.section(f"CRAWL START: {title}")
                run_logger.write(f"url: {url}")
                run_logger.write("")

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
                        if settings.REDDIT_SKIP_CRAWLER_FALLBACK:
                            logging.warning(
                                "Skipping Reddit URL after PRAW failure because REDDIT_SKIP_CRAWLER_FALLBACK is enabled: %s",
                                url,
                            )
                            if run_logger:
                                run_logger.write("STATUS: skipped_after_praw_failure")
                                run_logger.write("")
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
                if run_logger:
                    run_logger.write("FULL_MARKDOWN_BEFORE_LINK_STRIP:")
                    run_logger.write(markdown)
                    run_logger.write("")

                # Strip all links before any further processing
                markdown = strip_links(markdown)
                if run_logger:
                    run_logger.write("FULL_MARKDOWN_AFTER_LINK_STRIP:")
                    run_logger.write(markdown)
                    run_logger.write("")

                # ── Early junk check on the FULL raw markdown ──────────────
                # Catches signals that appear outside the first 30 lines
                # (e.g. Reddit login walls buried deep in the page)
                if not is_useful_content(markdown):
                    logging.warning(f"[SKIP-EARLY] Junk page detected: {url}")
                    print(f"[SKIP] Junk page (early check): {url}")
                    if run_logger:
                        run_logger.write("STATUS: skipped_early_junk_check")
                        run_logger.write("")
                    continue

                logging.info(
                    f"Successfully crawled: {url} | "
                    f"Markdown length: {len(markdown)}"
                )

                print(markdown[:1000])
                print("\n" + "-" * 80)

                # Extract meaningful content (strip boilerplate)
                core_content = extract_core(markdown)
                if run_logger:
                    run_logger.write("EXTRACTED_CORE_CONTENT:")
                    run_logger.write(core_content)
                    run_logger.write("")

                # ── Second quality check on the extracted core ─────────────
                # Catches pages that become too short after boilerplate removal
                if not is_useful_content(core_content):
                    logging.warning(f"[SKIP-CORE] Low-quality core for: {url}")
                    print(f"[SKIP] Low-quality core content: {url}")
                    if run_logger:
                        run_logger.write("STATUS: skipped_low_quality_core")
                        run_logger.write("")
                    continue

                logging.info(
                    f"Crawled content for {url}:\n{core_content}"
                )
                if run_logger:
                    run_logger.write("STATUS: kept")
                    run_logger.write("")

                content_items.append(
                    {
                        "title": title,
                        "url": url,
                        "content": core_content,
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
