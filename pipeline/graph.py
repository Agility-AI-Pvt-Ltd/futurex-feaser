"""
pipeline/graph.py
─────────────────
Builds and compiles the LangGraph StateGraph.
Import `app` from here wherever the pipeline needs to be invoked.
"""

from langgraph.graph import StateGraph, START, END
from pipeline.state import AgentState
from pipeline.tools import (
    cross_question_node,
    load_context_node,
    modify_query_node,
    web_research_node,
    llm_agent_node
)

def route_chat(state: AgentState) -> str:
    # We can eventually add LLM logic here to check if the idea is clear enough
    if state.get("is_new_chat", True):
        print("--- ROUTER: Routing to cross_question_node ---")
        return "cross_question"
    print("--- ROUTER: Routing to modify_query_node ---")
    return "modify_query"

# ── Graph ─────────────────────────────────────────────────────────────────────
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("cross_question", cross_question_node)
workflow.add_node("load_context", load_context_node)
workflow.add_node("modify_query", modify_query_node)
workflow.add_node("web_research", web_research_node)
workflow.add_node("analyzer", llm_agent_node)

# Add Edges
workflow.add_edge(START, "load_context")

workflow.add_conditional_edges(
    "load_context",
    route_chat,
    {
        "cross_question": "cross_question",
        "modify_query": "modify_query"
    }
)

workflow.add_edge("cross_question", END)

workflow.add_edge("modify_query", "web_research")
workflow.add_edge("web_research", "analyzer")
workflow.add_edge("analyzer", END)

app = workflow.compile()
