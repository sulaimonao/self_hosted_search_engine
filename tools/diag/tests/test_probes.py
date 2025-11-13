from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from tools.diag import DiagnosticsEngine, Severity


def _write_files(root: Path, files: Sequence[tuple[str, str]]) -> None:
    for relative, content in files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _run_probes(
    tmp_path: Path, files: Sequence[tuple[str, str]], only: Iterable[str]
) -> list[str]:
    _write_files(tmp_path, files)
    engine = DiagnosticsEngine(tmp_path)
    results, _, _ = engine.run(
        smoke=False, fail_on=Severity.HIGH, only=set(only), write_artifacts=False
    )
    return [finding.rule_id for finding in results.findings]


def test_probe_electron_webprefs_requires_hardening(tmp_path: Path) -> None:
    files = [
        (
            "desktop/electron/src/main.ts",
            """
            import { BrowserWindow, BrowserView } from "electron";
            function createWindow() {
              const win = new BrowserWindow({
                webPreferences: {
                  nodeIntegration: true,
                },
              });
              const view = new BrowserView({});
              return win;
            }
            export default createWindow;
            """,
        )
    ]
    rule_ids = _run_probes(tmp_path, files, only={"probe_electron_webprefs"})
    assert "probe_electron_webprefs" in rule_ids


def test_probe_sse_stream_integrity_requires_parser(tmp_path: Path) -> None:
    files = [
        (
            "frontend/src/hooks/useLlmStream.ts",
            """
            export function useLlmStream() {
              let state = { text: "" };
              const listeners = [] as (() => void)[];
              return {
                state,
                start: async () => undefined,
                abort: () => undefined,
                supported: true,
              };
            }
            """,
        )
    ]
    rule_ids = _run_probes(tmp_path, files, only={"probe_sse_stream_integrity"})
    assert "probe_sse_stream_integrity" in rule_ids


def test_probe_headers_pass_detects_missing_spread(tmp_path: Path) -> None:
    files = [
        (
            "desktop/main.ts",
            """
            import { session } from "electron";
            const mainSession = session.defaultSession;
            mainSession.webRequest.onBeforeSendHeaders((details, callback) => {
              const headers: Record<string, string> = {};
              headers["User-Agent"] = "Custom";
              callback({ requestHeaders: headers });
            });
            """,
        )
    ]
    rule_ids = _run_probes(tmp_path, files, only={"probe_headers_pass"})
    assert "probe_headers_pass" in rule_ids
