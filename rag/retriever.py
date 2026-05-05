from datetime import datetime, timezone
from pathlib import Path

from core.config import settings
from core.logging import get_logger, log_event, log_exception, truncate_for_log
from core.observability import ls_traceable

logger = get_logger(__name__)


class RagRunLogger:
    def __init__(self, conversation_id: str, query: str):
        log_dir = Path(settings.rag_run_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_conversation_id = _sanitize_filename(conversation_id or "unknown")
        safe_query = _sanitize_filename(query or "query")[:80]
        self.path = log_dir / f"{timestamp}_{safe_conversation_id}_{safe_query}.txt"
        self._fh = self.path.open("w", encoding="utf-8")

    def write(self, text: str = "") -> None:
        self._fh.write(f"{text}\n")
        self._fh.flush()

    def section(self, title: str) -> None:
        self.write("=" * 100)
        self.write(title)
        self.write("=" * 100)

    def close(self) -> None:
        self._fh.close()


def _sanitize_filename(value: str) -> str:
    import re

    normalized = re.sub(r"\s+", "_", value.strip())
    normalized = re.sub(r"[^A-Za-z0-9._-]", "", normalized)
    return normalized or "run"


def _create_rag_run_logger(conversation_id: str, query: str) -> RagRunLogger:
    run_logger = RagRunLogger(conversation_id=conversation_id, query=query)
    run_logger.section("RAG RETRIEVAL START")
    run_logger.write(f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}")
    run_logger.write(f"conversation_id: {conversation_id}")
    run_logger.write(f"retrieval_query: {query}")
    run_logger.write(f"log_file: {run_logger.path}")
    run_logger.write("")
    return run_logger


def _conversation_filter(conversation_id: str):
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    return Filter(
        must=[
            FieldCondition(
                key="conversation_id",
                match=MatchValue(value=conversation_id),
            )
        ]
    )


def conversation_chunk_count(conversation_id: str) -> int:
    """
    Returns the number of persisted chunks for a conversation_id without
    requiring the embedding model to be loaded.
    """
    if not conversation_id:
        return 0

    try:
        import rag.embedder as embedder_mod

        embedder_mod._init_qdrant(load_embedder=False)
        count_result = embedder_mod.qdrant_client.count(
            collection_name=embedder_mod.COLLECTION_NAME,
            count_filter=_conversation_filter(conversation_id),
            exact=True,
        )
        return int(getattr(count_result, "count", count_result or 0))
    except Exception as e:
        logger.error(f"Error counting RAG chunks for conversation {conversation_id}: {e}")
        return 0


def _run_similarity_search(query_vector: list[float], conversation_id: str, top_k: int):
    import rag.embedder as embedder_mod

    query_filter = _conversation_filter(conversation_id)

    if hasattr(embedder_mod.qdrant_client, "query_points"):
        result = embedder_mod.qdrant_client.query_points(
            collection_name=embedder_mod.COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        return list(getattr(result, "points", []) or [])

    if hasattr(embedder_mod.qdrant_client, "search"):
        return list(
            embedder_mod.qdrant_client.search(
                collection_name=embedder_mod.COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
            )
            or []
        )

    raise AttributeError("Qdrant client does not support query_points or search")


@ls_traceable(run_type="retriever", name="retrieve_context", tags=["rag", "retrieval"])
def retrieve_context(conversation_id: str, query: str, top_k: int = 5) -> tuple[str, list]:
    """
    Retrieves the top-k most relevant chunks for the given query
    filtered by conversation_id.
    """
    run_logger = _create_rag_run_logger(conversation_id=conversation_id, query=query)
    try:
        import rag.embedder as embedder_mod
        run_logger.section("RAG RETRIEVAL INPUT")
        run_logger.write(f"conversation_id: {conversation_id}")
        run_logger.write(f"requested_top_k: {top_k}")
        run_logger.write(f"retrieval_query: {query}")
        run_logger.write("")

        if not conversation_id:
            run_logger.section("RAG RETRIEVAL END")
            run_logger.write("reason: missing_conversation_id")
            log_event(
                logger,
                "rag_retrieval_skipped",
                conversation_id=conversation_id,
                retrieval_query=truncate_for_log(query, settings.RAG_LOG_CHUNK_CHARS),
                reason="missing_conversation_id",
                requested_top_k=top_k,
            )
            return "No relevant context found.", []

        chunk_count = conversation_chunk_count(conversation_id)
        run_logger.write(f"persisted_chunk_count: {chunk_count}")
        run_logger.write("")
        if chunk_count == 0:
            run_logger.section("RAG RETRIEVAL END")
            run_logger.write("reason: no_persisted_chunks")
            log_event(
                logger,
                "rag_retrieval_empty",
                conversation_id=conversation_id,
                retrieval_query=truncate_for_log(query, settings.RAG_LOG_CHUNK_CHARS),
                persisted_chunk_count=chunk_count,
                requested_top_k=top_k,
                reason="no_persisted_chunks",
            )
            return "No relevant context found.", []

        embedder_mod._init_qdrant(load_embedder=True)

        query_vector = next(embedder_mod.embedder.embed([query])).tolist()

        search_result = _run_similarity_search(query_vector, conversation_id, top_k)

        if not search_result:
            run_logger.section("RAG RETRIEVAL END")
            run_logger.write("reason: no_matching_chunks")
            log_event(
                logger,
                "rag_retrieval_empty",
                conversation_id=conversation_id,
                retrieval_query=truncate_for_log(query, settings.RAG_LOG_CHUNK_CHARS),
                persisted_chunk_count=chunk_count,
                requested_top_k=top_k,
                result_count=0,
                reason="no_matching_chunks",
            )
            return "No relevant context found.", []

        context_texts = []
        chunks_list = []
        chunk_summaries = []
        run_logger.section("TOP_K_CHUNKS")
        for i, hit in enumerate(search_result):
            payload = getattr(hit, "payload", {}) or {}
            source = payload.get("source", "unknown")
            text = payload.get("text", "")
            score = float(getattr(hit, "score", 0.0) or 0.0)
            preview = truncate_for_log(text, settings.RAG_LOG_CHUNK_CHARS)
            hit_id = str(getattr(hit, "id", "") or "")
            chunk_rank = i + 1

            chunks_list.append({
                "rank": chunk_rank,
                "id": hit_id,
                "source": source,
                "text": text,
                "score": score,
            })
            chunk_summaries.append(
                {
                    "rank": chunk_rank,
                    "id": hit_id,
                    "source": source,
                    "score": score,
                    "preview": preview,
                }
            )
            context_texts.append(f"[{source}] {text}")
            run_logger.write(f"chunk_rank: {chunk_rank}")
            run_logger.write(f"chunk_id: {hit_id}")
            run_logger.write(f"source: {source}")
            run_logger.write(f"score: {score}")
            run_logger.write("chunk_text:")
            run_logger.write(text)
            run_logger.write("")
            log_event(
                logger,
                "rag_retrieval_hit",
                conversation_id=conversation_id,
                retrieval_query=truncate_for_log(query, settings.RAG_LOG_CHUNK_CHARS),
                persisted_chunk_count=chunk_count,
                requested_top_k=top_k,
                chunk_rank=chunk_rank,
                chunk_id=hit_id,
                source=source,
                score=score,
                chunk_preview=preview,
            )

        log_event(
            logger,
            "rag_retrieval",
            conversation_id=conversation_id,
            retrieval_query=truncate_for_log(query, settings.RAG_LOG_CHUNK_CHARS),
            persisted_chunk_count=chunk_count,
            requested_top_k=top_k,
            result_count=len(chunks_list),
            top_chunk_source=chunks_list[0]["source"] if chunks_list else None,
            top_chunk_score=chunks_list[0]["score"] if chunks_list else None,
            top_chunks=chunk_summaries,
        )
        run_logger.section("RAG RETRIEVAL END")
        run_logger.write(f"result_count: {len(chunks_list)}")

        return "\n\n".join(context_texts), chunks_list

    except ImportError as e:
        run_logger.section("RAG RETRIEVAL END")
        run_logger.write(f"error: {e}")
        log_exception(
            logger,
            "rag_retrieval_import_error",
            conversation_id=conversation_id,
            retrieval_query=truncate_for_log(query, settings.RAG_LOG_CHUNK_CHARS),
            requested_top_k=top_k,
            error=str(e),
        )
        return "RAG is not available because dependencies are missing.", []
    except Exception as e:
        run_logger.section("RAG RETRIEVAL END")
        run_logger.write(f"error: {e}")
        log_exception(
            logger,
            "rag_retrieval_error",
            conversation_id=conversation_id,
            retrieval_query=truncate_for_log(query, settings.RAG_LOG_CHUNK_CHARS),
            requested_top_k=top_k,
            error=str(e),
        )
        return "Error retrieving context.", []
    finally:
        run_logger.close()
