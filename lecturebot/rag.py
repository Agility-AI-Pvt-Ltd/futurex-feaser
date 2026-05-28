from __future__ import annotations

import re
import uuid
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)
from fastembed import TextEmbedding

from core.config import settings
from core.fastembed_cache import get_fastembed_cache_dir
from core.logging import get_logger, truncate_for_log
from core.qdrant_client import get_local_qdrant_client


embedding_model: TextEmbedding | None = None
logger = get_logger(__name__)


def _default_collection_name() -> str:
    return settings.LECTURE_QDRANT_COLLECTION_NAME


def get_embedding_model() -> TextEmbedding:
    if not settings.qdrant_enabled:
        raise RuntimeError("Qdrant is disabled because QDRANT_BACKEND=none.")

    global embedding_model
    if embedding_model is None:
        logger.info("embedding_model.load name=%s", settings.LECTURE_EMBEDDING_MODEL)
        embedding_model = TextEmbedding(
            model_name=settings.LECTURE_EMBEDDING_MODEL,
            cache_dir=get_fastembed_cache_dir(),
            providers=["CPUExecutionProvider"],
        )
    return embedding_model


def get_qdrant_client() -> QdrantClient:
    return get_local_qdrant_client(settings.lecture_qdrant_path)


_verified_collections: set[str] = set()


def ensure_collection(collection_name: str | None = None) -> None:
    if not settings.qdrant_enabled:
        return

    collection_name = collection_name or _default_collection_name()
    if collection_name in _verified_collections:
        return

    qdrant_client = get_qdrant_client()
    existing = [
        collection.name for collection in qdrant_client.get_collections().collections
    ]
    if collection_name not in existing:
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=settings.LECTURE_VECTOR_SIZE,
                distance=Distance.COSINE,
                on_disk=True,
            ),
        )
        _verified_collections.add(collection_name)
        return

    collection_info = qdrant_client.get_collection(collection_name)
    vectors_config = collection_info.config.params.vectors
    current_size = getattr(vectors_config, "size", None)
    if current_size is None and isinstance(vectors_config, dict):
        default_vector = next(iter(vectors_config.values()), None)
        current_size = getattr(default_vector, "size", None)

    if current_size == settings.LECTURE_VECTOR_SIZE:
        _verified_collections.add(collection_name)
        return

    logger.warning(
        "qdrant.collection.recreate name=%s old_vector_size=%s new_vector_size=%s",
        collection_name,
        current_size,
        settings.LECTURE_VECTOR_SIZE,
    )
    qdrant_client.delete_collection(collection_name)
    qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=settings.LECTURE_VECTOR_SIZE,
            distance=Distance.COSINE,
            on_disk=True,
        ),
    )
    _verified_collections.add(collection_name)


def embed_text(text: str) -> List[float]:
    return next(get_embedding_model().embed([text])).tolist()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    # Split text into sentences using simple regex
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks: List[str] = []
    current_chunk_words: List[str] = []
    current_word_count = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_words = sentence.split()
        sentence_word_count = len(sentence_words)

        # If a single sentence is longer than chunk_size, split it by words as fallback
        if sentence_word_count > chunk_size:
            if current_chunk_words:
                chunks.append(" ".join(current_chunk_words))
                current_chunk_words = []
                current_word_count = 0

            for i in range(0, sentence_word_count, chunk_size - overlap):
                chunk = " ".join(sentence_words[i : i + chunk_size])
                if chunk:
                    chunks.append(chunk)
            continue

        if current_word_count + sentence_word_count > chunk_size:
            chunks.append(" ".join(current_chunk_words))

            # Maintain overlapping words at sentence boundary
            overlap_words: List[str] = []
            overlap_count = 0
            for word in reversed(current_chunk_words):
                if overlap_count + 1 > overlap:
                    break
                overlap_words.insert(0, word)
                overlap_count += 1

            current_chunk_words = overlap_words + sentence_words
            current_word_count = len(current_chunk_words)
        else:
            current_chunk_words.extend(sentence_words)
            current_word_count += sentence_word_count

    if current_chunk_words:
        chunks.append(" ".join(current_chunk_words))

    return chunks


def index_transcript(
    text: str,
    source_name: str,
    metadata: dict | None = None,
    *,
    collection_name: str | None = None,
) -> int:
    if not settings.qdrant_enabled:
        logger.info("lecture_rag.index_skipped qdrant_backend=none source=%s", source_name)
        return 0

    if not text.strip():
        raise ValueError("Transcript text cannot be empty.")

    collection_name = collection_name or _default_collection_name()
    ensure_collection(collection_name)
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("Transcript did not contain enough text to index.")

    points = []
    for chunk in chunks:
        payload = {"text": chunk, "source": source_name}
        if metadata:
            payload.update(metadata)
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embed_text(chunk),
                payload=payload,
            )
        )

    get_qdrant_client().upsert(
        collection_name=collection_name,
        points=points,
    )
    return len(points)


def _build_filter(
    *,
    transcript_id: int | None = None,
    source_name: str = "",
    session_name: str = "",
    object_path: str = "",
) -> Filter | None:
    must_conditions: list[FieldCondition] = []
    
    # If transcript_id is provided, it uniquely identifies the transcript chunks.
    # We do NOT want to filter by session_name or source_name in addition, 
    # because if they were updated via the Admin UI, Qdrant will still have the old names 
    # and the filter would fail.
    if transcript_id is not None:
        must_conditions.append(
            FieldCondition(key="transcript_id", match=MatchValue(value=transcript_id))
        )
        return Filter(must=must_conditions)

    if object_path:
        must_conditions.append(
            FieldCondition(key="object_path", match=MatchValue(value=object_path))
        )
    if session_name:
        must_conditions.append(
            FieldCondition(key="session_name", match=MatchValue(value=session_name))
        )
    if source_name:
        must_conditions.append(
            FieldCondition(key="source", match=MatchValue(value=source_name))
        )
    if not must_conditions:
        return None
    return Filter(must=must_conditions)


def search_similar(
    query: str,
    top_k: int = 5,
    *,
    transcript_id: int | None = None,
    source_name: str = "",
    session_name: str = "",
    object_path: str = "",
    collection_name: str | None = None,
) -> List[dict]:
    if not settings.qdrant_enabled:
        logger.info("lecture_rag.search_skipped qdrant_backend=none")
        return []

    collection_name = collection_name or _default_collection_name()
    ensure_collection(collection_name)
    results = get_qdrant_client().query_points(
        collection_name=collection_name,
        query=embed_text(query),
        limit=top_k,
        with_payload=True,
        query_filter=_build_filter(
            transcript_id=transcript_id,
            source_name=source_name,
            session_name=session_name,
            object_path=object_path,
        ),
    ).points

    chunks = [
        {
            "text": hit.payload["text"],
            "source": hit.payload.get("source", ""),
            "score": hit.score,
            "session_name": hit.payload.get("session_name", ""),
            "object_path": hit.payload.get("object_path", ""),
        }
        for hit in results
    ]
    logger.info(
        "lecture_rag.search result_count=%s query=%s",
        len(chunks),
        truncate_for_log(query, settings.LECTURE_LOG_PROMPT_CHARS),
        extra={
            "axiom_event": "rag_search",
            "query": query,
            "transcript_id": transcript_id,
            "session_name": session_name,
            "top_k": top_k,
            "result_count": len(chunks),
            "chunks": [
                {
                    "text": c["text"][:100] + ("..." if len(c["text"]) > 100 else ""),
                    "score": c["score"],
                    "source": c["source"]
                }
                for c in chunks
            ]
        }
    )

    # Print chunks to the terminal for debugging
    print(f"\n[RAG SEARCH] Retrieved {len(chunks)} chunks for query: '{query}'")
    for i, c in enumerate(chunks, 1):
        print(f"--- Chunk {i} (Score: {c['score']:.4f}) ---")
        print(c['text'])
        print("-" * 40)
    print()
    return chunks


def delete_transcript_points(
    *,
    transcript_id: int | None = None,
    object_path: str = "",
    collection_name: str | None = None,
) -> None:
    if not settings.qdrant_enabled:
        return

    collection_name = collection_name or _default_collection_name()
    ensure_collection(collection_name)
    query_filter = _build_filter(
        transcript_id=transcript_id,
        object_path=object_path,
    )
    if query_filter is None:
        raise ValueError("Transcript filter is required to delete indexed points.")

    get_qdrant_client().delete(
        collection_name=collection_name,
        points_selector=FilterSelector(filter=query_filter),
    )


def create_shadow_collection_name(base_collection_name: str | None = None) -> str:
    base = base_collection_name or _default_collection_name()
    return f"{base}_tmp_{uuid.uuid4().hex}"


def delete_collection_if_exists(collection_name: str) -> None:
    if not settings.qdrant_enabled:
        return

    qdrant_client = get_qdrant_client()
    existing = {
        collection.name for collection in qdrant_client.get_collections().collections
    }
    if collection_name in existing:
        qdrant_client.delete_collection(collection_name)


def reindex_transcript_with_shadow_collection(
    *,
    text: str,
    source_name: str,
    transcript_id: int,
    session_name: str,
    object_path: str,
    active_collection_name: str | None = None,
) -> tuple[str, int]:
    if not settings.qdrant_enabled:
        logger.info("lecture_rag.reindex_skipped qdrant_backend=none transcript_id=%s", transcript_id)
        return active_collection_name or _default_collection_name(), 0

    active_collection_name = active_collection_name or _default_collection_name()
    shadow_collection_name = create_shadow_collection_name(active_collection_name)

    try:
        ensure_collection(shadow_collection_name)
        chunks_indexed = index_transcript(
            text,
            source_name=source_name,
            metadata={
                "transcript_id": transcript_id,
                "session_name": session_name,
                "object_path": object_path,
            },
            collection_name=shadow_collection_name,
        )
    except Exception:
        delete_collection_if_exists(shadow_collection_name)
        raise

    logger.info(
        "lecture_rag.shadow_reindex_ready transcript_id=%s active_collection=%s shadow_collection=%s chunks_indexed=%s",
        transcript_id,
        active_collection_name,
        shadow_collection_name,
        chunks_indexed,
    )
    return shadow_collection_name, chunks_indexed
