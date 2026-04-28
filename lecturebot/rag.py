from __future__ import annotations

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
from sentence_transformers import SentenceTransformer

from core.config import settings
from core.logging import get_logger, truncate_for_log


client_qdrant: QdrantClient | None = None
embedding_model: SentenceTransformer | None = None
logger = get_logger(__name__)


def get_embedding_model() -> SentenceTransformer:
    global embedding_model
    if embedding_model is None:
        logger.info("embedding_model.load name=%s", settings.LECTURE_EMBEDDING_MODEL)
        embedding_model = SentenceTransformer(settings.LECTURE_EMBEDDING_MODEL)
    return embedding_model


def get_qdrant_client() -> QdrantClient:
    global client_qdrant
    if client_qdrant is None:
        client_qdrant = QdrantClient(path=settings.lecture_qdrant_path)
    return client_qdrant


def ensure_collection() -> None:
    qdrant_client = get_qdrant_client()
    existing = [
        collection.name for collection in qdrant_client.get_collections().collections
    ]
    if settings.LECTURE_QDRANT_COLLECTION_NAME not in existing:
        qdrant_client.create_collection(
            collection_name=settings.LECTURE_QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(
                size=settings.LECTURE_VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        return

    collection_info = qdrant_client.get_collection(settings.LECTURE_QDRANT_COLLECTION_NAME)
    vectors_config = collection_info.config.params.vectors
    current_size = getattr(vectors_config, "size", None)
    if current_size is None and isinstance(vectors_config, dict):
        default_vector = next(iter(vectors_config.values()), None)
        current_size = getattr(default_vector, "size", None)

    if current_size == settings.LECTURE_VECTOR_SIZE:
        return

    logger.warning(
        "qdrant.collection.recreate name=%s old_vector_size=%s new_vector_size=%s",
        settings.LECTURE_QDRANT_COLLECTION_NAME,
        current_size,
        settings.LECTURE_VECTOR_SIZE,
    )
    qdrant_client.delete_collection(settings.LECTURE_QDRANT_COLLECTION_NAME)
    qdrant_client.create_collection(
        collection_name=settings.LECTURE_QDRANT_COLLECTION_NAME,
        vectors_config=VectorParams(
            size=settings.LECTURE_VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )


def embed_text(text: str) -> List[float]:
    return get_embedding_model().encode(
        text,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    words = text.split()
    chunks: List[str] = []
    step = chunk_size - overlap
    for index in range(0, len(words), step):
        chunk = " ".join(words[index : index + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def index_transcript(
    text: str,
    source_name: str,
    metadata: dict | None = None,
) -> int:
    if not text.strip():
        raise ValueError("Transcript text cannot be empty.")

    ensure_collection()
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
        collection_name=settings.LECTURE_QDRANT_COLLECTION_NAME,
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
    if transcript_id is not None:
        must_conditions.append(
            FieldCondition(key="transcript_id", match=MatchValue(value=transcript_id))
        )
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
) -> List[dict]:
    ensure_collection()
    results = get_qdrant_client().query_points(
        collection_name=settings.LECTURE_QDRANT_COLLECTION_NAME,
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
    )
    return chunks


def delete_transcript_points(
    *,
    transcript_id: int | None = None,
    object_path: str = "",
) -> None:
    ensure_collection()
    query_filter = _build_filter(
        transcript_id=transcript_id,
        object_path=object_path,
    )
    if query_filter is None:
        raise ValueError("Transcript filter is required to delete indexed points.")

    get_qdrant_client().delete(
        collection_name=settings.LECTURE_QDRANT_COLLECTION_NAME,
        points_selector=FilterSelector(filter=query_filter),
    )
