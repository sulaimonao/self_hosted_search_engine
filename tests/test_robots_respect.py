from urllib.robotparser import RobotFileParser

from config import load_config


def test_robots_respect_disallow():
    cfg = load_config()
    user_agent = cfg["crawler"]["user_agent"]
    rp = RobotFileParser()
    rp.parse(
        [
            "User-agent: *",
            "Disallow: /private",
            "Allow: /",
        ]
    )
    assert not rp.can_fetch(user_agent, "https://example.com/private/page")
    assert rp.can_fetch(user_agent, "https://example.com/public")
