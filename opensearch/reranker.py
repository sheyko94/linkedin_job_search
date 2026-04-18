import time

from config.logging import get_logger
from config.settings import settings
from opensearch.models import RetrievedChunk

logger = get_logger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder
        _model = CrossEncoder(settings.reranker_model)
    return _model


def rerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    if not chunks:
        return chunks
    start = time.monotonic()
    scores = _get_model().predict([(query, c.text) for c in chunks])
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    top = [c for _, c in ranked[: settings.reranker_top_k]]
    logger.info(
        "reranker_complete",
        input_chunks=len(chunks),
        output_chunks=len(top),
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    return top
