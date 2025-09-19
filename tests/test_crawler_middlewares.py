import types

from crawler.middlewares import AdaptiveDelayMiddleware


class DummySlot:
    def __init__(self, delay, key="slot"):
        self.delay = delay
        self.key = key


class DummyDownloader:
    def __init__(self):
        self.slots = {}


class DummyCrawler:
    def __init__(self):
        self.engine = types.SimpleNamespace(downloader=DummyDownloader())


def make_request(slot_key: str):
    return types.SimpleNamespace(meta={"download_slot": slot_key})


def test_adaptive_delay_increases_on_429(monkeypatch):
    crawler = DummyCrawler()
    slot = DummySlot(delay=0.25)
    crawler.engine.downloader.slots["example"] = slot
    middleware = AdaptiveDelayMiddleware(crawler)

    request = make_request("example")
    response = types.SimpleNamespace(status=429)
    middleware.process_response(request, response, spider=None)
    assert slot.delay > 0.25

    # Recovery on success should decay towards base delay
    response_ok = types.SimpleNamespace(status=200)
    previous = slot.delay
    middleware.process_response(request, response_ok, spider=None)
    assert slot.delay <= previous
