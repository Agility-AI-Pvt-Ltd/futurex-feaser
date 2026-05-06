from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from lecturebot.state import ChatPipelineState
from lecturebot.tools import (
    analyze_question_node,
    answer_question_node,
    irrelevant_question_node,
    relevance_check_node,
    retrieve_context_node,
    summarize_memory_node,
)


def route_relevance(state: ChatPipelineState) -> str:
    if state.get("relevance_label") == "irrelevant":
        return "irrelevant"
    return "answer"


workflow = StateGraph(ChatPipelineState)
workflow.add_node("analyze_question", analyze_question_node)
workflow.add_node("retrieve_context", retrieve_context_node)
workflow.add_node("relevance_check", relevance_check_node)
workflow.add_node("irrelevant_question", irrelevant_question_node)
workflow.add_node("answer_question", answer_question_node)
workflow.add_node("summarize_memory", summarize_memory_node)

workflow.add_edge(START, "analyze_question")
workflow.add_edge("analyze_question", "retrieve_context")
workflow.add_edge("retrieve_context", "relevance_check")
workflow.add_conditional_edges(
    "relevance_check",
    route_relevance,
    {
        "irrelevant": "irrelevant_question",
        "answer": "answer_question",
    },
)
workflow.add_edge("irrelevant_question", "summarize_memory")
workflow.add_edge("answer_question", "summarize_memory")
workflow.add_edge("summarize_memory", END)

chat_app = workflow.compile()
