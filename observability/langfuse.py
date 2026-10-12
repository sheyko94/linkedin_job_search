"""Optional Langfuse callbacks and export lifecycle for a pipeline run."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from config.settings import settings
from observability.logging import get_logger

logger = get_logger(__name__)
_ACTIVE_CLIENT: ContextVar[Langfuse | None] = ContextVar("langfuse_client", default=None)


def record_guardrail(name: str, *, passed: bool, reason: str, kind: str) -> None:
    """Record decisions without exporting the untrusted URL or affecting enforcement."""
    fields = {"guardrail": name, "passed": passed, "reason": reason, "kind": kind}
    if passed:
        logger.info("guardrail_passed", **fields)
    else:
        logger.warning("guardrail_blocked", **fields)
    client = _ACTIVE_CLIENT.get()
    if client is None:
        return
    try:
        if client.get_current_trace_id() is None:
            return
        with client.start_as_current_observation(
            name=name,
            as_type="guardrail",
            input={"kind": kind},
            output={"passed": passed, "reason": reason},
            level="DEFAULT" if passed else "WARNING",
        ):
            pass
    except Exception as exc:
        logger.warning("guardrail_export_failed", error_type=type(exc).__name__)


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
    client_token = _ACTIVE_CLIENT.set(client)
    try:
        with propagate_attributes(session_id=session_id, trace_name="linkedin-job-search"):
            yield CallbackHandler(public_key=public_key)
    finally:
        _ACTIVE_CLIENT.reset(client_token)
        try:
            client.flush()
        except Exception as exc:
            # Export failures must not replace the workflow's result or error.
            logger.warning("langfuse_flush_failed", error_type=type(exc).__name__)
