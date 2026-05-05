from core.config import settings
from qdrant_client import QdrantClient
import traceback

try:
    print("Testing Qdrant connection to", settings.lecture_qdrant_path)
    client = QdrantClient(path=settings.lecture_qdrant_path)
    print("Success:", client.get_collections())
except Exception as e:
    print("Failed!")
    traceback.print_exc()
