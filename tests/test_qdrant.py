from core.config import settings
from core.qdrant_client import get_local_qdrant_client
import traceback

try:
    print("Testing Qdrant connection to", settings.lecture_qdrant_path)
    client = get_local_qdrant_client(settings.lecture_qdrant_path)
    print("Success:", client.get_collections())
except Exception as e:
    print("Failed!")
    traceback.print_exc()
