import time

from opensearchpy import OpenSearch

from config.logging import get_logger
from config.settings import settings
from opensearch.models import RetrievedChunk

logger = get_logger(__name__)

_client = OpenSearch(settings.opensearch_url)


def search(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    start = time.monotonic()
    response = _client.search(
        index=settings.opensearch_index,
        body={
            "size": top_k,
            "query": {"match": {"text": query}},
        },
        params={"request_timeout": settings.opensearch_timeout},
    )
    logger.info(
        "opensearch_search",
        query=query,
        hits=len(response["hits"]["hits"]),
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    return [
        RetrievedChunk(
            chunk_id=hit["_source"]["chunk_id"],
            document_id=hit["_source"]["document_id"],
            text=hit["_source"]["text"],
            score=hit["_score"],
            metadata=hit["_source"].get("metadata", {}),
        )
        for hit in response["hits"]["hits"]
    ]
