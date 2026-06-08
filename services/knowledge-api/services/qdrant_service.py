from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

import config

VECTOR_SIZE = 384
REPOS_COLLECTION = 'repos'

_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
    return _client


def _ensure_named_collection(name: str) -> None:
    client = get_client()
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def ensure_collection() -> None:
    _ensure_named_collection(config.COLLECTION_NAME)


def ensure_repos_collection() -> None:
    _ensure_named_collection(REPOS_COLLECTION)


def upsert_point(point_id: str, vector: list[float], payload: dict) -> None:
    get_client().upsert(
        collection_name=config.COLLECTION_NAME,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )


def search_points(vector: list[float], limit: int, topic: str | None = None) -> list:
    query_filter = None
    if topic:
        query_filter = Filter(
            must=[FieldCondition(key='topic', match=MatchValue(value=topic))]
        )
    result = get_client().query_points(
        collection_name=config.COLLECTION_NAME,
        query=vector,
        limit=limit,
        with_payload=True,
        query_filter=query_filter,
    )
    return result.points


def upsert_repo_point(repo_id: str, vector: list[float], payload: dict) -> None:
    get_client().upsert(
        collection_name=REPOS_COLLECTION,
        points=[PointStruct(id=repo_id, vector=vector, payload=payload)],
    )


def search_repos(vector: list[float], limit: int = 3) -> list:
    result = get_client().query_points(
        collection_name=REPOS_COLLECTION,
        query=vector,
        limit=limit,
        with_payload=True,
    )
    return result.points


def health_check() -> bool:
    try:
        get_client().get_collections()
        return True
    except Exception:
        return False
