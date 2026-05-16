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
              ├─► [vague]   vague_idea_response ──► END
              ├─► [new]     cross_question      ──► END
              └─► [follow]  modify_query ──► web_research ──► analyzer ──► END
"""

from langgraph.graph import StateGraph, START, END
from core.llm_factory import get_llm
from pipeline.state import AgentState
from pipeline.tools import (
    cross_question_node,
    engagement_question_node,
    idea_vagueness_filter_node,
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
    if state.get("is_new_chat", True):
        print("--- ROUTER: Routing to cross_question_node ---")
        return "new"
    print("--- ROUTER: Routing to modify_query_node ---")
    return "follow"


def build_graph(
    *,
    cross_question_llm=None,
    vagueness_llm=None,
    modify_query_llm=None,
    analysis_llm=None,
    engagement_llm=None,
):
    workflow = StateGraph(AgentState)

    cross_question_llm = cross_question_llm or get_llm()
    vagueness_llm = vagueness_llm or get_llm(temperature=0)
    modify_query_llm = modify_query_llm or get_llm(temperature=0.3)
    analysis_llm = analysis_llm or get_llm()
    engagement_llm = engagement_llm or get_llm(temperature=0.4)

    workflow.add_node("load_context", load_context_node)
    workflow.add_node(
        "idea_vagueness_filter",
        lambda state: idea_vagueness_filter_node(state, vagueness_llm),
    )
    workflow.add_node("vague_idea_response", vague_idea_response_node)
    workflow.add_node(
        "cross_question",
        lambda state: cross_question_node(state, cross_question_llm),
    )
    workflow.add_node(
        "modify_query",
        lambda state: modify_query_node(state, modify_query_llm),
    )
    workflow.add_node("web_research", web_research_node)
    workflow.add_node("analyzer", lambda state: llm_agent_node(state, analysis_llm))
    workflow.add_node(
        "engagement_question",
        lambda state: engagement_question_node(state, engagement_llm),
    )

    workflow.add_edge(START, "load_context")
    workflow.add_edge("load_context", "idea_vagueness_filter")

    workflow.add_conditional_edges(
        "idea_vagueness_filter",
        route_vagueness,
        {
            "vague": "vague_idea_response",
            "new": "cross_question",
            "follow": "modify_query",
        },
    )

    workflow.add_edge("vague_idea_response", END)
    workflow.add_edge("cross_question", END)

    workflow.add_edge("modify_query", "web_research")
    workflow.add_edge("web_research", "analyzer")
    workflow.add_edge("analyzer", "engagement_question")
    workflow.add_edge("engagement_question", END)

    return workflow.compile()


app = build_graph()
