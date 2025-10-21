from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import pytest

from tools.diag import DiagnosticsEngine, Severity


def _write_files(root: Path, files: Sequence[tuple[str, str]]) -> None:
    for relative, content in files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _run_rules(tmp_path: Path, files: Sequence[tuple[str, str]], only: Iterable[str]) -> list[str]:
    _write_files(tmp_path, files)
    engine = DiagnosticsEngine(tmp_path)
    results, _, _ = engine.run(smoke=False, fail_on=Severity.HIGH, only=set(only), write_artifacts=False)
    return [finding.rule_id for finding in results.findings]


def test_browser_shell_iframe_and_history(tmp_path: Path) -> None:
    files = [
        (
            "frontend/src/components/BrowserShell.tsx",
            """
            export function BrowserShell() {
              const iframeRef = React.useRef<HTMLIFrameElement | null>(null);
              function goBack() {
                const view = iframeRef.current;
                if (view?.contentWindow) {
                  view.contentWindow.history.back();
                }
              }
              return <iframe ref={iframeRef} src="https://example.com/app" />;
            }
            """,
        )
    ]
    rule_ids = _run_rules(tmp_path, files, only={"R1", "R2"})
    assert "R1" in rule_ids
    assert "R2" in rule_ids


def test_browser_shell_webview_prevents_r3(tmp_path: Path) -> None:
    files = [
        (
            "frontend/src/components/browser/WebviewHost.tsx",
            """
            export function WebviewHost() {
              return <webview src="https://internal.app" allowpopups={false} />;
            }
            """,
        )
    ]
    rule_ids = _run_rules(tmp_path, files, only={"R3"})
    assert rule_ids == []


def test_electron_preferences_rules(tmp_path: Path) -> None:
    files = [
        (
            "electron/main.js",
            """
            const { app, BrowserWindow } = require('electron');
            function createWindow() {
              const win = new BrowserWindow({
                webPreferences: {
                  nodeIntegration: true,
                  contextIsolation: false,
                  partition: 'temp',
                },
              });
              app.disableHardwareAcceleration();
              return win;
            }
            """,
        )
    ]
    rule_ids = _run_rules(tmp_path, files, only={"R4", "R5", "R6", "R7"})
    for expected in ("R4", "R5", "R6", "R7"):
        assert expected in rule_ids


def test_headers_missing_accept_language(tmp_path: Path) -> None:
    files = [
        (
            "electron/session.js",
            """
            session.webRequest.onBeforeSendHeaders((details, callback) => {
              const headers = details.requestHeaders;
              delete headers['User-Agent'];
              callback({ requestHeaders: headers });
            });
            """,
        )
    ]
    rule_ids = _run_rules(tmp_path, files, only={"R9"})
    assert "R9" in rule_ids


def test_proxy_absolute_fetch(tmp_path: Path) -> None:
    files = [
        (
            "frontend/src/api.ts",
            """
            export async function proxyFetch() {
              return fetch('https://danger.example.com/api');
            }
            """,
        )
    ]
    rule_ids = _run_rules(tmp_path, files, only={"R10"})
    assert "R10" in rule_ids


def test_missing_scripts(tmp_path: Path) -> None:
    files = [
        (
            "package.json",
            """
            { "name": "test", "version": "0.0.0", "scripts": { "dev": "node index.js" } }
            """,
        ),
        (
            "frontend/package.json",
            """
            { "name": "frontend", "version": "0.0.0", "scripts": { "dev": "next dev" } }
            """,
        ),
    ]
    rule_ids = _run_rules(tmp_path, files, only={"R11"})
    assert "R11" in rule_ids
