"""Keep sync Playwright resources on one thread across graph node executions."""

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from typing import Any, Callable

from playwright.sync_api import sync_playwright

from tools import linkedin


class LinkedInAuthenticationError(RuntimeError):
    """LinkedIn login failed; the search did not produce a valid result."""


class BrowserSession:
    """Runtime resource: graph nodes submit blocking page operations via call()."""

    def __init__(self) -> None:
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="linkedin-browser")
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self.logged_in = False

    def _submit(self, function: Callable, *args: Any, **kwargs: Any) -> Any:
        # Preserve the coordinator's session ID in logs emitted by the browser worker.
        return self._worker.submit(copy_context().run, function, *args, **kwargs).result()

    def __enter__(self) -> "BrowserSession":
        try:
            self._submit(self._open)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _open(self) -> None:
        self._playwright = sync_playwright().start()
        self._browser, self._context = linkedin._create_browser_and_context(self._playwright)
        self._page = self._context.new_page()
        self.logged_in = linkedin.ensure_logged_in(self._page, self._context)

    def call(self, function: Callable, *args: Any, **kwargs: Any) -> Any:
        """Run function(page, ...) on the browser's owning thread and return its result."""
        return self._submit(function, self._page, *args, **kwargs)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            self._submit(self._close)
        finally:
            self._worker.shutdown(wait=True)

    def _close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        finally:
            try:
                if self._browser is not None:
                    self._browser.close()
            finally:
                if self._playwright is not None:
                    self._playwright.stop()
