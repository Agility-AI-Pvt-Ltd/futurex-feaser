import uuid
import json
from lecturebot.rag import search_similar

with open("test_transcript_id.txt", "r") as f:
    transcript_id = int(f.read().strip())

query = "Which AI models or tools are mentioned in this discussion?"

print(f"Querying Qdrant for transcript ID: {transcript_id}")
print(f"Query: '{query}'\n")

chunks = search_similar(query, top_k=5, transcript_id=transcript_id)

for i, chunk in enumerate(chunks, 1):
    print(f"--- Chunk {i} ---")
    print(f"Score: {chunk['score']:.4f}")
    print(f"Text:\n{chunk['text']}")
    print()
    
