from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from api.dependencies import (
    get_db
)
from models import ChatSession, AgentStateModel, FeasibilityReport
from pipeline.graph import app as langgraph_app
from pipeline.qa_graph import qa_app as qa_langgraph_app, get_qa_graph_mermaid
import json
import logging

try:
    from rag.embedder import embed_conversation_context
except ImportError:
    embed_conversation_context = None

router = APIRouter()


class IdeaInput(BaseModel):
    idea: str
    user_name: str
    ideal_customer: str
    problem_solved: str
    authorId: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    analysis: Optional[str] = None


class QaInput(BaseModel):
    conversation_id: str
    question: str


class QaResponse(BaseModel):
    answer: str
    top_chunks: Optional[list[dict]] = None
    trace: Optional[list[dict]] = None



@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    input_data: IdeaInput,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    print("--- INCOMING REQUEST ---")
    print(f"Idea: {input_data.idea}")

    is_new_chat = True
    conv_id = input_data.conversation_id
    
    original_idea = input_data.idea
    problem_solved = input_data.problem_solved
    ideal_customer = input_data.ideal_customer
    current_message = input_data.idea

    initial_analysis = ""
    if conv_id:
        existing = db.query(ChatSession).filter(ChatSession.conversation_id == conv_id).order_by(ChatSession.timestamp.asc()).first()
        state_model = db.query(AgentStateModel).filter(AgentStateModel.conversation_id == conv_id).first()
        
        if existing:
            is_new_chat = False
            original_idea = existing.idea or original_idea
            problem_solved = existing.what_problem_it_solves or problem_solved
            ideal_customer = existing.ideal_customer or ideal_customer
            current_message = input_data.idea  # The user's newest reply
            
        if state_model:
            initial_analysis = state_model.analysis or ""
    else:
        conv_id = str(uuid.uuid4())

    history_dicts = []
    if not is_new_chat and conv_id:
        sessions = db.query(ChatSession).filter(ChatSession.conversation_id == conv_id).order_by(ChatSession.timestamp.asc()).all()
        for s in sessions:
            history_dicts.append({"user": s.human_message, "ai": s.ai_message})

    initial_state = {
        "idea": original_idea,
        "user_name": input_data.user_name,
        "ideal_customer": ideal_customer,
        "problem_solved": problem_solved,
        "messages": [],
        "search_results": "",
        "analysis": initial_analysis,
        "is_new_chat": is_new_chat,
        "conversation_id": conv_id,
        "conversation_history": history_dicts,
        "optimized_query": "",
        "optimized_queries": [],
        "current_message": current_message
    }

    result = await langgraph_app.ainvoke(initial_state)

    new_entry = ChatSession(
        authorId=input_data.authorId,
        conversation_id=conv_id,
        user_name=input_data.user_name,
        idea=original_idea,
        what_problem_it_solves=problem_solved,
        ideal_customer=ideal_customer,
        human_message=current_message,
        ai_message=result.get("analysis", "Error in analysis"),
    )
    db.add(new_entry)
    
    # ── Upsert the State record ──
    state_model = db.query(AgentStateModel).filter(AgentStateModel.conversation_id == conv_id).first()
    if not state_model:
        state_model = AgentStateModel(conversation_id=conv_id)
        db.add(state_model)
    
    state_model.optimized_query = result.get("optimized_query", state_model.optimized_query)
    state_model.search_results = result.get("search_results", state_model.search_results)
    state_model.analysis = result.get("analysis", state_model.analysis)

    # ── Try parsing and storing the JSON feasibility report ──
    raw_analysis = result.get("analysis", "")
    if raw_analysis and not is_new_chat:
        try:
            # We expect raw json string. Sometimes LLMs sneak in ```json markers
            clean_json = raw_analysis.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            
            # Upsert into feasibility_reports
            report = db.query(FeasibilityReport).filter(FeasibilityReport.conversation_id == conv_id).first()
            if not report:
                report = FeasibilityReport(conversation_id=conv_id)
                db.add(report)
                
            report.chain_of_thought = data.get("chain_of_thought")
            report.idea_fit = data.get("idea_fit")
            report.competitors = data.get("competitors")
            report.opportunity = data.get("opportunity")
            report.score = data.get("score")
            report.targeting = data.get("targeting")
            report.next_step = data.get("next_step")
            
        except json.JSONDecodeError:
            print("Warning: LLM analysis output wasn't valid JSON. Could not parse to FeasibilityReport.")

    db.commit()
    
    # ── Queue the state to be embedded in the background if it's the final report ──
    if not is_new_chat and embed_conversation_context is not None:
        background_tasks.add_task(
            embed_conversation_context,
            conversation_id=conv_id,
            search_results="",  # Handled inside llm_agent_node in parallel
            analysis=state_model.analysis
        )

    return ChatResponse(
        response="Analysis Complete" if not is_new_chat else "Researching your idea...",
        conversation_id=conv_id,
        analysis=result.get("analysis"),
    )


@router.post("/qa", response_model=QaResponse)
async def qa_endpoint(input_data: QaInput, db: Session = Depends(get_db)):
    """
    RAG-backed Q&A for follow-up questions about the feasibility report.
    Maintains a server-side sliding-window memory (last 7 turns verbatim +
    LLM-compressed rolling summary of older turns).
    """
    conv_id = input_data.conversation_id
    question = input_data.question

    # ── Load persisted state ───────────────────────────────────────────────────
    state_model = db.query(AgentStateModel).filter(AgentStateModel.conversation_id == conv_id).first()
    if not state_model:
        return QaResponse(answer="Could not find a feasibility report for this idea.")

    sessions = db.query(ChatSession).filter(
        ChatSession.conversation_id == conv_id
    ).order_by(ChatSession.timestamp.asc()).all()

    if not sessions:
        return QaResponse(answer="Could not find chat history for this conversation.")

    history_dicts = [{"user": s.human_message, "ai": s.ai_message} for s in sessions]

    # Full QA turn list from DB (uncompressed — routes.py is the source of truth)
    full_qa_history: list[dict] = state_model.qa_history or []
    qa_summary: str = state_model.qa_summary or ""

    answer = ""
    chunks: list[dict] = []
    trace: list[dict] = []

    try:
        first = sessions[0]
        initial_state = {
            "idea":               first.idea or "your startup idea",
            "user_name":          first.user_name or "",
            "ideal_customer":     first.ideal_customer or "",
            "problem_solved":     first.what_problem_it_solves or "",
            "messages":           [],
            "search_results":     state_model.search_results or "",
            "analysis":           state_model.analysis or "",
            "is_new_chat":        False,
            "conversation_id":    conv_id,
            "conversation_history": history_dicts,
            "optimized_query":    state_model.optimized_query or "",
            "optimized_queries":  [],
            "current_message":    question,
            "question":           question,
            "rag_context":        "",
            "top_chunks":         [],
            "qa_answer":          "",
            "trace":              [],
            # ── QA memory ──────────────────────────────────────────────────────
            # Pass the FULL uncompressed list; qa_memory_node handles windowing.
            "qa_history":         full_qa_history,
            "qa_summary":         qa_summary,
        }

        result = await qa_langgraph_app.ainvoke(initial_state)
        answer = result.get("qa_answer") or "I couldn't generate an answer right now."
        chunks = result.get("top_chunks", [])
        trace  = result.get("trace", [])

        # ── Persist updated memory ─────────────────────────────────────────────
        # Append the new turn to the FULL list (not the windowed result slice).
        new_full_history = full_qa_history + [{"q": question, "a": answer}]
        state_model.qa_history = new_full_history
        # qa_summary may have been updated by qa_memory_node (compression path).
        state_model.qa_summary = result.get("qa_summary", qa_summary)
        db.commit()

        logging.info(
            f"[QA Memory] conv={conv_id} total_turns={len(new_full_history)} "
            f"summary_len={len(state_model.qa_summary or '')}"
        )

    except Exception as e:
        logging.error(f"Error during QA LLM call: {e}")
        answer = "I'm sorry, I encountered an error while trying to answer your question."
        chunks = []
        trace  = [{"step": "qa_error", "message": str(e)}]

    return QaResponse(answer=answer, top_chunks=chunks, trace=trace)


@router.get("/history")
async def get_history(author_id: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Return one entry per conversation for the history sidebar.
    The list is filtered by author_id to avoid leaking other users' history.
    """
    if not author_id:
        return []

    from sqlalchemy import func

    subquery = (
        db.query(
            ChatSession.conversation_id,
            func.min(ChatSession.timestamp).label("min_ts"),
        )
        .filter(ChatSession.authorId == author_id)
        .group_by(ChatSession.conversation_id)
        .subquery()
    )

    sessions = (
        db.query(ChatSession)
        .join(
            subquery,
            (ChatSession.conversation_id == subquery.c.conversation_id)
            & (ChatSession.timestamp == subquery.c.min_ts),
        )
        .order_by(ChatSession.timestamp.desc())
        .all()
    )

    return [
        {
            "conversation_id": session.conversation_id,
            "idea": session.idea,
            "timestamp": session.timestamp,
            "user_name": session.user_name,
        }
        for session in sessions
    ]


@router.get("/history/{conversation_id}")
async def get_conversation_details(conversation_id: str, db: Session = Depends(get_db)):
    """
    Return the stored report and QA history for a specific conversation.
    """
    state_model = (
        db.query(AgentStateModel)
        .filter(AgentStateModel.conversation_id == conversation_id)
        .first()
    )
    first_session = (
        db.query(ChatSession)
        .filter(ChatSession.conversation_id == conversation_id)
        .order_by(ChatSession.timestamp.asc())
        .first()
    )

    if not state_model or not first_session:
        return {"error": "Conversation not found"}

    return {
        "conversation_id": conversation_id,
        "idea": first_session.idea,
        "user_name": first_session.user_name,
        "ideal_customer": first_session.ideal_customer,
        "problem_solved": first_session.what_problem_it_solves,
        "analysis": state_model.analysis,
        "qa_history": state_model.qa_history or [],
    }


@router.get("/qa/graph")
async def qa_graph_endpoint():
    """
    Returns a Mermaid graph definition for the QA LangGraph flow.
    Use this to visualize and trace QA pipeline execution.
    """
    return {
        "name": "qa_langgraph",
        "mermaid": get_qa_graph_mermaid(),
    }
