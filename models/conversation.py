import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Date, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from core.db_base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    authorId = Column(String, index=True)
    conversation_id = Column(String, index=True)
    user_name = Column(String)
    idea = Column(Text)
    what_problem_it_solves = Column(Text)
    ideal_customer = Column(Text)
    human_message = Column(Text)
    ai_message = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)


class AgentStateModel(Base):
    """
    Dedicated table to persist the LangGraph state JSON variables
    (search query, analysis results, and QA memory) independent of the raw chat log.
    """
    __tablename__ = "agent_states"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, unique=True, index=True)
    optimized_query = Column(Text, nullable=True)
    search_results = Column(Text, nullable=True)
    analysis = Column(Text, nullable=True)
    # ── QA Memory fields ───────────────────────────────────────────────────────
    # qa_history: list of {"q": user_question, "a": ai_answer} dicts (full, uncompressed)
    qa_history = Column(JSON, nullable=True, default=list)
    # qa_summary: LLM-generated rolling summary of turns that fell outside the window
    qa_summary = Column(Text, nullable=True, default="")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)




class FeasibilityReport(Base):
    """
    Stores the structured JSON output from the final Feasibility LLM agent node.
    """
    __tablename__ = "feasibility_reports"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, unique=True, index=True)
    chain_of_thought = Column(JSON)  # Stores the array of reasoning steps
    idea_fit = Column(Text)
    competitors = Column(Text)
    opportunity = Column(Text)
    score = Column(String)
    targeting = Column(Text)
    next_step = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AuthorDailyUsage(Base):
    """
    Tracks how many scrape-triggering requests an author has made on a given UTC day.
    """
    __tablename__ = "author_daily_usage"
    __table_args__ = (
        UniqueConstraint("author_id", "usage_date", name="uq_author_daily_usage_author_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    author_id = Column(String, nullable=False, index=True)
    usage_date = Column(Date, nullable=False, index=True)
    scrape_requests_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )


class LectureChatSession(Base):
    __tablename__ = "lecture_chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    author_id = Column(String, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_mentor_requested = Column(Boolean, default=False)
    memory_summary = Column(Text, default="")
    transcript_id = Column(Integer, ForeignKey("lecture_transcript_assets.id"), nullable=True)

    transcript = relationship("LectureTranscriptAsset", foreign_keys=[transcript_id])
    messages = relationship(
        "LectureMessage",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    transcripts = relationship(
        "LectureTranscriptAsset",
        back_populates="session",
        cascade="all, delete-orphan",
        foreign_keys="[LectureTranscriptAsset.session_id]"
    )


class LectureMessage(Base):
    __tablename__ = "lecture_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("lecture_chat_sessions.session_id"))
    role = Column(String)
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("LectureChatSession", back_populates="messages")


class LectureTranscriptAsset(Base):
    __tablename__ = "lecture_transcript_assets"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("lecture_chat_sessions.session_id"), index=True)
    session_name = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    bucket_name = Column(String, nullable=False)
    object_path = Column(String, nullable=False, unique=True)
    chunks_indexed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("LectureChatSession", back_populates="transcripts", foreign_keys=[session_id])
    metadata_entry = relationship(
        "LectureTranscriptMetadata",
        back_populates="transcript",
        cascade="all, delete-orphan",
        uselist=False,
    )


class LectureTranscriptMetadata(Base):
    __tablename__ = "lecture_transcript_metadata"

    id = Column(Integer, primary_key=True, index=True)
    transcript_id = Column(
        Integer,
        ForeignKey("lecture_transcript_assets.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    course_name = Column(String, nullable=False, default="")
    instructor_name = Column(String, nullable=False, default="")
    session_date = Column(String, nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    tags = Column(Text, nullable=False, default="")
    storage_path = Column(String, nullable=False)
    qdrant_collection_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    transcript = relationship("LectureTranscriptAsset", back_populates="metadata_entry")
