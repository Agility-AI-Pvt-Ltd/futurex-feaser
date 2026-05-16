"""
pipeline/tools.py
─────────────────
All tool functions / node callables used in the LangGraph pipeline.
Add new tools here and wire them into graph.py.
"""

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from core.config import settings
from core.json_utils import extract_json_payload as _extract_json_payload
from core.logging import get_logger
from core.observability import ls_traceable
from pipeline.feasibility_parser import (
    get_feasibility_report_repair_prompt,
    normalize_feasibility_report_json,
    parse_feasibility_report,
)
from pipeline.state import AgentState
from pipeline.prompts.feasibility import get_feasibility_prompt
from pipeline.prompts.cross_question import get_cross_question_prompt
from scraper.web import (
    create_scrape_run_logger,
    crawler_service_with_logging,
    ddgs_url_scrapper,
    filter_urls,
)


from core.database import SessionLocal
from models.conversation import ChatSession

logger = get_logger(__name__)
WEB_RESEARCH_EXECUTOR = ThreadPoolExecutor(max_workers=10)


def _extract_llm_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    return getattr(response, "content", "") or ""


@ls_traceable(run_type="tool", name="embedding_retry", tags=["embedding", "background"])
def run_embedding_with_retry(
    conversation_id: str,
    search_results: str,
    analysis: str,
    *,
    attempts: int = 3,
) -> None:
    for attempt in range(1, attempts + 1):
        try:
            from rag.embedder import embed_conversation_context
            embed_conversation_context(conversation_id, search_results, analysis)
            logger.info(
                "embedding.completed conversation_id=%s attempt=%s",
                conversation_id,
                attempt,
            )
            return
        except Exception:
            logger.warning(
                "embedding.failed conversation_id=%s attempt=%s",
                conversation_id,
                attempt,
                exc_info=True,
            )
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))

    logger.error(
        "embedding.permanently_failed conversation_id=%s attempts=%s",
        conversation_id,
        attempts,
    )


def start_embedding_thread(conversation_id: str, search_results: str, analysis: str):
    thread = threading.Thread(
        target=run_embedding_with_retry,
        args=(conversation_id, search_results, analysis),
        name=f"embed-{conversation_id or 'unknown'}",
    )
    thread.start()
    return thread


async def _run_ddgs_search(query: str, run_logger) -> list[dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        WEB_RESEARCH_EXECUTOR,
        ddgs_url_scrapper,
        query,
        run_logger,
    )


@ls_traceable(run_type="tool", name="cross_question_node", tags=["feasibility", "node"])
def cross_question_node(state: AgentState, llm) -> dict:
    """
    Tool: Cross Question (New Chat)
    Generates a clarifying question to ask the user.
    """
    print("--- NODE EXECUTING: cross_question_node ---")

    history_str = "\n".join([f"User: {h['user']}\nAI: {h['ai']}" for h in state.get('conversation_history', [])])
    
    prompt = get_cross_question_prompt(
        idea=state['idea'],
        problem_solved=state['problem_solved'],
        ideal_customer=state['ideal_customer'],
        history_str=history_str,
        current_message=state.get('current_message', ''),
        previous_analysis=state.get('analysis', '')
    )
    response = llm.invoke(prompt)
    return {"analysis": _extract_llm_content(response)}


def load_context_node(state: AgentState) -> dict:
    """
    Tool: Load Context
    History is now loaded in api/routes.py and passed in state.
    This node simply passes it along.
    """
    print("--- NODE EXECUTING: load_context_node ---")
    return {"conversation_history": state.get("conversation_history", [])}


@ls_traceable(run_type="tool", name="idea_vagueness_filter_node", tags=["feasibility", "node"])
def idea_vagueness_filter_node(state: AgentState, llm) -> dict:
    """
    LLM-powered gatekeeper that determines whether the user's startup idea
    is genuinely meaningful enough to warrant web research and analysis.

    Returns::
        is_vague (bool)    – True  → idea is too vague / nonsensical
        vague_message (str) – friendly, specific feedback for the user
    """
    print("--- NODE EXECUTING: idea_vagueness_filter_node ---")

    idea            = (state.get("idea")            or "").strip()
    problem_solved  = (state.get("problem_solved")  or "").strip()
    ideal_customer  = (state.get("ideal_customer")  or "").strip()

    # ── Skip LLM gate for follow-up messages (only gate new ideas) ────────────
    if not state.get("is_new_chat", True):
        return {"is_vague": False, "vague_message": ""}

    prompt = (
        "You are an expert startup evaluator acting as a strict quality gatekeeper.\n"
        "Your ONLY job is to decide whether the startup idea below is specific enough\n"
        "to be worth running deep market research on.\n\n"
        "Reject an idea when it is:\n"
        "  • Gibberish or random characters (e.g. 'asdf', 'xyz123')\n"
        "  • Extremely generic with zero domain specificity (e.g. 'app idea', 'startup', 'something cool')\n"
        "  • A single meaningless word or phrase that conveys no real problem or domain\n"
        "  • Intentionally blank or a clear test input\n\n"
        "Accept an idea when it:\n"
        "  • Names a concrete problem, domain, or user group — even briefly\n"
        "  • Has at least a partial direction (e.g. 'food delivery for students', 'AI tutor for kids')\n"
        "  • Is a rough draft that shows genuine intent\n\n"
        f"Idea: {idea!r}\n"
        f"Problem it solves: {problem_solved!r}\n"
        f"Target customer: {ideal_customer!r}\n\n"
        "Respond with ONLY valid JSON — no markdown, no extra text:\n"
        '{"is_vague": <true|false>, "reason": "<one sentence explaining your verdict>"}'
    )

    try:
        raw = _extract_json_payload(_extract_llm_content(llm.invoke(prompt)))
        data = json.loads(raw)
        is_vague = bool(data.get("is_vague", False))
        reason   = str(data.get("reason", ""))
    except Exception as exc:
        print(f"  [VaguenessFilter] LLM/parse error — defaulting to not-vague: {exc}")
        is_vague = False
        reason   = ""

    if is_vague:
        vague_message = (
            f"Your idea seems too vague for me to run a meaningful analysis. {reason} "
            "Please describe your idea more specifically — mention the problem you're solving, "
            "your target users, and the domain (e.g. 'AI-powered scheduling tool for remote teams')."
        )
        print(f"  [VaguenessFilter] Idea flagged as VAGUE. Reason: {reason}")
    else:
        vague_message = ""
        print("  [VaguenessFilter] Idea looks specific enough — proceeding.")

    return {"is_vague": is_vague, "vague_message": vague_message}


def vague_idea_response_node(state: AgentState) -> dict:
    """
    Terminal node reached when the LLM gatekeeper marks the idea as vague.
    Returns a friendly, actionable message to the user.
    """
    print("--- NODE EXECUTING: vague_idea_response_node ---")
    message = state.get("vague_message") or (
        "Your idea is too vague for me to run a meaningful analysis. "
        "Please describe it more specifically — include the problem, target users, "
        "and the domain (e.g. 'AI scheduling tool for remote teams')."
    )
    return {"analysis": message}


def invalid_chat_response_node(state: AgentState) -> dict:
    print("--- NODE EXECUTING: invalid_chat_response_node ---")
    message = state.get("validation_message") or (
        "Please provide a clearer startup idea before I run research."
    )
    return {"analysis": message}


@ls_traceable(run_type="tool", name="modify_query_node", tags=["feasibility", "node"])
def modify_query_node(state: AgentState, llm) -> dict:

    """
    Tool: Modify User Query
    Asks the LLM to generate 3 targeted search queries covering:
      1. Direct startup competitors
      2. Existing products on the market
      3. VC / Y Combinator funded companies in the space
    Returns both a flat string (for DB) and a list (for multi-search).
    """
    print("--- NODE EXECUTING: modify_query_node ---")

    history_str = "\n".join([f"User: {h['user']}\nAI: {h['ai']}" for h in state.get('conversation_history', [])])

    prompt = (
        f"You are a market research expert.\n"
        f"Startup Idea: {state['idea']}\n"
        f"Problem it solves: {state['problem_solved']}\n"
        f"Conversation context:\n{history_str}\n"
        f"User's latest reply: {state.get('current_message', '')}\n\n"
        f"Generate exactly 3 short, targeted English Google search queries (max 6 words each) covering:\n"
        f"  1. Direct startup competitors in this space\n"
        f"  2. Existing products or tools already solving this problem\n"
        f"  3. Y Combinator or VC-funded companies in this space\n\n"
        f"Output ONLY a valid JSON array of 3 strings. Example:\n"
        f'["AI pet trainer startup competitors", "AI pet training apps market", "AI pet startup Y Combinator"]'
    )
    response = llm.invoke(prompt)
    raw = _extract_llm_content(response).strip()

    # Parse the JSON array; fall back to a single query if LLM misbehaves
    try:
        queries = json.loads(_extract_json_payload(raw))
        if not isinstance(queries, list) or len(queries) == 0:
            raise ValueError("Not a list")
        queries = [q.strip(' "') for q in queries[:3]]
    except Exception:
        # Fallback: treat whole response as one query
        queries = [raw.strip(' "[]')]

    print(f"  [QueryGen] Generated queries: {queries}")

    return {
        "optimized_queries": queries,
        "optimized_query": queries[0],   # keep DB field populated
    }


@ls_traceable(run_type="tool", name="web_research_node", tags=["feasibility", "web-research"])
async def web_research_node(state: AgentState) -> dict:
    """
    Tool: Web Research
    Runs multiple targeted DDGS searches + a Reddit search.
    - Up to 3 targeted queries (from modify_query_node) × 10 results each
    - 1 Reddit query on the primary query × 10 results
    All results are deduplicated by URL before crawling.
    """
    print("--- NODE EXECUTING: web_research_node ---")
    idea = state['idea']
    problem_solved = state['problem_solved']
    conversation_id = state.get("conversation_id", "")
    on_log = state.get("on_log")
    on_scrape_event = state.get("on_scrape_event")
    run_logger = create_scrape_run_logger(conversation_id=conversation_id, idea=idea, on_log=on_log, on_scrape_event=on_scrape_event)

    try:
        run_logger.section("WEB RESEARCH INPUT")
        run_logger.write(f"idea: {idea}")
        run_logger.write(f"problem_solved: {problem_solved}")
        run_logger.write(f"conversation_id: {conversation_id}")
        run_logger.write("")

        # Use multi-query list if available; fall back to single optimized_query
        queries = state.get('optimized_queries') or []
        if not queries:
            fallback = state.get('optimized_query') or f"{idea} {problem_solved} market competitors"
            queries = [fallback]

        run_logger.section("OPTIMIZED QUERIES")
        for query in queries:
            run_logger.write(query)
        run_logger.write("")

        seen = set()
        all_urls = []

        def _add_urls(items):
            for item in items:
                if item["url"] not in seen:
                    seen.add(item["url"])
                    all_urls.append(item)

        # Run blocking DDGS searches in a bounded executor so the event loop stays responsive.
        targeted_searches = [
            _run_ddgs_search(q, run_logger)
            for q in queries
        ]
        targeted_results = await asyncio.gather(*targeted_searches)

        for q, raw in zip(queries, targeted_results):
            print(f"  [Search] Query: {q}")
            _add_urls(filter_urls(raw, max_results=6, run_logger=run_logger))

        # Reddit-specific search — intentionally unfiltered (we WANT reddit.com URLs here)
        reddit_query = f"{queries[0]} site:reddit.com"
        print(f"  [Search] Reddit query: {reddit_query}")
        _add_urls(await _run_ddgs_search(reddit_query, run_logger))

        run_logger.section("DEDUPED URLS TO CRAWL")
        run_logger.write(f"count: {len(all_urls)}")
        run_logger.write("")
        for item in all_urls:
            run_logger.write(f"title: {item['title']}")
            run_logger.write(f"url: {item['url']}")
            run_logger.write("")

        print(f"  [Search] Total unique URLs to crawl: {len(all_urls)}")

        if not all_urls:
            run_logger.section("FINAL_AGGREGATED_SEARCH_RESULTS")
            run_logger.write("No relevant data found on the web.")
            run_logger.section("SCRAPE RUN END")
            return {"search_results": "No relevant data found on the web."}

        seed_texts = [
            idea,
            problem_solved,
            *queries,
            f"{idea} startup competitors",
            f"{idea} target market",
            f"{problem_solved} existing solutions",
        ]

        results_text = await crawler_service_with_logging(
            all_urls,
            seed_texts=seed_texts,
            run_logger=run_logger,
        )
        return {"search_results": results_text or "No relevant data found on the web."}
    finally:
        run_logger.close()


@ls_traceable(run_type="tool", name="llm_agent_node", tags=["feasibility", "analysis"])
def llm_agent_node(state: AgentState, llm) -> dict:
    """
    Tool: LLM Feasibility Analyser
    Calls the Groq LLM to produce a structured feasibility report.
    """
    print("--- NODE EXECUTING: llm_agent_node ---")

    prompt = get_feasibility_prompt(
        idea=state['idea'],
        ideal_customer=state['ideal_customer'],
        search_results=state['search_results']
    )
    response = llm.invoke(prompt)
    raw_analysis = _extract_llm_content(response)

    try:
        return {"analysis": normalize_feasibility_report_json(raw_analysis)}
    except Exception as exc:
        logger.warning("feasibility.analysis.parse_failed.initial error=%s", exc)

    try:
        repair_prompt = get_feasibility_report_repair_prompt(raw_analysis)
        repaired_response = llm.invoke(repair_prompt)
        repaired_analysis = _extract_llm_content(repaired_response)
        normalized = normalize_feasibility_report_json(repaired_analysis)
        logger.info("feasibility.analysis.repaired_json")
        return {"analysis": normalized}
    except Exception as exc:
        logger.warning("feasibility.analysis.parse_failed.repair error=%s", exc)

    return {"analysis": raw_analysis}


@ls_traceable(run_type="chain", name="generate_engagement_question", tags=["engagement"])
def generate_engagement_question_from_analysis(idea: str, raw_analysis: str, llm) -> str:
    cleaned_analysis = (raw_analysis or "").strip()
    if not cleaned_analysis:
        return ""

    try:
        report = parse_feasibility_report(cleaned_analysis)
    except Exception:
        return ""

    prompt = (
        "You are helping continue a startup feasibility conversation after a report was generated.\n"
        "Based on the report fields below, ask EXACTLY ONE sharp, engaging follow-up question.\n"
        "The question should make the founder think and reply with useful specifics.\n\n"
        "Rules:\n"
        "- Ask only one question.\n"
        "- Keep it under 30 words.\n"
        "- Make it conversational, not robotic.\n"
        "- Use the score and report insights to choose the most important next discussion point.\n"
        "- If score is low, focus on the biggest risk or missing proof.\n"
        "- If score is medium, focus on differentiation, validation, or wedge.\n"
        "- If score is high, focus on execution priority, beachhead users, or defensibility.\n"
        "- Return only the question text, with no bullets, labels, or markdown.\n\n"
        f"Startup idea: {idea}\n"
        f"Score: {report.get('score', '')}\n"
        f"Idea Fit: {report.get('idea_fit', '')}\n"
        f"Competitors: {report.get('competitors', '')}\n"
        f"Opportunity: {report.get('opportunity', '')}\n"
        f"Targeting: {report.get('targeting', '')}\n"
        f"Next Step: {report.get('next_step', '')}\n"
    )

    try:
        return _extract_llm_content(llm.invoke(prompt)).strip()
    except Exception:
        return ""


@ls_traceable(run_type="chain", name="generate_engagement_reply", tags=["engagement"])
def generate_engagement_reply_from_analysis(
    idea: str,
    raw_analysis: str,
    engagement_question: str,
    founder_answer: str,
    llm,
) -> str:
    cleaned_analysis = (raw_analysis or "").strip()
    founder_answer = (founder_answer or "").strip()
    if not cleaned_analysis or not founder_answer:
        return ""

    try:
        report = parse_feasibility_report(cleaned_analysis)
    except Exception:
        return ""

    prompt = (
        "You are a startup advisor continuing a feasibility conversation.\n"
        "A founder has answered an engagement question after receiving a feasibility report.\n"
        "Reply directly to the founder using ONLY the report fields below and their answer.\n\n"
        "Your job:\n"
        "- Acknowledge their answer briefly.\n"
        "- Interpret it through the report's score, idea fit, competitors, opportunity, targeting, and next step.\n"
        "- Give practical feedback in 3 short paragraphs or bullet-style sections.\n"
        "- End with one concise sentence that naturally invites the founder to continue.\n"
        "- Do not ask a brand-new follow-up question here.\n\n"
        f"Startup idea: {idea}\n"
        f"Original engagement question: {engagement_question}\n"
        f"Founder answer: {founder_answer}\n\n"
        f"Score: {report.get('score', '')}\n"
        f"Idea Fit: {report.get('idea_fit', '')}\n"
        f"Competitors: {report.get('competitors', '')}\n"
        f"Opportunity: {report.get('opportunity', '')}\n"
        f"Targeting: {report.get('targeting', '')}\n"
        f"Next Step: {report.get('next_step', '')}\n"
    )

    try:
        return _extract_llm_content(llm.invoke(prompt)).strip()
    except Exception:
        return ""


@ls_traceable(run_type="tool", name="engagement_question_node", tags=["engagement", "node"])
def engagement_question_node(state: AgentState, llm) -> dict:
    """
    Generates one engagement-driving follow-up question from the completed
    feasibility report so the conversation naturally continues.
    """
    print("--- NODE EXECUTING: engagement_question_node ---")
    question = generate_engagement_question_from_analysis(
        state.get("idea", ""),
        state.get("analysis", "") or "",
        llm,
    )
    return {"engagement_question": question}
