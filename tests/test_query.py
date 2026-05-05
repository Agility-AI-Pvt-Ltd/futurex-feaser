import requests
import json
import uuid

with open("test_transcript_id.txt", "r") as f:
    transcript_id = int(f.read().strip())

session_id = str(uuid.uuid4())

print("Testing chat endpoint...")

# First, a greeting to test the new prompt flexibility
payload1 = {
    "session_id": session_id,
    "message": "Hello!",
    "transcript_id": transcript_id
}
res1 = requests.post("http://127.0.0.1:8888/api/chat", json=payload1)
print("--- Greeting Query ---")
print("Status:", res1.status_code)
try:
    print(json.dumps(res1.json(), indent=2))
except:
    print(res1.text)

# Second, ask what the lecture is about (a general question to see retrieval in action)
payload2 = {
    "session_id": session_id,
    "message": "Summarize the main topic of this recording.",
    "transcript_id": transcript_id
}
res2 = requests.post("http://127.0.0.1:8888/api/chat", json=payload2)
print("\n--- Substantive Query ---")
print("Status:", res2.status_code)
try:
    print(json.dumps(res2.json(), indent=2))
except:
    print(res2.text)

