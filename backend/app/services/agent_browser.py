"""Browser session management for agent mode."""

from __future__ import annotations

import atexit
from contextlib import suppress
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


class BrowserSessionError(RuntimeError):
    """Base class for browser session errors."""


class SessionNotFoundError(BrowserSessionError):
    """Raised when an unknown session identifier is referenced."""


class BrowserActionError(BrowserSessionError):
    """Raised when a browser operation fails."""


@dataclass(slots=True)
class _BrowserSession:
    """Thin wrapper around a Playwright page with retry support."""

    context: Any
    page: Any
    action_timeout_ms: int
    navigation_timeout_ms: int
    max_retries: int
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _last_active: float = field(default_factory=time.monotonic, init=False, repr=False)

    def __post_init__(self) -> None:
        self.page.set_default_timeout(self.action_timeout_ms)
        self.page.set_default_navigation_timeout(self.navigation_timeout_ms)

    @property
    def last_active(self) -> float:
        return self._last_active

    def close(self) -> None:
        with self._lock:
            try:
                self.page.close()
            except Exception:
                pass
            try:
                self.context.close()
            except Exception:
                pass

    def _run(self, func: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            with self._lock:
                try:
                    result = func()
                except (PlaywrightTimeout, PlaywrightError) as exc:
                    last_error = exc
                except Exception as exc:
                    raise BrowserActionError(str(exc)) from exc
                else:
                    self._last_active = time.monotonic()
                    return result
            if attempt < self.max_retries:
                time.sleep(0.1)
        assert last_error is not None  # pragma: no cover - defensive
        raise BrowserActionError(str(last_error)) from last_error

    def navigate(self, url: str) -> Dict[str, Any]:
        clean_url = (url or "").strip()
        if not clean_url:
            raise ValueError("url is required")

        def _go() -> Dict[str, Any]:
            self.page.goto(clean_url, wait_until="load")
            return {"url": self.page.url}

        return self._run(_go)

    def click(self, selector: str | None = None, text: str | None = None) -> Dict[str, Any]:
        clean_selector = (selector or "").strip()
        clean_text = (text or "").strip()
        if not clean_selector and not clean_text:
            raise ValueError("selector or text is required")

        def _click() -> Dict[str, Any]:
            if clean_selector:
                self.page.wait_for_selector(clean_selector, timeout=self.action_timeout_ms)
                target = self.page.locator(clean_selector)
            else:
                locator = self.page.get_by_text(clean_text, exact=False)
                target = locator.first
            target.click(timeout=self.action_timeout_ms)
            return {"url": self.page.url}

        return self._run(_click)

    def type(self, selector: str, text: str) -> Dict[str, Any]:
        clean_selector = (selector or "").strip()
        if not clean_selector:
            raise ValueError("selector is required")
        body = text if isinstance(text, str) else str(text)

        def _type() -> Dict[str, Any]:
            self.page.wait_for_selector(clean_selector, timeout=self.action_timeout_ms)
            self.page.fill(clean_selector, body, timeout=self.action_timeout_ms)
            return {"url": self.page.url, "text": body}

        return self._run(_type)

    def extract(self) -> Dict[str, Any]:
        def _extract() -> Dict[str, Any]:
            html = self.page.content()
            try:
                text = self.page.inner_text("body")
            except (PlaywrightTimeout, PlaywrightError):
                text = ""
            return {"url": self.page.url, "html": html, "text": text}

        return self._run(_extract)

    def reload(self) -> Dict[str, Any]:
        def _reload() -> Dict[str, Any]:
            self.page.reload(wait_until="load")
            return {"url": self.page.url}

        return self._run(_reload)


class AgentBrowserManager:
    """Manage short-lived Playwright sessions for agent actions."""

    def __init__(
        self,
        *,
        idle_timeout: float = 120.0,
        action_timeout_ms: int = 5_000,
        navigation_timeout_ms: int = 15_000,
        max_retries: int = 1,
        headless: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, _BrowserSession] = {}
        self._idle_timeout = float(idle_timeout)
        self._action_timeout = int(action_timeout_ms)
        self._navigation_timeout = int(navigation_timeout_ms)
        self._max_retries = max(0, int(max_retries))
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=headless)
        self._closed = False
        self._atexit_registered = False
        self._register_atexit()

    def _register_atexit(self) -> None:
        if self._atexit_registered:
            return
        atexit.register(self.close)
        self._atexit_registered = True

    def _safe_close_browser(self, browser: Any | None, *, timeout: float = 2.0) -> None:
        if browser is None:
            return

        done = threading.Event()

        def _close() -> None:
            with suppress(Exception, KeyboardInterrupt):
                browser.close()
            done.set()

        thread = threading.Thread(target=_close, name="AgentBrowserClose", daemon=True)
        thread.start()
        done.wait(max(0.0, float(timeout)))

    def close(self) -> None:
        sessions: list[_BrowserSession] = []
        browser = None
        playwright = None

        with suppress(Exception):
            with self._lock:
                if getattr(self, "_closed", False):
                    return
                self._closed = True
                sessions = list(self._sessions.values())
                self._sessions.clear()
                browser = getattr(self, "_browser", None)
                playwright = getattr(self, "_playwright", None)
                self._browser = None
                self._playwright = None

        for session in sessions:
            with suppress(Exception, KeyboardInterrupt):
                session.close()

        with suppress(Exception, KeyboardInterrupt):
            self._safe_close_browser(browser, timeout=2.0)

        if playwright is not None:
            with suppress(Exception, KeyboardInterrupt):
                playwright.stop()

    def start_session(self) -> str:
        session_id = secrets.token_hex(8)
        with self._lock:
            self._cleanup_locked()
            context = self._browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            session = _BrowserSession(
                context=context,
                page=page,
                action_timeout_ms=self._action_timeout,
                navigation_timeout_ms=self._navigation_timeout,
                max_retries=self._max_retries,
            )
            self._sessions[session_id] = session
        return session_id

    def navigate(self, session_id: str, url: str) -> Dict[str, Any]:
        session = self._get_session(session_id)
        return session.navigate(url)

    def click(
        self,
        session_id: str,
        selector: str | None = None,
        text: str | None = None,
    ) -> Dict[str, Any]:
        session = self._get_session(session_id)
        return session.click(selector, text)

    def type(self, session_id: str, selector: str, text: str) -> Dict[str, Any]:
        session = self._get_session(session_id)
        return session.type(selector, text)

    def extract(self, session_id: str) -> Dict[str, Any]:
        session = self._get_session(session_id)
        return session.extract()

    def reload(self, session_id: str) -> Dict[str, Any]:
        session = self._get_session(session_id)
        return session.reload()

    def close_session(self, session_id: str) -> None:
        sid = (session_id or "").strip()
        if not sid:
            raise ValueError("sid is required")
        with self._lock:
            session = self._sessions.pop(sid, None)
        if session is None:
            raise SessionNotFoundError(f"unknown session: {sid}")
        session.close()

    def _cleanup_locked(self) -> None:
        if not self._sessions:
            return
        threshold = time.monotonic() - self._idle_timeout
        expired = [
            sid
            for sid, session in self._sessions.items()
            if session.last_active < threshold
        ]
        for sid in expired:
            session = self._sessions.pop(sid, None)
            if session is not None:
                session.close()

    def _get_session(self, session_id: str) -> _BrowserSession:
        sid = (session_id or "").strip()
        if not sid:
            raise ValueError("sid is required")
        with self._lock:
            self._cleanup_locked()
            session = self._sessions.get(sid)
        if session is None:
            raise SessionNotFoundError(f"unknown session: {sid}")
        return session


__all__ = [
    "AgentBrowserManager",
    "BrowserSessionError",
    "SessionNotFoundError",
    "BrowserActionError",
]
