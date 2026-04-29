import requests
import json

with open("test_transcript_id.txt", "r") as f:
    transcript_id = int(f.read().strip())

query = "Which AI models or tools are mentioned in this discussion?"
url = f"http://127.0.0.1:8888/api/test-rag?query={query}&transcript_id={transcript_id}"

print(f"Fetching chunks for query: '{query}'")
res = requests.get(url)
if res.status_code == 200:
    data = res.json()
    for i, chunk in enumerate(data.get("chunks", []), 1):
        print(f"--- Chunk {i} ---")
        print(f"Score: {chunk.get('score', 0):.4f}")
        print(f"Text:\n{chunk.get('text', '')}")
        print()
else:
    print(f"Failed with status: {res.status_code}")
    print(res.text)
