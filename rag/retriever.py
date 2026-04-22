import logging

logger = logging.getLogger(__name__)


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


def retrieve_context(conversation_id: str, query: str, top_k: int = 5) -> tuple[str, list]:
    """
    Retrieves the top-k most relevant chunks for the given query
    filtered by conversation_id.
    """
    try:
        import rag.embedder as embedder_mod

        if not conversation_id:
            print("  [RAG] No conversation_id provided for retrieval.")
            return "No relevant context found.", []

        chunk_count = conversation_chunk_count(conversation_id)
        print(f"  [RAG] Chunk count for conversation_id={conversation_id}: {chunk_count}")
        if chunk_count == 0:
            print(f"  [RAG] No persisted chunks found for conversation_id={conversation_id}.")
            return "No relevant context found.", []

        embedder_mod._init_qdrant(load_embedder=True)

        query_vector = next(embedder_mod.embedder.embed([query])).tolist()

        print(f"  [RAG] Executing Qdrant search for conversation_id={conversation_id}...")
        search_result = _run_similarity_search(query_vector, conversation_id, top_k)

        if not search_result:
            print(f"  [RAG] 🔍 Retrieved 0 matching chunks for query: '{query}'")
            return "No relevant context found.", []

        print(f"\n  [RAG] 🔍 Retrieved top {len(search_result)} chunks for QA:")
        context_texts = []
        chunks_list = []
        for i, hit in enumerate(search_result):
            payload = getattr(hit, "payload", {}) or {}
            source = payload.get("source", "unknown")
            text = payload.get("text", "")
            score = float(getattr(hit, "score", 0.0) or 0.0)

            print(f"    Hit {i+1} | Score: {score:.4f} | Source: {source}")
            preview = (text or "").replace(chr(10), " ").strip()
            print(f"    Retrieved Text: {preview[:350]}{'...' if len(preview) > 350 else ''}\n")

            chunks_list.append({
                "source": source,
                "text": text,
                "score": score,
            })
            context_texts.append(f"[{source}] {text}")

        return "\n\n".join(context_texts), chunks_list

    except ImportError as e:
        logger.error(f"Failed to retrieve context (Imports missing): {e}")
        return "RAG is not available because dependencies are missing.", []
    except Exception as e:
        logger.error(f"Error retrieving context for RAG: {e}")
        return "Error retrieving context.", []
