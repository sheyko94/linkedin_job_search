"""Optional Langfuse callbacks and export lifecycle for a pipeline run."""

from collections.abc import Iterator
from contextlib import contextmanager

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from config.settings import settings
from observability.logging import get_logger

logger = get_logger(__name__)


@contextmanager
def trace_run(session_id: str) -> Iterator[CallbackHandler | None]:
    """Create a fresh handler and flush exports on success or failure."""
    public_key = settings.langfuse_public_key.strip()
    secret_key = settings.langfuse_secret_key.strip()
    if not public_key and not secret_key:
        yield None
        return
    if not public_key or not secret_key:
        raise ValueError("Set both LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to enable tracing")

    # Settings reads .env without exporting it to os.environ, so configure the
    # SDK explicitly. The handler selects this client's shared resources by key.
    client = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=settings.langfuse_base_url,
    )
    try:
        with propagate_attributes(session_id=session_id, trace_name="linkedin-job-search"):
            yield CallbackHandler(public_key=public_key)
    finally:
        try:
            client.flush()
        except Exception as exc:
            # Export failures must not replace the workflow's result or error.
            logger.warning("langfuse_flush_failed", error_type=type(exc).__name__)
