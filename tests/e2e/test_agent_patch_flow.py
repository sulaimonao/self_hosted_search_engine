from __future__ import annotations

import subprocess
from server.agent_policy import (
    Autonomy,
    apply_and_verify,
    finalize_pr,
    run_maintainer_task,
)


class DummyProcess:
    def __init__(self) -> None:
        self.returncode = 0
        self.stdout = "ok"
        self.stderr = ""


def test_agent_patch_flow(monkeypatch) -> None:
    calls: dict[str, list[list[str]]] = {"check_call": [], "run": []}

    def fake_run(
        cmd, text=True, capture_output=True, check=False
    ):  # noqa: D401 - match subprocess signature
        calls["run"].append(list(cmd))
        return DummyProcess()

    def fake_check_call(cmd):
        calls["check_call"].append(list(cmd))
        return 0

    def fake_check_output(cmd, text=True):
        if list(cmd) == ["git", "diff", "--cached"]:
            return "diff --git a/server/__init__.py b/server/__init__.py\n"
        return ""

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    # Ensure agent tools module uses the patched subprocess functions.
    monkeypatch.setattr("server.agent_tools_repo.subprocess", subprocess)

    state = run_maintainer_task("Chore: trivial lint", autonomy=Autonomy.PATCH)
    assert state["status"] == "planned"
    assert state["branch"].startswith("bot/")

    diff = (
        "diff --git a/server/__init__.py b/server/__init__.py\n"
        "--- a/server/__init__.py\n"
        "+++ b/server/__init__.py\n"
        "@@ -1 +1 @@\n"
        "-DEBUG = True\n"
        "+DEBUG = True  # noqa: F401\n"
    )

    result = apply_and_verify(diff, autonomy=Autonomy.PATCH)
    assert result["ok"]
    assert result["lint"]["ok"]
    assert result["tests"]["ok"]
    assert result["security"]["ok"]
    assert result["perf"]["ok"]
    assert "diff" in result

    pr_payload = finalize_pr("Chore: trivial lint", "Silence unused var warning.")
    assert pr_payload["ok"]
    assert pr_payload["title"] == "Chore: trivial lint"

    assert any("git" in cmd for cmd in calls["check_call"])
