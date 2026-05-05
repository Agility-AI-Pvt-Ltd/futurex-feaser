import requests
import json

file_path = "/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/GMT20260419-121958_Recording.transcript (1).vtt"

try:
    with open(file_path, "rb") as f:
        files = {
            "file": ("recording.vtt", f, "text/vtt")
        }
        payload = {
            "session_name": "Testing Session VTT"
        }
        print("Uploading transcript...")
        res = requests.post("http://127.0.0.1:8888/api/upload", data=payload, files=files)
        print("Upload Status:", res.status_code)
        
        try:
            data = res.json()
            print(json.dumps(data, indent=2))
        except:
            print("Response text:", res.text)
            
        if res.status_code == 200:
            transcript_id = data.get("metadata_entry", {}).get("transcript_id")
            if not transcript_id:
                print("Could not find transcript_id in response!")
            else:
                with open("test_transcript_id.txt", "w") as out:
                    out.write(str(transcript_id))
except Exception as e:
    print("Error:", e)
