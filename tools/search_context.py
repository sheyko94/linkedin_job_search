"""Dependencies supplied for one search invocation, outside graph state."""

from dataclasses import dataclass

from tools.browser_session import BrowserSession


@dataclass(frozen=True)
class SearchContext:
    browser: BrowserSession
