import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


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
