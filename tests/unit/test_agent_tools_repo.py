from __future__ import annotations

from server.agent_tools_repo import Policy


def _policy() -> Policy:
    return Policy(
        write_paths=("backend/", "policy/allowlist.yml", "server/**"),
        deny_paths=(".env", "data/"),
        max_changed_files=5,
        max_changed_loc=100,
    )


def test_policy_allows_configured_prefixes() -> None:
    policy = _policy()
    assert policy.is_path_allowed("backend/module.py")
    assert policy.is_path_allowed("policy/allowlist.yml")
    assert policy.is_path_allowed("server/agent_tools_repo.py")


def test_policy_rejects_similar_prefixes() -> None:
    policy = _policy()
    assert not policy.is_path_allowed("backendx/module.py")
    assert not policy.is_path_allowed("backend-tools/__init__.py")


def test_policy_rejects_traversal_and_absolute_paths() -> None:
    policy = _policy()
    assert not policy.is_path_allowed("../backend/module.py")
    assert not policy.is_path_allowed("backend/../secrets.py")
    assert not policy.is_path_allowed("/etc/passwd")


def test_policy_normalizes_platform_specific_separators() -> None:
    policy = _policy()
    assert policy.is_path_allowed(r"backend\subdir\file.py")
    assert not policy.is_path_allowed(r"..\backend\file.py")


def test_policy_denies_configured_prefixes() -> None:
    policy = _policy()
    assert not policy.is_path_allowed("data/leak.json")
    assert not policy.is_path_allowed(".env")
