"""Browser session management for agent mode."""

from __future__ import annotations

import atexit
import queue
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
    """Facade that proxies requests to a dedicated Playwright worker thread."""

    def __init__(
        self,
        *,
        default_timeout_s: int = 15,
        headless: bool = True,
        idle_timeout: float = 120.0,
        action_timeout_ms: int = 5_000,
        navigation_timeout_ms: int = 15_000,
        max_retries: int = 1,
    ) -> None:
        self._default_timeout_s = max(1, int(default_timeout_s))
        self._worker = _BrowserWorker(
            default_timeout_s=self._default_timeout_s,
            headless=bool(headless),
            idle_timeout=float(idle_timeout),
            action_timeout_ms=int(action_timeout_ms),
            navigation_timeout_ms=int(navigation_timeout_ms),
            max_retries=max(0, int(max_retries)),
        )
        self._worker.start()
        try:
            self._worker.wait_until_ready(timeout=self._default_timeout_s)
        except Exception:
            self._worker.stop()
            raise
        self._stopped = False
        self._register_atexit()

    def _register_atexit(self) -> None:
        atexit.register(self.stop)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._worker.stop()

    def close(self) -> None:  # Backwards compatibility
        self.stop()

    def start_session(self) -> str:
        result = self._request("start_session")
        sid = result.get("sid")
        if not sid:
            raise BrowserActionError("failed to create browser session")
        return sid

    def navigate(self, session_id: str, url: str) -> Dict[str, Any]:
        return self._request("navigate", sid=session_id, url=url)

    def click(
        self,
        session_id: str,
        selector: str | None = None,
        text: str | None = None,
    ) -> Dict[str, Any]:
        return self._request("click", sid=session_id, selector=selector, text=text)

    def type(self, session_id: str, selector: str, text: str) -> Dict[str, Any]:
        return self._request("type", sid=session_id, selector=selector, text=text)

    def extract(self, session_id: str) -> Dict[str, Any]:
        return self._request("extract", sid=session_id)

    def reload(self, session_id: str) -> Dict[str, Any]:
        return self._request("reload", sid=session_id)

    def close_session(self, session_id: str) -> None:
        self._request("close_session", sid=session_id)

    def health(self) -> bool:
        try:
            response = self._request("ping")
        except (BrowserSessionError, BrowserActionError):
            return False
        return bool(response.get("ok", True))

    def _request(self, op: str, **kwargs: Any) -> Dict[str, Any]:
        response = self._worker.call(op, **kwargs)
        if response.get("status") == "ok":
            return response.get("result", {}) or {}

        error_type = response.get("error_type", "BrowserActionError")
        message = response.get("message", "browser operation failed")

        if error_type == "SessionNotFoundError":
            raise SessionNotFoundError(message)
        if error_type == "ValueError":
            raise ValueError(message)
        if error_type == "BrowserActionError":
            raise BrowserActionError(message)
        raise BrowserActionError(message)


class _BrowserWorker(threading.Thread):
    """Owns Playwright objects and executes commands on a single thread."""

    def __init__(
        self,
        *,
        default_timeout_s: int,
        headless: bool,
        idle_timeout: float,
        action_timeout_ms: int,
        navigation_timeout_ms: int,
        max_retries: int,
    ) -> None:
        super().__init__(name="AgentBrowserWorker", daemon=True)
        self._default_timeout_s = max(1, int(default_timeout_s))
        self._headless = bool(headless)
        self._queue: "queue.Queue[tuple[str, Dict[str, Any], queue.Queue[Dict[str, Any]]]]" = (
            queue.Queue()
        )
        self._stop_evt = threading.Event()
        self._sessions: dict[str, _BrowserSession] = {}
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._action_timeout_ms = int(action_timeout_ms)
        self._navigation_timeout_ms = int(navigation_timeout_ms)
        self._max_retries = max(0, int(max_retries))
        self._idle_timeout = float(idle_timeout)
        self._ready: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1)

    def call(self, op: str, **kwargs: Any) -> Dict[str, Any]:
        if self._stop_evt.is_set():
            raise BrowserSessionError("Agent browser manager has been stopped")

        reply: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1)
        self._queue.put((op, kwargs, reply))
        try:
            return reply.get(timeout=self._default_timeout_s)
        except queue.Empty as exc:
            raise BrowserActionError(f"{op} timed out") from exc

    def stop(self) -> None:
        if self._stop_evt.is_set():
            return
        self._stop_evt.set()
        reply: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1)
        self._queue.put(("_stop", {}, reply))
        with suppress(Exception):
            reply.get(timeout=self._default_timeout_s)
        self.join(timeout=self._default_timeout_s)

    def wait_until_ready(self, *, timeout: float) -> None:
        try:
            message = self._ready.get(timeout=timeout)
        except queue.Empty as exc:
            raise BrowserActionError("browser worker failed to start") from exc

        if not message.get("ok"):
            error = message.get("error")
            if isinstance(error, Exception):
                raise error
            raise BrowserActionError(str(error) if error else "browser worker failed to start")

    def run(self) -> None:
        handshake_sent = False
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=self._headless)
            self._playwright = playwright
            self._browser = browser
            self._ready.put({"ok": True})
            handshake_sent = True
            while True:
                try:
                    op, args, reply = self._queue.get(timeout=0.1)
                except queue.Empty:
                    if self._stop_evt.is_set():
                        break
                    continue

                if op == "_stop":
                    if reply is not None:
                        reply.put({"status": "ok", "result": {}})
                    break

                try:
                    result = self._dispatch(op, args)
                except Exception as exc:  # noqa: BLE001 - deliberate broad catch
                    if reply is not None:
                        reply.put(
                            {
                                "status": "error",
                                "error_type": exc.__class__.__name__,
                                "message": str(exc),
                            }
                        )
                else:
                    if reply is not None:
                        reply.put({"status": "ok", "result": result})
        except Exception as exc:  # pragma: no cover - defensive handshake
            self._stop_evt.set()
            if not handshake_sent:
                with suppress(Exception):
                    self._ready.put({"ok": False, "error": exc})
                    handshake_sent = True
            return
        finally:
            if not handshake_sent:
                with suppress(Exception):
                    self._ready.put({
                        "ok": False,
                        "error": RuntimeError("browser worker failed to start"),
                    })
            self._shutdown()

    def _dispatch(self, op: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if self._browser is None:
            raise BrowserSessionError("Browser is unavailable")

        if op == "ping":
            return {"ok": True}

        if op == "start_session":
            return self._start_session()

        self._cleanup_idle_sessions()
        sid = (args.get("sid") or "").strip()
        if not sid:
            raise ValueError("sid is required")

        session = self._sessions.get(sid)
        if session is None:
            raise SessionNotFoundError(f"unknown session: {sid}")

        if op == "navigate":
            return session.navigate(args.get("url", ""))
        if op == "click":
            return session.click(args.get("selector"), args.get("text"))
        if op == "type":
            return session.type(args.get("selector", ""), args.get("text", ""))
        if op == "reload":
            return session.reload()
        if op == "extract":
            return session.extract()
        if op == "close_session":
            self._sessions.pop(sid, None)
            with suppress(Exception):
                session.close()
            return {"closed": True}

        raise BrowserSessionError(f"unsupported operation: {op}")

    def _start_session(self) -> Dict[str, Any]:
        if self._browser is None:
            raise BrowserSessionError("Browser is unavailable")

        self._cleanup_idle_sessions()
        session_id = secrets.token_urlsafe(12)
        context = self._browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        session = _BrowserSession(
            context=context,
            page=page,
            action_timeout_ms=self._action_timeout_ms,
            navigation_timeout_ms=self._navigation_timeout_ms,
            max_retries=self._max_retries,
        )
        self._sessions[session_id] = session
        return {"sid": session_id}

    def _cleanup_idle_sessions(self) -> None:
        if not self._sessions:
            return

        threshold = time.monotonic() - self._idle_timeout
        expired = [
            sid for sid, session in self._sessions.items() if session.last_active < threshold
        ]
        for sid in expired:
            session = self._sessions.pop(sid, None)
            if session is not None:
                with suppress(Exception):
                    session.close()

    def _shutdown(self) -> None:
        for sid, session in list(self._sessions.items()):
            with suppress(Exception):
                session.close()
            self._sessions.pop(sid, None)

        with suppress(Exception):
            if self._browser is not None:
                self._browser.close()
        with suppress(Exception):
            if self._playwright is not None:
                self._playwright.stop()


__all__ = [
    "AgentBrowserManager",
    "BrowserSessionError",
    "SessionNotFoundError",
    "BrowserActionError",
]
