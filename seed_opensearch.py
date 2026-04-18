"""Insert the mock corpus into OpenSearch.

Usage:
    uv run python scripts/seed_opensearch.py

Requires OpenSearch running at OPENSEARCH_URL (default: http://localhost:9200).
"""

import sys

from opensearchpy import OpenSearch, helpers
from opensearch.models import RetrievedChunk
from config.settings import settings

INDEX = settings.opensearch_index
HOST = settings.opensearch_url

_CORPUS: list[RetrievedChunk] = [
    RetrievedChunk(
        chunk_id="nexus-pricing-1",
        document_id="nexus-pricing",
        text=(
            "Nexus AI Platform offers three pricing tiers. Starter: $49/month, "
            "includes 100k API calls and 5 GB storage. Pro: $299/month, includes "
            "1M API calls, 50 GB storage, and priority support. Enterprise: custom "
            "pricing with unlimited API calls, dedicated infrastructure, and SLA guarantees."
        ),
        score=0.0,
        metadata={"source": "pricing-page", "section": "plans"},
    ),
    RetrievedChunk(
        chunk_id="nexus-auth-1",
        document_id="nexus-api-docs",
        text=(
            "Authentication is handled via API keys. Generate a key from the dashboard "
            "under Settings > API Keys. Pass the key in the Authorization header as "
            "'Bearer <your-key>'. Keys can be scoped to specific resources and rotated "
            "at any time without downtime."
        ),
        score=0.0,
        metadata={"source": "api-docs", "section": "authentication"},
    ),
    RetrievedChunk(
        chunk_id="nexus-rate-limits-1",
        document_id="nexus-api-docs",
        text=(
            "Rate limits are enforced per API key. Starter tier: 10 requests/second, "
            "burst up to 50. Pro tier: 100 requests/second, burst up to 500. "
            "Enterprise tier: configurable. Exceeding the limit returns HTTP 429. "
            "Retry-After header indicates when to retry."
        ),
        score=0.0,
        metadata={"source": "api-docs", "section": "rate-limits"},
    ),
    RetrievedChunk(
        chunk_id="nexus-retention-1",
        document_id="nexus-privacy",
        text=(
            "Data retention policy: user-uploaded data is stored for 90 days by default. "
            "Pro and Enterprise plans can configure retention from 30 days to 7 years. "
            "Data is encrypted at rest (AES-256) and in transit (TLS 1.3). "
            "Deletion requests are processed within 72 hours."
        ),
        score=0.0,
        metadata={"source": "privacy-policy", "section": "data-retention"},
    ),
    RetrievedChunk(
        chunk_id="nexus-sla-1",
        document_id="nexus-sla",
        text=(
            "Nexus guarantees 99.9% uptime for Pro plans and 99.99% for Enterprise. "
            "Maintenance windows are scheduled on Sundays 02:00-04:00 UTC and announced "
            "72 hours in advance. SLA credits: 10% for each hour below guaranteed uptime, "
            "capped at 30% of the monthly bill."
        ),
        score=0.0,
        metadata={"source": "sla", "section": "uptime"},
    ),
    RetrievedChunk(
        chunk_id="nexus-models-1",
        document_id="nexus-api-docs",
        text=(
            "Available models: nexus-fast (latency < 200ms, best for classification), "
            "nexus-balanced (latency < 800ms, general purpose), nexus-deep "
            "(latency < 5s, best for reasoning and long-context tasks). "
            "All models support streaming via SSE."
        ),
        score=0.0,
        metadata={"source": "api-docs", "section": "models"},
    ),
    RetrievedChunk(
        chunk_id="nexus-sdk-1",
        document_id="nexus-quickstart",
        text=(
            "Install the Python SDK: pip install nexus-ai. "
            "Quickstart: from nexus import NexusClient; "
            "client = NexusClient(api_key='...'); "
            "response = client.complete(model='nexus-balanced', prompt='Hello'). "
            "The SDK handles retries, rate-limit backoff, and streaming out of the box."
        ),
        score=0.0,
        metadata={"source": "quickstart", "section": "python-sdk"},
    ),
]


def main() -> None:
    client = OpenSearch(HOST)

    if not client.ping():
        print(f"Cannot reach OpenSearch at {HOST}")
        sys.exit(1)

    if not client.indices.exists(index = INDEX):
        client.indices.create(
            index = INDEX,
            body={
                "mappings": {
                    "properties": {
                        "chunk_id":    {"type": "keyword"},
                        "document_id": {"type": "keyword"},
                        "text":        {"type": "text"},
                        "metadata":    {"type": "object"},
                    }
                }
            },
        )
        print(f"Created index '{INDEX}'")

    actions = [
        {
            "_index": INDEX,
            "_id": chunk.chunk_id,
            "_source": {
                "chunk_id":    chunk.chunk_id,
                "document_id": chunk.document_id,
                "text":        chunk.text,
                "metadata":    chunk.metadata,
            },
        }
        for chunk in _CORPUS
    ]

    success, errors = helpers.bulk(client, actions)
    print(f"Indexed {success} chunk(s)")
    if errors:
        print(f"Errors: {errors}")
        sys.exit(1)


if __name__ == "__main__":
    main()
