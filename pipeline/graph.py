"""
pipeline/graph.py
─────────────────
Builds and compiles the LangGraph StateGraph.
Import `app` from here wherever the pipeline needs to be invoked.

Graph flow
──────────
START
  └─► load_context
        └─► idea_vagueness_filter  ← LLM gatekeeper (new ideas only)
              ├─► [vague]  vague_idea_response ──► END
              └─► [ok]     chat_filter
                    ├─► [invalid] invalid_chat_response ──► END
                    ├─► [new]     cross_question         ──► END
                    └─► [follow]  modify_query ──► web_research ──► analyzer ──► END
"""

from langgraph.graph import StateGraph, START, END
from pipeline.state import AgentState
from pipeline.tools import (
    chat_filter_node,
    cross_question_node,
    engagement_question_node,
    idea_vagueness_filter_node,
    invalid_chat_response_node,
    load_context_node,
    modify_query_node,
    vague_idea_response_node,
    web_research_node,
    llm_agent_node,
)


# ── Routers ───────────────────────────────────────────────────────────────────

def route_vagueness(state: AgentState) -> str:
    """Route after the LLM vagueness gate."""
    if state.get("is_vague", False):
        print("--- ROUTER: Idea is VAGUE → vague_idea_response ---")
        return "vague"
    print("--- ROUTER: Idea passed vagueness gate → chat_filter ---")
    return "ok"


def route_chat(state: AgentState) -> str:
    if not state.get("input_valid", True):
        print("--- ROUTER: Routing to invalid_chat_response_node ---")
        return "invalid_chat_response"
    if state.get("is_new_chat", True):
        print("--- ROUTER: Routing to cross_question_node ---")
        return "cross_question"
    print("--- ROUTER: Routing to modify_query_node ---")
    return "modify_query"


# ── Graph ─────────────────────────────────────────────────────────────────────
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("load_context",         load_context_node)
workflow.add_node("idea_vagueness_filter", idea_vagueness_filter_node)
workflow.add_node("vague_idea_response",  vague_idea_response_node)
workflow.add_node("chat_filter",          chat_filter_node)
workflow.add_node("cross_question",       cross_question_node)
workflow.add_node("invalid_chat_response",invalid_chat_response_node)
workflow.add_node("modify_query",         modify_query_node)
workflow.add_node("web_research",         web_research_node)
workflow.add_node("analyzer",             llm_agent_node)
workflow.add_node("engagement_question",  engagement_question_node)

# Add Edges
workflow.add_edge(START, "load_context")
workflow.add_edge("load_context", "idea_vagueness_filter")

workflow.add_conditional_edges(
    "idea_vagueness_filter",
    route_vagueness,
    {
        "vague": "vague_idea_response",
        "ok":    "chat_filter",
    },
)

workflow.add_edge("vague_idea_response", END)

workflow.add_conditional_edges(
    "chat_filter",
    route_chat,
    {
        "invalid_chat_response": "invalid_chat_response",
        "cross_question":        "cross_question",
        "modify_query":          "modify_query",
    },
)

workflow.add_edge("cross_question",        END)
workflow.add_edge("invalid_chat_response", END)

workflow.add_edge("modify_query",  "web_research")
workflow.add_edge("web_research",  "analyzer")
workflow.add_edge("analyzer",      "engagement_question")
workflow.add_edge("engagement_question", END)

app = workflow.compile()
