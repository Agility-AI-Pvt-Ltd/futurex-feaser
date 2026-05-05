import requests

payload = {"session_name": "test_session"}
files = {"file": ("test.txt", b"Hello this is a test transcript with enough words to be embedded properly.", "text/plain")}

res = requests.post("http://127.0.0.1:8888/api/upload", data=payload, files=files)
print(res.status_code)
print(res.text)
