import requests
import uuid

session_id = str(uuid.uuid4())
payload = {
    "session_id": session_id,
    "message": "Why is a Starbucks coffee priced at $400 and a chai?",
    "transcript_id": 1 
}

# The transcript_id is likely 1, let's just omit it or try 1.
# Actually, the user's session_id was 22d3b175-3102-4d65-a825-04b218c69ffb. We can reuse that or new one.
payload = {
    "session_id": "22d3b175-3102-4d65-a825-04b218c69ffb",
    "message": "Why is a Starbucks coffee priced at $400 and a chai?",
}

res = requests.post("http://127.0.0.1:8888/chat", json=payload)
print(res.status_code)
print(res.json())
