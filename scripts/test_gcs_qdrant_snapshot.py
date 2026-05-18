from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from fastembed import TextEmbedding
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.fastembed_cache import get_fastembed_cache_dir
from core.qdrant_client import close_qdrant_clients, get_local_qdrant_client


GCS_HOST = "storage.googleapis.com"
GCS_REGION = "auto"
GCS_SERVICE = "storage"
GCS_REQUEST_TYPE = "goog4_request"
GCS_ALGORITHM = "GOOG4-HMAC-SHA256"
SNAPSHOT_PREFIX = "qdrant-snapshots/smoke"
VECTOR_SIZE = 384


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, datestamp: str) -> bytes:
    date_key = _sign(("GOOG4" + secret_key).encode("utf-8"), datestamp)
    region_key = _sign(date_key, GCS_REGION)
    service_key = _sign(region_key, GCS_SERVICE)
    return _sign(service_key, GCS_REQUEST_TYPE)


def _gcs_headers(
    *,
    access_key_id: str,
    secret_access_key: str,
    method: str,
    bucket_name: str,
    object_name: str,
    body: bytes,
    content_type: str | None = None,
) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    request_timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_uri = f"/{quote(bucket_name, safe='')}/{quote(object_name, safe='/~')}"

    headers = {
        "host": GCS_HOST,
        "x-goog-content-sha256": payload_hash,
        "x-goog-date": request_timestamp,
    }
    if content_type:
        headers["content-type"] = content_type

    signed_header_names = sorted(headers)
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in signed_header_names)
    signed_headers = ";".join(signed_header_names)
    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    credential_scope = f"{datestamp}/{GCS_REGION}/{GCS_SERVICE}/{GCS_REQUEST_TYPE}"
    string_to_sign = "\n".join(
        [
            GCS_ALGORITHM,
            request_timestamp,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(secret_access_key, datestamp),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        f"{GCS_ALGORITHM} "
        f"Credential={access_key_id}/{credential_scope},"
        f"SignedHeaders={signed_headers},"
        f"Signature={signature}"
    )

    request_headers = {key: value for key, value in headers.items() if key != "host"}
    request_headers["Authorization"] = authorization
    return request_headers


def _gcs_request(
    method: str,
    *,
    bucket_name: str,
    access_key_id: str,
    secret_access_key: str,
    object_name: str,
    body: bytes = b"",
    content_type: str | None = None,
) -> requests.Response:
    headers = _gcs_headers(
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        method=method,
        bucket_name=bucket_name,
        object_name=object_name,
        body=body,
        content_type=content_type,
    )
    url = f"https://{GCS_HOST}/{quote(bucket_name, safe='')}/{quote(object_name, safe='/~')}"
    response = requests.request(method, url, headers=headers, data=body, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(
            f"GCS {method} failed with HTTP {response.status_code}: {response.text[:1000]}"
        )
    return response


def _query_points(client: Any, collection_name: str, query_vector: list[float], test_id: str, limit: int = 3) -> list[Any]:
    query_filter = Filter(
        must=[
            FieldCondition(
                key="snapshot_test_id",
                match=MatchValue(value=test_id),
            )
        ]
    )
    if hasattr(client, "query_points"):
        result = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return list(getattr(result, "points", []) or [])

    return list(
        client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
        )
        or []
    )


def _collect_snapshot_points(client: Any, collection_name: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=collection_name,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        points.extend(
            {
                "id": str(point.id),
                "vector": point.vector,
                "payload": point.payload or {},
            }
            for point in batch
        )
        if offset is None:
            return points


def _create_collection(client: Any, collection_name: str) -> None:
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE, on_disk=True),
    )
    client.create_payload_index(
        collection_name=collection_name,
        field_name="snapshot_test_id",
        field_schema=PayloadSchemaType.KEYWORD,
        wait=True,
    )


def _restore_snapshot(client: Any, collection_name: str, snapshot: dict[str, Any]) -> int:
    _create_collection(client, collection_name)
    points = [
        PointStruct(
            id=point["id"],
            vector=point["vector"],
            payload=point["payload"],
        )
        for point in snapshot["points"]
    ]
    client.upsert(collection_name=collection_name, points=points, wait=True)
    return len(points)


def run_smoke_test(delete_gcs_snapshot: bool = False, keep_qdrant_collections: bool = False) -> None:
    load_dotenv()
    console_url = _require_env("GCS_CONSOLE_URL")
    bucket_name = _require_env("GCS_BUCKET_NAME")
    access_key_id = _require_env("GCS_ACCESS_KEY_ID")
    secret_access_key = _require_env("GCS_SECRET_ACCESS_KEY")

    if bucket_name not in console_url:
        raise RuntimeError("GCS_CONSOLE_URL does not appear to point at GCS_BUCKET_NAME.")

    test_id = uuid.uuid4().hex
    source_collection = f"gcs_snapshot_smoke_{test_id[:12]}"
    restored_collection = f"{source_collection}_restore"
    snapshot_object_name = f"{SNAPSHOT_PREFIX}/{test_id}.json"
    client = get_local_qdrant_client(settings.qdrant_path)

    print("GCS env vars loaded.")
    print(f"Bucket: {bucket_name}")
    print(f"Snapshot object: gs://{bucket_name}/{snapshot_object_name}")
    print(f"Qdrant backend: {settings.qdrant_backend}")

    try:
        _create_collection(client, source_collection)

        embedding_model = TextEmbedding(
            model_name=os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5"),
            cache_dir=get_fastembed_cache_dir(),
            providers=["CPUExecutionProvider"],
        )
        docs = [
            "FutureX stores portable Qdrant smoke-test snapshots in Google Cloud Storage.",
            "Reloading the snapshot should restore embeddings and payload metadata.",
            "The restored collection must answer a similarity query from the cloud snapshot.",
        ]
        vectors = list(embedding_model.embed(docs))
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector.tolist(),
                payload={
                    "snapshot_test_id": test_id,
                    "source": "gcs_qdrant_snapshot_smoke",
                    "text": text,
                },
            )
            for text, vector in zip(docs, vectors)
        ]
        client.upsert(collection_name=source_collection, points=points, wait=True)
        print(f"Created and indexed {len(points)} Qdrant test points.")

        query_vector = next(embedding_model.embed(["Can cloud snapshots restore Qdrant embeddings?"])).tolist()
        source_hits = _query_points(client, source_collection, query_vector, test_id)
        if not source_hits:
            raise RuntimeError("Source collection search returned no results.")
        print(f"Source collection search OK. Top score: {source_hits[0].score:.4f}")

        snapshot = {
            "snapshot_format": "futurex-qdrant-portable-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_collection": source_collection,
            "vector_size": VECTOR_SIZE,
            "distance": "COSINE",
            "points": _collect_snapshot_points(client, source_collection),
        }
        snapshot_body = json.dumps(snapshot, indent=2).encode("utf-8")
        _gcs_request(
            "PUT",
            bucket_name=bucket_name,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            object_name=snapshot_object_name,
            body=snapshot_body,
            content_type="application/json",
        )
        print(f"Uploaded snapshot to GCS ({len(snapshot_body)} bytes).")

        downloaded = _gcs_request(
            "GET",
            bucket_name=bucket_name,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            object_name=snapshot_object_name,
        ).content
        restored_snapshot = json.loads(downloaded.decode("utf-8"))
        restored_count = _restore_snapshot(client, restored_collection, restored_snapshot)
        print(f"Reloaded {restored_count} points from GCS snapshot into {restored_collection}.")

        restored_hits = _query_points(client, restored_collection, query_vector, test_id)
        if not restored_hits:
            raise RuntimeError("Restored collection search returned no results.")
        top_payload = restored_hits[0].payload or {}
        if top_payload.get("snapshot_test_id") != test_id:
            raise RuntimeError("Restored search returned a point from the wrong snapshot test.")
        print(f"Restored collection search OK. Top score: {restored_hits[0].score:.4f}")
        print("Smoke test passed.")
    finally:
        if not keep_qdrant_collections:
            for collection_name in (source_collection, restored_collection):
                try:
                    if client.collection_exists(collection_name):
                        client.delete_collection(collection_name)
                        print(f"Deleted temporary Qdrant collection: {collection_name}")
                except Exception as exc:
                    print(f"Warning: failed to delete temporary collection {collection_name}: {exc}")

        if delete_gcs_snapshot:
            try:
                _gcs_request(
                    "DELETE",
                    bucket_name=bucket_name,
                    access_key_id=access_key_id,
                    secret_access_key=secret_access_key,
                    object_name=snapshot_object_name,
                )
                print(f"Deleted GCS snapshot: gs://{bucket_name}/{snapshot_object_name}")
            except Exception as exc:
                print(f"Warning: failed to delete GCS snapshot {snapshot_object_name}: {exc}")

        close_qdrant_clients()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test GCS HMAC credentials, Qdrant embedding snapshot upload, and restore."
    )
    parser.add_argument(
        "--delete-gcs-snapshot",
        action="store_true",
        help="Delete the uploaded GCS snapshot object after the restore test passes.",
    )
    parser.add_argument(
        "--keep-qdrant-collections",
        action="store_true",
        help="Keep temporary Qdrant source and restored collections for manual inspection.",
    )
    args = parser.parse_args()

    try:
        run_smoke_test(
            delete_gcs_snapshot=args.delete_gcs_snapshot,
            keep_qdrant_collections=args.keep_qdrant_collections,
        )
        return 0
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
