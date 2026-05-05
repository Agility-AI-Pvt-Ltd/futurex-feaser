import requests
import json
import uuid

with open("test_transcript_id.txt", "r") as f:
    transcript_id = int(f.read().strip())

session_id = str(uuid.uuid4())

# Specific factual query
payload = {
    "session_id": session_id,
    "message": "Which AI models or tools are mentioned in this discussion?",
    "transcript_id": transcript_id
}
res = requests.post("http://127.0.0.1:8888/api/chat", json=payload)
print("Status:", res.status_code)
try:
    print(json.dumps(res.json(), indent=2))
except:
    print(res.text)

