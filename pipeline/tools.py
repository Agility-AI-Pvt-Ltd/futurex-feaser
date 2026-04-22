"""
pipeline/tools.py
─────────────────
All tool functions / node callables used in the LangGraph pipeline.
Add new tools here and wire them into graph.py.
"""

import asyncio
import json
from pipeline.state import AgentState
from pipeline.prompts.feasibility import get_feasibility_prompt
from pipeline.prompts.cross_question import get_cross_question_prompt
from scraper.web import ddgs_url_scrapper, crawler_service, filter_urls


from core.database import SessionLocal
from models.conversation import ChatSession


def cross_question_node(state: AgentState) -> dict:
    """
    Tool: Cross Question (New Chat)
    Generates a clarifying question to ask the user.
    """
    print("--- NODE EXECUTING: cross_question_node ---")
    from core.llm_factory import get_llm
    llm = get_llm()

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
    return {"analysis": response.content}


def load_context_node(state: AgentState) -> dict:
    """
    Tool: Load Context
    History is now loaded in api/routes.py and passed in state.
    This node simply passes it along.
    """
    print("--- NODE EXECUTING: load_context_node ---")
    return {"conversation_history": state.get("conversation_history", [])}


def modify_query_node(state: AgentState) -> dict:
    """
    Tool: Modify User Query
    Asks the LLM to generate 3 targeted search queries covering:
      1. Direct startup competitors
      2. Existing products on the market
      3. VC / Y Combinator funded companies in the space
    Returns both a flat string (for DB) and a list (for multi-search).
    """
    print("--- NODE EXECUTING: modify_query_node ---")
    from core.llm_factory import get_llm
    llm = get_llm(temperature=0.3)

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
    raw = response.content.strip()

    # Parse the JSON array; fall back to a single query if LLM misbehaves
    try:
        queries = json.loads(raw)
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

    # Use multi-query list if available; fall back to single optimized_query
    queries = state.get('optimized_queries') or []
    if not queries:
        fallback = state.get('optimized_query') or f"{idea} {problem_solved} market competitors"
        queries = [fallback]

    seen = set()
    all_urls = []

    def _add_urls(items):
        for item in items:
            if item["url"] not in seen:
                seen.add(item["url"])
                all_urls.append(item)

    # Run all targeted queries; apply domain-filter + cap on general results
    for q in queries:
        print(f"  [Search] Query: {q}")
        raw = ddgs_url_scrapper(q)
        _add_urls(filter_urls(raw, max_results=6))  # strips reddit/quora/zhihu, caps at 6

    # Reddit-specific search — intentionally unfiltered (we WANT reddit.com URLs here)
    reddit_query = f"{queries[0]} site:reddit.com"
    print(f"  [Search] Reddit query: {reddit_query}")
    _add_urls(ddgs_url_scrapper(reddit_query))

    print(f"  [Search] Total unique URLs to crawl: {len(all_urls)}")

    if not all_urls:
        return {"search_results": "No relevant data found on the web."}

    seed_texts = [
        idea,
        problem_solved,
        *queries,
        f"{idea} startup competitors",
        f"{idea} target market",
        f"{problem_solved} existing solutions",
    ]

    results_text = await crawler_service(all_urls, seed_texts=seed_texts)
    return {"search_results": results_text}


def llm_agent_node(state: AgentState) -> dict:
    """
    Tool: LLM Feasibility Analyser
    Calls the Groq LLM to produce a structured feasibility report.
    """
    print("--- NODE EXECUTING: llm_agent_node ---")
    from core.llm_factory import get_llm
    llm = get_llm()

    # ── Parallelize Embedding & LLM Call ──
    # The LLM API call takes time (waiting on network).
    # We can perform the CPU-intensive embedding of search_results locally at the same time.
    try:
        from rag.embedder import embed_conversation_context
        import threading
        
        # Fire off the CPU-bound embedding in a background thread
        print("  [RAG] 🚀 Starting background embedding for search_results...")
        emb_thread = threading.Thread(
            target=embed_conversation_context,
            args=(state.get('conversation_id', ''), state.get('search_results', ''), ""),
            daemon=True
        )
        emb_thread.start()
    except Exception as e:
        print(f"  [RAG] ⚠️ Could not start background embedding: {e}")

    prompt = get_feasibility_prompt(
        idea=state['idea'],
        ideal_customer=state['ideal_customer'],
        search_results=state['search_results']
    )
    response = llm.invoke(prompt)
    return {"analysis": response.content}
