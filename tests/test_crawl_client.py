import threading
import time

from engine.indexing.crawl import CrawlClient


class _BlockingSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.started = threading.Event()
        self.allow_finish = threading.Event()
        self.concurrent_attempts = 0
        self.calls = 0

    def get(self, url: str, timeout: tuple[float, float], allow_redirects: bool):
        if not self.started.is_set():
            self.started.set()
        elif not self.allow_finish.is_set():
            self.concurrent_attempts += 1
        self.calls += 1
        if not self.allow_finish.wait(timeout=1):
            raise RuntimeError("timed out waiting for release")
        return _FakeResponse(url)

    def close(self) -> None:  # pragma: no cover - exercised indirectly
        pass


class _ImmediateSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.calls = 0
        self.closed = False

    def get(self, url: str, timeout: tuple[float, float], allow_redirects: bool):
        self.calls += 1
        return _FakeResponse(url)

    def close(self) -> None:
        self.closed = True


class _FakeResponse:
    def __init__(self, url: str) -> None:
        self.status_code = 200
        self.url = url
        self.text = "<html><title>ok</title><body>hello world</body></html>"
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:  # pragma: no cover - compatibility shim
        return None


def test_fetch_serializes_session_usage_under_concurrency():
    session = _BlockingSession()
    client = CrawlClient(
        "SelfHostedSearch/pytest",
        min_delay=0.0,
        session=session,
        enable_browser_fallback=False,
    )

    results: list = []

    def run_fetch(target_url: str) -> None:
        results.append(client.fetch(target_url))

    first = threading.Thread(target=run_fetch, args=("https://example.com/one",))
    first.start()
    assert session.started.wait(1.0)

    second = threading.Thread(target=run_fetch, args=("https://example.com/two",))
    second.start()

    time.sleep(0.05)
    assert session.concurrent_attempts == 0

    session.allow_finish.set()

    first.join(timeout=1.0)
    second.join(timeout=1.0)

    assert session.concurrent_attempts == 0
    assert session.calls == 2
    assert all(result is not None for result in results)

    client.close()


def test_fetch_reinitializes_session_after_close():
    initial_session = _ImmediateSession()
    client = CrawlClient(
        "SelfHostedSearch/pytest",
        min_delay=0.0,
        session=initial_session,
        enable_browser_fallback=False,
    )

    client.close()
    assert initial_session.closed is True

    replacement_session = _ImmediateSession()
    client._build_session = lambda: replacement_session  # type: ignore[assignment]

    result = client.fetch("https://example.com/again")

    assert replacement_session.calls == 1
    assert result is not None

    client.close()
