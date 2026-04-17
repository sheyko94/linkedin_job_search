from opensearchpy import OpenSearch

from config.settings import settings
from search.models import RetrievedChunk

_client = OpenSearch(settings.opensearch_url)


def search(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    response = _client.search(
        index=settings.opensearch_index,
        body={
            "size": top_k,
            "query": {"match": {"text": query}},
        },
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
