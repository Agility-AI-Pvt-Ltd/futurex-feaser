from __future__ import annotations

import json
import logging
import uuid
from json import JSONDecodeError
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

logger = logging.getLogger(__name__)

from api.dependencies import enforce_api_rate_limit, get_db
from api.input_validation import ensure_meaningful_text
from core.database import settings, SessionLocal
from core.llm_factory import get_llm
from core.observability import ls_traceable
import asyncio
from core.redis_client import get_redis
from core.scrape_usage import enforce_daily_scrape_limit

HISTORY_CACHE_TTL = 60  # seconds
from lecturebot.rag import (
    delete_collection_if_exists,
    delete_transcript_points,
    index_transcript,
    reindex_transcript_with_shadow_collection,
)
from lecturebot.runner import run_chat_pipeline
from lecturebot.schemas import (
    ChatRequest as LectureChatRequest,
    ChatResponse as LectureChatResponse,
    ChatSessionOut as LectureChatSessionOut,
    MessageOut as LectureMessageOut,
    TranscriptAssetOut as LectureTranscriptAssetOut,
    TranscriptMetadataOut as LectureTranscriptMetadataOut,
    TranscriptUpdate,
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
from pipeline.tools import (
    _extract_json_payload,
    generate_engagement_question_from_analysis,
    generate_engagement_reply_from_analysis,
    run_embedding_with_retry,
)

try:
    from rag.embedder import embed_conversation_context
except ImportError:
    embed_conversation_context = None


router = APIRouter(dependencies=[Depends(enforce_api_rate_limit)])


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
    engagement_question: Optional[str] = None
    is_vague: bool = False


class QaInput(BaseModel):
    conversation_id: str
    question: str


class QaResponse(BaseModel):
    answer: str
    top_chunks: Optional[list[dict]] = None
    trace: Optional[list[dict]] = None


class EngagementReplyInput(BaseModel):
    conversation_id: str
    answer: str
    engagement_question: Optional[str] = None


class EngagementReplyResponse(BaseModel):
    answer: str


def _paginate_query(query, *, limit: int, offset: int):
    page_size = max(1, min(limit, settings.API_MAX_PAGE_SIZE))
    page_offset = max(0, offset)
    return query.limit(page_size).offset(page_offset)


def _transcript_metadata_response_loader():
    return selectinload(LectureTranscriptAsset.metadata_entry).load_only(
        LectureTranscriptMetadata.id,
        LectureTranscriptMetadata.transcript_id,
        LectureTranscriptMetadata.course_name,
        LectureTranscriptMetadata.instructor_name,
        LectureTranscriptMetadata.session_date,
        LectureTranscriptMetadata.description,
        LectureTranscriptMetadata.tags,
        LectureTranscriptMetadata.storage_path,
        LectureTranscriptMetadata.qdrant_collection_name,
        LectureTranscriptMetadata.created_at,
    )


def _trim_qa_history(history: list[dict]) -> list[dict]:
    max_turns = max(1, settings.QA_MAX_STORED_TURNS)
    if len(history) <= max_turns:
        return history
    return history[-max_turns:]


def _commit_or_500(db: Session, action: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error while trying to {action}.",
        ) from exc


def _get_or_create_lecture_session(db: Session, session_id: str, author_id: Optional[str] = None, transcript_id: Optional[int] = None) -> LectureChatSession:
    try:
        session = db.query(LectureChatSession).filter_by(session_id=session_id).first()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database error while loading the chat session.",
        ) from exc

    if session:
        changed = False
        if author_id and not session.author_id:
            session.author_id = author_id
            changed = True
        if transcript_id and not session.transcript_id:
            session.transcript_id = transcript_id
            changed = True
        if changed:
            _commit_or_500(db, "update lecture chat session")
        return session

    session = LectureChatSession(
        session_id=session_id,
        author_id=author_id,
        transcript_id=transcript_id,
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


def _load_feasibility_conversation_messages(db: Session, conversation_id: str) -> list[ChatSession]:
    if not conversation_id:
        return []

    try:
        return (
            db.query(ChatSession)
            .filter(ChatSession.conversation_id == conversation_id)
            .order_by(ChatSession.timestamp.asc())
            .all()
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database error while loading conversation history.",
        ) from exc


def _is_lecture_chat_payload(payload: dict[str, Any]) -> bool:
    return "session_id" in payload and "message" in payload


def _validate_feasibility_input(input_data: IdeaInput) -> None:
    input_data.idea = ensure_meaningful_text(input_data.idea)

    if not input_data.conversation_id:
        input_data.ideal_customer = ensure_meaningful_text(input_data.ideal_customer)
        input_data.problem_solved = ensure_meaningful_text(input_data.problem_solved)


@ls_traceable(run_type="chain", name="handle_feasibility_chat", tags=["api", "feasibility"])
async def _handle_feasibility_chat(
    input_data: IdeaInput,
    background_tasks: BackgroundTasks,
    db: Session,
) -> FeasibilityChatResponse:
    # Use the streaming implementation but collect all events and return the last one
    # This avoids duplicating the complex logic
    result_analysis = None
    result_engagement = None
    conv_id = None
    is_vague = False

    async for event_str in _handle_feasibility_chat_stream(input_data, background_tasks, db):
        if event_str.startswith("data: "):
            try:
                event = json.loads(event_str[6:])
                if event["type"] == "final":
                    result_analysis = event.get("analysis")
                    result_engagement = event.get("engagement_question")
                    conv_id = event.get("conversation_id")
                    is_vague = event.get("is_vague", False)
                elif event["type"] == "node" and event.get("node") == "vague_idea_response":
                    is_vague = True
            except Exception:
                continue

    return FeasibilityChatResponse(
        response=result_analysis or "Error in analysis",
        conversation_id=conv_id or input_data.conversation_id or str(uuid.uuid4()),
        analysis=result_analysis,
        engagement_question=result_engagement,
        is_vague=is_vague
    )

async def _handle_feasibility_chat_stream(
    input_data: IdeaInput,
    background_tasks: BackgroundTasks,
):
    _validate_feasibility_input(input_data)

    is_new_chat = True
    conv_id = input_data.conversation_id

    original_idea = input_data.idea
    problem_solved = input_data.problem_solved
    ideal_customer = input_data.ideal_customer
    current_message = input_data.idea
    effective_author_id = input_data.authorId

    initial_analysis = ""
    existing_messages: list[ChatSession] = []
    
    # 1. Initial read and close session immediately
    db = SessionLocal()
    try:
        if conv_id:
            existing_messages = _load_feasibility_conversation_messages(db, conv_id)
            existing = existing_messages[0] if existing_messages else None
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

            if state_model and existing:
                initial_analysis = state_model.analysis or ""
        else:
            conv_id = str(uuid.uuid4())

        if not is_new_chat:
            enforce_daily_scrape_limit(db, effective_author_id)

        history_dicts = [
            {"user": s.human_message, "ai": s.ai_message}
            for s in existing_messages
        ]
    finally:
        db.close()

    stream_queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_log(message):
        if message and message.strip():
            # Filter out the "==" separator lines to keep the UI clean
            if message.startswith("="): return
            loop.call_soon_threadsafe(stream_queue.put_nowait, {"type": "log", "message": message})

    def on_scrape_event(event_data: dict):
        loop.call_soon_threadsafe(stream_queue.put_nowait, {"type": "scrape_url", **event_data})

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
        "on_log": on_log,
        "on_scrape_event": on_scrape_event,
    }

    yield f"data: {json.dumps({'type': 'node', 'node': 'start', 'message': 'Initializing research context...', 'conversation_id': conv_id})}\n\n"

    async def run_graph():
        try:
            async for event in langgraph_app.astream(initial_state, stream_mode="updates"):
                await stream_queue.put({"type": "node_event", "event": event})
        except Exception as e:
            logging.exception("Error in LangGraph streaming")
            await stream_queue.put({"type": "error", "message": str(e)})
        finally:
            await stream_queue.put({"type": "end"})

    asyncio.create_task(run_graph())

    accumulated_state: dict = {}
    while True:
        item = await stream_queue.get()
        if item["type"] == "end":
            break
        if item["type"] == "error":
            msg = "Error: " + str(item.get("message", "Unknown error"))
            yield f"data: {json.dumps({'type': 'log', 'message': msg})}\n\n"
            break
        if item["type"] == "log":
            yield f"data: {json.dumps(item)}\n\n"
        if item["type"] == "scrape_url":
            yield f"data: {json.dumps(item)}\n\n"
        if item["type"] == "node_event":
            event = item["event"]
            for node_name, node_state in event.items():
                msg = f"Executing {node_name}..."
                if node_name == "web_research": msg = "Conducting deep web research and scraping..."
                elif node_name == "analyzer": msg = "Analyzing findings and generating feasibility report..."
                elif node_name == "modify_query": msg = "Optimizing search queries for better market coverage..."
                elif node_name == "idea_vagueness_filter": msg = "Verifying idea clarity..."

                yield f"data: {json.dumps({'type': 'node', 'node': node_name, 'message': msg})}\n\n"
                if isinstance(node_state, dict):
                    accumulated_state.update(node_state)

    result = accumulated_state
    
    # ── Vagueness gate: idea was too vague — skip DB writes and RAG ───────────
    if result.get("is_vague", False):
        vague_msg = result.get("analysis") or (
            "Your idea is too vague for me to run a meaningful analysis. "
            "Please describe it more specifically."
        )
        yield f"data: {json.dumps({'type': 'final', 'analysis': vague_msg, 'conversation_id': conv_id, 'is_vague': True})}\n\n"
        return

    # 2. Re-open session only for the final write
    db = SessionLocal()
    try:
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
                data = json.loads(_extract_json_payload(raw_analysis))
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
            except (JSONDecodeError, ValueError):
                logging.warning("LLM analysis output was not valid JSON for conversation %s", conv_id)

        db.commit()

        _inv_redis = get_redis()
        if _inv_redis is not None:
            try:
                pattern = f"idealab:history:{effective_author_id}:*"
                keys = await _inv_redis.keys(pattern)
                if keys:
                    await _inv_redis.delete(*keys)
            except Exception as exc:
                logger.warning("Redis cache invalidation failed: %s", exc)

        if not is_new_chat and embed_conversation_context is not None:
            background_tasks.add_task(
                run_embedding_with_retry,
                conversation_id=conv_id,
                search_results=result.get("search_results", ""),
                analysis=state_model.analysis,
            )
    finally:
        db.close()

    yield f"data: {json.dumps({'type': 'final', 'analysis': result.get('analysis'), 'engagement_question': result.get('engagement_question'), 'conversation_id': conv_id, 'is_report': not is_new_chat or result.get('is_vague', False) == False and 'optimized_query' in result})}\n\n"


@ls_traceable(run_type="chain", name="handle_lecture_chat", tags=["api", "lecturebot"])
def _handle_lecture_chat(
    request_data: LectureChatRequest,
    db: Session,
) -> LectureChatResponse:
    if not request_data.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    session = _get_or_create_lecture_session(
        db,
        request_data.session_id,
        request_data.author_id,
        request_data.transcript_id,
    )
    transcript = None
    effective_transcript_id = request_data.transcript_id or session.transcript_id
    if effective_transcript_id is not None:
        try:
            transcript = (
                db.query(LectureTranscriptAsset)
                .filter_by(id=effective_transcript_id)
                .first()
            )
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=500,
                detail="Database error while loading transcript metadata.",
            ) from exc
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found.")
        if session.transcript_id != transcript.id:
            session.transcript_id = transcript.id

    history = _load_lecture_history(db, request_data.session_id)
    answer, sources, updated_memory_summary = run_chat_pipeline(
        request_data.message,
        history,
        memory_summary=session.memory_summary or "",
        transcript_id=transcript.id if transcript else None,
        transcript_source=transcript.source_name if transcript else "",
        transcript_session_name=transcript.session_name if transcript else "",
        transcript_object_path=transcript.object_path if transcript else "",
        transcript_collection_name=(
            transcript.metadata_entry.qdrant_collection_name
            if transcript and transcript.metadata_entry
            else settings.LECTURE_QDRANT_COLLECTION_NAME
        ),
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
            transcript_text=text,
            transcript_summary=None,
            summary_generated_at=None,
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
        logger.exception("Transcript upload failed")
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


@router.post("/chat/stream", tags=["Chat"])
async def chat_stream_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
):
    try:
        payload = await request.json()
    except JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc

    return StreamingResponse(
        _handle_feasibility_chat_stream(
            IdeaInput.model_validate(payload),
            background_tasks,
        ),
        media_type="text/event-stream",
    )


@ls_traceable(run_type="chain", name="qa_endpoint", tags=["api", "qa"])
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

    sessions = _load_feasibility_conversation_messages(db, conv_id)
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

        new_full_history = _trim_qa_history(full_qa_history + [{"q": question, "a": answer}])
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


@ls_traceable(run_type="chain", name="engagement_reply_endpoint", tags=["api", "engagement"])
@router.post("/engagement-reply", response_model=EngagementReplyResponse)
async def engagement_reply_endpoint(
    input_data: EngagementReplyInput,
    db: Session = Depends(get_db),
):
    conv_id = input_data.conversation_id
    founder_answer = ensure_meaningful_text(input_data.answer or "")
    engagement_question = (input_data.engagement_question or "").strip()

    sessions = _load_feasibility_conversation_messages(db, conv_id)
    if not sessions:
        return EngagementReplyResponse(answer="Could not find chat history for this conversation.")

    state_model = (
        db.query(AgentStateModel)
        .filter(AgentStateModel.conversation_id == conv_id)
        .first()
    )
    if not state_model or not (state_model.analysis or "").strip():
        return EngagementReplyResponse(
            answer="Could not find a feasibility report for this conversation."
        )

    first_session = sessions[0]
    derived_question = engagement_question or generate_engagement_question_from_analysis(
        first_session.idea or "your startup idea",
        state_model.analysis or "",
        get_llm(temperature=0.4),
    )

    reply = generate_engagement_reply_from_analysis(
        idea=first_session.idea or "your startup idea",
        raw_analysis=state_model.analysis or "",
        engagement_question=derived_question,
        founder_answer=founder_answer,
        llm=get_llm(temperature=0.4),
    )
    if not reply:
        reply = (
            "Thanks for sharing that answer. Based on the current feasibility report, "
            "the next step is to sharpen your target user, stress-test the strongest competitor angle, "
            "and validate whether this moment is painful enough that people would come back daily."
        )

    full_qa_history: list[dict] = list(state_model.qa_history or [])
    full_qa_history.append(
        {
            "kind": "engagement",
            "engagement_question": derived_question,
            "q": founder_answer,
            "a": reply,
        }
    )
    state_model.qa_history = _trim_qa_history(full_qa_history)
    db.commit()

    return EngagementReplyResponse(answer=reply)


@router.get("/history")
async def get_history(
    author_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    limit: int = settings.API_DEFAULT_PAGE_SIZE,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    if conversation_id:
        query = db.query(ChatSession).filter(ChatSession.conversation_id == conversation_id)
        if author_id:
            query = query.filter(ChatSession.authorId == author_id)

        sessions = _paginate_query(
            query.order_by(ChatSession.timestamp.asc()),
            limit=limit,
            offset=offset,
        ).all()
        return [
            {
                "conversation_id": session.conversation_id,
                "idea": session.idea,
                "timestamp": session.timestamp,
                "user_name": session.user_name,
            }
            for session in sessions
        ]

    if not author_id:
        return {"items": [], "total": 0, "offset": offset, "limit": limit}

    cache_key = f"idealab:history:{author_id}:{offset}:{limit}"
    redis = get_redis()
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Redis GET failed for history cache: %s", exc)

    total: int = (
        db.query(func.count(func.distinct(ChatSession.conversation_id)))
        .filter(ChatSession.authorId == author_id)
        .scalar()
    ) or 0

    subquery = (
        db.query(
            ChatSession.conversation_id,
            func.min(ChatSession.timestamp).label("min_ts"),
        )
        .filter(ChatSession.authorId == author_id)
        .group_by(ChatSession.conversation_id)
        .subquery()
    )

    sessions = _paginate_query(
        db.query(ChatSession)
        .join(
            subquery,
            (ChatSession.conversation_id == subquery.c.conversation_id)
            & (ChatSession.timestamp == subquery.c.min_ts),
        )
        .order_by(ChatSession.timestamp.desc()),
        limit=limit,
        offset=offset,
    ).all()

    result = {
        "items": [
            {
                "conversation_id": session.conversation_id,
                "idea": session.idea,
                "timestamp": str(session.timestamp),
                "user_name": session.user_name,
            }
            for session in sessions
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }

    if redis is not None:
        try:
            await redis.set(cache_key, json.dumps(result), ex=HISTORY_CACHE_TTL)
        except Exception as exc:
            logger.warning("Redis SET failed for history cache: %s", exc)

    return result


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
    conversation_sessions = _load_feasibility_conversation_messages(db, identifier)
    first_session = conversation_sessions[0] if conversation_sessions else None
    if not state_model or not first_session:
        return {"error": "Conversation not found"}

    return {
        "conversation_id": identifier,
        "idea": first_session.idea,
        "user_name": first_session.user_name,
        "ideal_customer": first_session.ideal_customer,
        "problem_solved": first_session.what_problem_it_solves,
        "analysis": state_model.analysis,
        "engagement_question": generate_engagement_question_from_analysis(
            first_session.idea or "",
            state_model.analysis or "",
            get_llm(temperature=0.4),
        ),
        "qa_history": state_model.qa_history or [],
        "messages": [
            {
                "human_message": session.human_message,
                "ai_message": session.ai_message,
                "timestamp": session.timestamp,
            }
            for session in conversation_sessions
        ],
    }


@router.get("/sessions", response_model=list[LectureChatSessionOut], tags=["History"])
def list_sessions(
    author_id: Optional[str] = None,
    limit: int = settings.API_DEFAULT_PAGE_SIZE,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    try:
        query = db.query(LectureChatSession)
        if author_id:
            query = query.filter(LectureChatSession.author_id == author_id)
        return _paginate_query(
            query.order_by(LectureChatSession.created_at.desc()),
            limit=limit,
            offset=offset,
        ).all()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database error while loading chat sessions.",
        ) from exc


@router.patch("/transcripts/{transcript_id}", response_model=LectureTranscriptAssetOut, tags=["Transcript"])
def update_transcript(transcript_id: int, payload: TranscriptUpdate, db: Session = Depends(get_db)):
    try:
        transcript = (
            db.query(LectureTranscriptAsset)
            .options(_transcript_metadata_response_loader())
            .filter_by(id=transcript_id)
            .first()
        )
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=500,
            detail="Database error while loading transcript metadata.",
        ) from exc

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")
        
    if payload.session_name is not None:
        transcript.session_name = payload.session_name
    if payload.source_name is not None:
        transcript.source_name = payload.source_name
        
    if transcript.metadata_entry:
        if payload.course_name is not None:
            transcript.metadata_entry.course_name = payload.course_name
        if payload.instructor_name is not None:
            transcript.metadata_entry.instructor_name = payload.instructor_name
        if payload.session_date is not None:
            transcript.metadata_entry.session_date = payload.session_date
        if payload.description is not None:
            transcript.metadata_entry.description = payload.description
        if payload.tags is not None:
            transcript.metadata_entry.tags = payload.tags
            
    try:
        db.commit()
        return (
            db.query(LectureTranscriptAsset)
            .options(_transcript_metadata_response_loader())
            .filter_by(id=transcript_id)
            .first()
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error while updating transcript.") from exc


@router.get("/transcripts", response_model=list[LectureTranscriptAssetOut], tags=["Transcript"])
def list_transcripts(
    limit: int = settings.API_DEFAULT_PAGE_SIZE,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    try:
        return _paginate_query(
            db.query(LectureTranscriptAsset)
            .options(_transcript_metadata_response_loader())
            .order_by(LectureTranscriptAsset.created_at.desc()),
            limit=limit,
            offset=offset,
        ).all()
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

        active_collection_name = (
            transcript.metadata_entry.qdrant_collection_name
            if transcript.metadata_entry
            else settings.LECTURE_QDRANT_COLLECTION_NAME
        )

        new_collection_name, chunks_indexed = reindex_transcript_with_shadow_collection(
            text=cleaned_text,
            source_name=transcript.source_name,
            transcript_id=transcript.id,
            session_name=transcript.session_name,
            object_path=transcript.object_path,
            active_collection_name=active_collection_name,
        )

        if transcript.metadata_entry:
            transcript.metadata_entry.qdrant_collection_name = new_collection_name
            transcript.metadata_entry.transcript_text = cleaned_text
            transcript.metadata_entry.transcript_summary = None
            transcript.metadata_entry.summary_generated_at = None
        else:
            db.add(
                LectureTranscriptMetadata(
                    transcript_id=transcript.id,
                    storage_path=transcript.object_path,
                    qdrant_collection_name=new_collection_name,
                    transcript_text=cleaned_text,
                    transcript_summary=None,
                    summary_generated_at=None,
                )
            )

        transcript.chunks_indexed = chunks_indexed
        _commit_or_500(db, "reprocess transcript")

        if active_collection_name != new_collection_name:
            try:
                if active_collection_name == settings.LECTURE_QDRANT_COLLECTION_NAME:
                    delete_transcript_points(
                        transcript_id=transcript.id,
                        object_path=transcript.object_path,
                        collection_name=active_collection_name,
                    )
                else:
                    delete_collection_if_exists(active_collection_name)
            except Exception:
                logger.exception(
                    "lecture_rag.reprocess_cleanup_failed transcript_id=%s collection_name=%s",
                    transcript.id,
                    active_collection_name,
                )
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
