from __future__ import annotations

import json
import logging
import uuid
from json import JSONDecodeError
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.dependencies import get_db
from core.config import settings
from core.scrape_usage import enforce_daily_scrape_limit
from lecturebot.rag import delete_transcript_points, index_transcript
from lecturebot.runner import run_chat_pipeline
from lecturebot.schemas import (
    ChatRequest as LectureChatRequest,
    ChatResponse as LectureChatResponse,
    ChatSessionOut as LectureChatSessionOut,
    MessageOut as LectureMessageOut,
    TranscriptAssetOut as LectureTranscriptAssetOut,
    TranscriptMetadataOut as LectureTranscriptMetadataOut,
    TranscriptReprocessResponse,
    UploadResponse,
)
from lecturebot.storage import download_transcript_text, upload_transcript_bytes
from lecturebot.transcript_converter import (
    clean_transcript_text,
    convert_transcript_to_text,
    is_supported_transcript_file,
    transcript_file_type,
)
from models import (
    AgentStateModel,
    ChatSession,
    FeasibilityReport,
    LectureChatSession,
    LectureMessage,
    LectureTranscriptAsset,
    LectureTranscriptMetadata,
)
from pipeline.graph import app as langgraph_app
from pipeline.qa_graph import get_qa_graph_mermaid, qa_app as qa_langgraph_app

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


class FeasibilityChatResponse(BaseModel):
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


def _commit_or_500(db: Session, action: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error while trying to {action}.",
        ) from exc


def _get_or_create_lecture_session(db: Session, session_id: str) -> LectureChatSession:
    try:
        session = db.query(LectureChatSession).filter_by(session_id=session_id).first()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database error while loading the chat session.",
        ) from exc

    if session:
        return session

    session = LectureChatSession(
        session_id=session_id,
        is_mentor_requested=False,
        memory_summary="",
    )
    db.add(session)
    _commit_or_500(db, "create lecture chat session")
    db.refresh(session)
    return session


def _load_lecture_history(db: Session, session_id: str) -> list[dict]:
    try:
        messages = (
            db.query(LectureMessage)
            .filter_by(session_id=session_id)
            .order_by(LectureMessage.timestamp)
            .all()
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database error while loading chat history.",
        ) from exc

    return [{"role": message.role, "content": message.content} for message in messages]


def _is_lecture_chat_payload(payload: dict[str, Any]) -> bool:
    return "session_id" in payload and "message" in payload


async def _handle_feasibility_chat(
    input_data: IdeaInput,
    background_tasks: BackgroundTasks,
    db: Session,
) -> FeasibilityChatResponse:
    is_new_chat = True
    conv_id = input_data.conversation_id

    original_idea = input_data.idea
    problem_solved = input_data.problem_solved
    ideal_customer = input_data.ideal_customer
    current_message = input_data.idea
    effective_author_id = input_data.authorId

    initial_analysis = ""
    if conv_id:
        existing = (
            db.query(ChatSession)
            .filter(ChatSession.conversation_id == conv_id)
            .order_by(ChatSession.timestamp.asc())
            .first()
        )
        state_model = (
            db.query(AgentStateModel)
            .filter(AgentStateModel.conversation_id == conv_id)
            .first()
        )

        if existing:
            is_new_chat = False
            original_idea = existing.idea or original_idea
            problem_solved = existing.what_problem_it_solves or problem_solved
            ideal_customer = existing.ideal_customer or ideal_customer
            effective_author_id = existing.authorId or effective_author_id
            current_message = input_data.idea

        if state_model:
            initial_analysis = state_model.analysis or ""
    else:
        conv_id = str(uuid.uuid4())

    if not is_new_chat:
        enforce_daily_scrape_limit(db, effective_author_id)

    history_dicts = []
    if not is_new_chat and conv_id:
        sessions = (
            db.query(ChatSession)
            .filter(ChatSession.conversation_id == conv_id)
            .order_by(ChatSession.timestamp.asc())
            .all()
        )
        for session in sessions:
            history_dicts.append({"user": session.human_message, "ai": session.ai_message})

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
        "current_message": current_message,
    }

    result = await langgraph_app.ainvoke(initial_state)

    # ── Vagueness gate: idea was too vague — skip DB writes and RAG ───────────
    if result.get("is_vague", False):
        vague_msg = result.get("analysis") or (
            "Your idea is too vague for me to run a meaningful analysis. "
            "Please describe it more specifically."
        )
        return FeasibilityChatResponse(
            response=vague_msg,
            conversation_id=conv_id,
            analysis=vague_msg,
        )

    new_entry = ChatSession(
        authorId=effective_author_id,
        conversation_id=conv_id,
        user_name=input_data.user_name,
        idea=original_idea,
        what_problem_it_solves=problem_solved,
        ideal_customer=ideal_customer,
        human_message=current_message,
        ai_message=result.get("analysis", "Error in analysis"),
    )
    db.add(new_entry)

    state_model = (
        db.query(AgentStateModel)
        .filter(AgentStateModel.conversation_id == conv_id)
        .first()
    )
    if not state_model:
        state_model = AgentStateModel(conversation_id=conv_id)
        db.add(state_model)

    state_model.optimized_query = result.get("optimized_query", state_model.optimized_query)
    state_model.search_results = result.get("search_results", state_model.search_results)
    state_model.analysis = result.get("analysis", state_model.analysis)

    raw_analysis = result.get("analysis", "")
    if raw_analysis and not is_new_chat:
        try:
            clean_json = raw_analysis.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            report = (
                db.query(FeasibilityReport)
                .filter(FeasibilityReport.conversation_id == conv_id)
                .first()
            )
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
        except JSONDecodeError:
            logging.warning("LLM analysis output was not valid JSON for conversation %s", conv_id)

    db.commit()

    if not is_new_chat and embed_conversation_context is not None:
        background_tasks.add_task(
            embed_conversation_context,
            conversation_id=conv_id,
            search_results="",
            analysis=state_model.analysis,
        )

    return FeasibilityChatResponse(
        response="Analysis Complete" if not is_new_chat else "Researching your idea...",
        conversation_id=conv_id,
        analysis=result.get("analysis"),
    )


def _handle_lecture_chat(
    request_data: LectureChatRequest,
    db: Session,
) -> LectureChatResponse:
    if not request_data.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    session = _get_or_create_lecture_session(db, request_data.session_id)
    transcript = None
    if request_data.transcript_id is not None:
        try:
            transcript = (
                db.query(LectureTranscriptAsset)
                .filter_by(id=request_data.transcript_id)
                .first()
            )
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=500,
                detail="Database error while loading transcript metadata.",
            ) from exc
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found.")

    history = _load_lecture_history(db, request_data.session_id)
    answer, sources, updated_memory_summary = run_chat_pipeline(
        request_data.message,
        history,
        memory_summary=session.memory_summary or "",
        transcript_id=transcript.id if transcript else None,
        transcript_source=transcript.source_name if transcript else "",
        transcript_session_name=transcript.session_name if transcript else "",
        transcript_object_path=transcript.object_path if transcript else "",
    )

    db.add(LectureMessage(session_id=request_data.session_id, role="user", content=request_data.message))
    db.add(LectureMessage(session_id=request_data.session_id, role="assistant", content=answer))
    session.memory_summary = updated_memory_summary
    _commit_or_500(db, "save lecture chat messages")

    return LectureChatResponse(
        session_id=request_data.session_id,
        answer=answer,
        sources=sources,
    )


@router.post("/upload", response_model=UploadResponse, tags=["Transcript"])
async def upload_transcript(
    file: UploadFile = File(...),
    session_name: str = Form(...),
    source_name: str | None = Form(default=None),
    chat_session_id: str | None = Form(default=None),
    course_name: str | None = Form(default=None),
    instructor_name: str | None = Form(default=None),
    session_date: str | None = Form(default=None),
    description: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    if not file.filename or not is_supported_transcript_file(file.filename):
        raise HTTPException(status_code=400, detail="Only .txt and .vtt files are supported.")
    if not session_name.strip():
        raise HTTPException(status_code=400, detail="Session name is required.")

    try:
        file_bytes = await file.read()
        raw_text = file_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Transcript must be a UTF-8 encoded .txt or .vtt file.",
        ) from exc

    try:
        text = convert_transcript_to_text(file.filename, raw_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not text.strip():
        raise HTTPException(status_code=400, detail="Transcript file is empty after conversion.")

    transcript_name = (source_name or file.filename).strip()
    chat_session = None
    if chat_session_id and chat_session_id.strip():
        chat_session = _get_or_create_lecture_session(db, chat_session_id.strip())

    try:
        bucket_name, object_path = upload_transcript_bytes(
            session_name=session_name,
            file_name=file.filename,
            file_bytes=file_bytes,
            content_type=file.content_type,
        )
        transcript_asset = LectureTranscriptAsset(
            session_id=chat_session.session_id if chat_session else None,
            session_name=session_name.strip(),
            source_name=transcript_name,
            file_name=file.filename,
            file_type=transcript_file_type(file.filename),
            bucket_name=bucket_name,
            object_path=object_path,
            chunks_indexed=0,
        )
        db.add(transcript_asset)
        db.flush()

        transcript_metadata = LectureTranscriptMetadata(
            transcript_id=transcript_asset.id,
            course_name=(course_name or "").strip(),
            instructor_name=(instructor_name or "").strip(),
            session_date=(session_date or "").strip(),
            description=(description or "").strip(),
            tags=(tags or "").strip(),
            storage_path=object_path,
            qdrant_collection_name=settings.LECTURE_QDRANT_COLLECTION_NAME,
        )
        db.add(transcript_metadata)

        chunks_indexed = index_transcript(
            text,
            source_name=transcript_name,
            metadata={
                "transcript_id": transcript_asset.id,
                "session_name": transcript_asset.session_name,
                "object_path": transcript_asset.object_path,
            },
        )
        transcript_asset.chunks_indexed = chunks_indexed
        _commit_or_500(db, "save transcript asset")
        db.refresh(transcript_asset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Transcript upload or indexing is temporarily unavailable.",
        ) from exc

    return UploadResponse(
        message=f"Transcript '{transcript_name}' uploaded and indexed successfully.",
        chunks_indexed=chunks_indexed,
        session_name=session_name.strip(),
        source_name=transcript_name,
        bucket_name=bucket_name,
        object_path=object_path,
        metadata_entry=LectureTranscriptMetadataOut.model_validate(transcript_asset.metadata_entry),
    )


@router.post(
    "/chat",
    response_model=FeasibilityChatResponse | LectureChatResponse,
    tags=["Chat"],
)
async def chat_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        payload = await request.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object.")

    if _is_lecture_chat_payload(payload):
        return _handle_lecture_chat(LectureChatRequest.model_validate(payload), db)

    return await _handle_feasibility_chat(
        IdeaInput.model_validate(payload),
        background_tasks,
        db,
    )


@router.post("/qa", response_model=QaResponse)
async def qa_endpoint(input_data: QaInput, db: Session = Depends(get_db)):
    conv_id = input_data.conversation_id
    question = input_data.question

    first_session = (
        db.query(ChatSession)
        .filter(ChatSession.conversation_id == conv_id)
        .order_by(ChatSession.timestamp.asc())
        .first()
    )
    if not first_session:
        return QaResponse(answer="Could not find chat history for this conversation.")

    state_model = (
        db.query(AgentStateModel)
        .filter(AgentStateModel.conversation_id == conv_id)
        .first()
    )
    if not state_model:
        return QaResponse(answer="Could not find a feasibility report for this idea.")

    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.conversation_id == conv_id)
        .order_by(ChatSession.timestamp.asc())
        .all()
    )
    history_dicts = [{"user": session.human_message, "ai": session.ai_message} for session in sessions]
    full_qa_history: list[dict] = state_model.qa_history or []
    qa_summary: str = state_model.qa_summary or ""

    answer = ""
    chunks: list[dict] = []
    trace: list[dict] = []

    try:
        first = sessions[0]
        initial_state = {
            "idea": first.idea or "your startup idea",
            "user_name": first.user_name or "",
            "ideal_customer": first.ideal_customer or "",
            "problem_solved": first.what_problem_it_solves or "",
            "messages": [],
            "search_results": state_model.search_results or "",
            "analysis": state_model.analysis or "",
            "is_new_chat": False,
            "conversation_id": conv_id,
            "conversation_history": history_dicts,
            "optimized_query": state_model.optimized_query or "",
            "optimized_queries": [],
            "current_message": question,
            "question": question,
            "rag_context": "",
            "top_chunks": [],
            "qa_answer": "",
            "trace": [],
            "qa_history": full_qa_history,
            "qa_summary": qa_summary,
        }

        result = await qa_langgraph_app.ainvoke(initial_state)
        answer = result.get("qa_answer") or "I couldn't generate an answer right now."
        chunks = result.get("top_chunks", [])
        trace = result.get("trace", [])

        new_full_history = full_qa_history + [{"q": question, "a": answer}]
        state_model.qa_history = new_full_history
        state_model.qa_summary = result.get("qa_summary", qa_summary)
        db.commit()

        logging.info(
            "[QA Memory] conv=%s total_turns=%s summary_len=%s",
            conv_id,
            len(new_full_history),
            len(state_model.qa_summary or ""),
        )
    except Exception as exc:
        logging.error("Error during QA LLM call: %s", exc)
        answer = "I'm sorry, I encountered an error while trying to answer your question."
        chunks = []
        trace = [{"step": "qa_error", "message": str(exc)}]

    return QaResponse(answer=answer, top_chunks=chunks, trace=trace)


@router.get("/history")
async def get_history(author_id: Optional[str] = None, db: Session = Depends(get_db)):
    if not author_id:
        return []

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


@router.get("/history/{identifier}")
async def get_history_or_conversation_details(identifier: str, db: Session = Depends(get_db)):
    lecture_session = (
        db.query(LectureChatSession)
        .filter(LectureChatSession.session_id == identifier)
        .first()
    )
    if lecture_session:
        return (
            db.query(LectureMessage)
            .filter_by(session_id=identifier)
            .order_by(LectureMessage.timestamp)
            .all()
        )

    state_model = (
        db.query(AgentStateModel)
        .filter(AgentStateModel.conversation_id == identifier)
        .first()
    )
    first_session = (
        db.query(ChatSession)
        .filter(ChatSession.conversation_id == identifier)
        .order_by(ChatSession.timestamp.asc())
        .first()
    )
    if not state_model or not first_session:
        return {"error": "Conversation not found"}

    return {
        "conversation_id": identifier,
        "idea": first_session.idea,
        "user_name": first_session.user_name,
        "ideal_customer": first_session.ideal_customer,
        "problem_solved": first_session.what_problem_it_solves,
        "analysis": state_model.analysis,
        "qa_history": state_model.qa_history or [],
    }


@router.get("/sessions", response_model=list[LectureChatSessionOut], tags=["History"])
def list_sessions(db: Session = Depends(get_db)):
    try:
        return db.query(LectureChatSession).order_by(LectureChatSession.created_at.desc()).all()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database error while loading chat sessions.",
        ) from exc


@router.get("/transcripts", response_model=list[LectureTranscriptAssetOut], tags=["Transcript"])
def list_transcripts(db: Session = Depends(get_db)):
    try:
        return db.query(LectureTranscriptAsset).order_by(LectureTranscriptAsset.created_at.desc()).all()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database error while loading transcripts.",
        ) from exc


@router.post(
    "/transcripts/{transcript_id}/reprocess",
    response_model=TranscriptReprocessResponse,
    tags=["Transcript"],
)
def reprocess_transcript(transcript_id: int, db: Session = Depends(get_db)):
    try:
        transcript = db.query(LectureTranscriptAsset).filter_by(id=transcript_id).first()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database error while loading transcript metadata.",
        ) from exc

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    try:
        raw_text = download_transcript_text(transcript.bucket_name, transcript.object_path)
        file_type = transcript_file_type(transcript.file_name)
        if file_type == "vtt":
            cleaned_text = convert_transcript_to_text(transcript.file_name, raw_text)
        else:
            cleaned_text = clean_transcript_text(raw_text)

        if not cleaned_text.strip():
            raise ValueError("Transcript is empty after preprocessing.")

        delete_transcript_points(
            transcript_id=transcript.id,
            object_path=transcript.object_path,
        )
        chunks_indexed = index_transcript(
            cleaned_text,
            source_name=transcript.source_name,
            metadata={
                "transcript_id": transcript.id,
                "session_name": transcript.session_name,
                "object_path": transcript.object_path,
            },
        )
        transcript.chunks_indexed = chunks_indexed
        _commit_or_500(db, "reprocess transcript")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Transcript reprocessing is temporarily unavailable.",
        ) from exc

    return TranscriptReprocessResponse(
        message="Transcript reprocessed successfully.",
        transcript_id=transcript.id,
        chunks_indexed=chunks_indexed,
    )


@router.get("/qa/graph")
async def qa_graph_endpoint():
    return {
        "name": "qa_langgraph",
        "mermaid": get_qa_graph_mermaid(),
    }
