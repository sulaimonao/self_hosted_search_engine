import pytest

from backend.app.services.agent_browser import AgentBrowserManager


def test_agent_browser_extracts_example_domain():
    try:
        manager = AgentBrowserManager(idle_timeout=2.0)
    except Exception as exc:  # pragma: no cover - skip when Playwright not installed
        pytest.skip(f"Playwright unavailable: {exc}")
    try:
        sid = manager.start_session()
        manager.navigate(sid, "https://example.com")
        payload = manager.extract(sid)
    finally:
        manager.close()
    assert "Example Domain" in payload.get("text", "")
    assert payload.get("url", "").startswith("https://")
