import asyncio
import logging
import os
import re
import sys
from ddgs import DDGS
from crawl4ai import AsyncWebCrawler
from core.config import settings


# Configure logging
logging.basicConfig(
    filename="scraper.log",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

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


def ddgs_url_scrapper(query):
    logging.info(f"Searching DDGS for query: {query}")

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


def filter_urls(urls: list, max_results: int = 6) -> list:
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
    content_items = []
    async with AsyncWebCrawler() as crawler:
        for item in urls:
            title = item["title"]
            url = item["url"]

            print(f"\n=== {title} ===")
            print(f"URL: {url}\n")

            logging.info(f"Starting crawl for: {url}")

            try:
                result = await crawler.arun(url=url)

                markdown = result.markdown or ""

                # Strip all links before any further processing
                markdown = strip_links(markdown)

                # ── Early junk check on the FULL raw markdown ──────────────
                # Catches signals that appear outside the first 30 lines
                # (e.g. Reddit login walls buried deep in the page)
                if not is_useful_content(markdown):
                    logging.warning(f"[SKIP-EARLY] Junk page detected: {url}")
                    print(f"[SKIP] Junk page (early check): {url}")
                    continue

                logging.info(
                    f"Successfully crawled: {url} | "
                    f"Markdown length: {len(markdown)}"
                )

                print(markdown[:1000])
                print("\n" + "-" * 80)

                # Extract meaningful content (strip boilerplate)
                core_content = extract_core(markdown)

                # ── Second quality check on the extracted core ─────────────
                # Catches pages that become too short after boilerplate removal
                if not is_useful_content(core_content):
                    logging.warning(f"[SKIP-CORE] Low-quality core for: {url}")
                    print(f"[SKIP] Low-quality core content: {url}")
                    continue

                logging.info(
                    f"Crawled content for {url}:\n{core_content}"
                )

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

            print("-" * 80)

    content_items = _apply_noise_remover(content_items, seed_texts)

    content_results = [
        f"Source: {item['title']} ({item['url']})\nContent:\n{item['content']}"
        for item in content_items
    ]
    return "\n\n---\n\n".join(content_results)


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
