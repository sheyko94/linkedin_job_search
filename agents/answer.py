"""Answer agent — synthesises retrieved evidence, never retrieves."""

from agents.models import AnswerResult
from opensearch.models import RetrievalResult, RetrievedChunk
from llm import client as llm
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


def _parse(raw: str) -> AnswerResult:
    import json
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1].split("\n", 1)[-1] if "\n" in parts[1] else parts[1]
    return AnswerResult.model_validate(json.loads(text.strip()))


_SYSTEM = """\
You are an answer generation agent. Rules you must never break:
1. Answer ONLY using the provided evidence chunks — never invent or infer beyond them.
2. If the evidence is insufficient, set missing_information to true and explain what is missing.
3. Cite the chunk_ids of every chunk you relied on.
4. Confidence is a float 0.0–1.0 reflecting how well the evidence supports your answer.

Respond with a single JSON object matching this exact schema (no markdown, no extra text):
{
  "answer": "<your answer>",
  "citations": ["<chunk_id>", ...],
  "confidence": <float>,
  "missing_information": <bool>,
  "notes": "<optional string or null>"
}\
"""


def _user_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    evidence = "\n\n".join(f"[{c.chunk_id}] score={c.score:.4f}\n{c.text}" for c in chunks)
    return f"Query: {query}\n\nEvidence:\n{evidence}"


def run(query: str, retrieval: RetrievalResult) -> AnswerResult:
    if not retrieval.chunks:
        logger.warning("answer_agent_no_evidence", query=query)
        return AnswerResult(
            answer="No relevant information was found in the knowledge base.",
            citations=[],
            confidence=0.0,
            missing_information=True,
            notes="Retrieval returned zero chunks.",
        )

    raw = llm.complete(system=_SYSTEM, user=_user_prompt(query, retrieval.chunks), model=settings.answer_model)
    logger.info("answer_agent_llm_response", raw=raw)

    result = _parse(raw)
    logger.info(
        "answer_agent_complete",
        confidence=result.confidence,
        citations=result.citations,
        missing_information=result.missing_information,
    )
    return result
