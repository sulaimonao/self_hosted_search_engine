from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import pytest

from tools.diag import DiagnosticsEngine, Finding, Severity


def _write_files(root: Path, files: Sequence[tuple[str, str]]) -> None:
    for relative, content in files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _run_rules(tmp_path: Path, files: Sequence[tuple[str, str]], only: Iterable[str]) -> list[Finding]:
    _write_files(tmp_path, files)
    engine = DiagnosticsEngine(tmp_path)
    results, _, _ = engine.run(smoke=False, fail_on=Severity.HIGH, only=set(only), write_artifacts=False)
    return list(results.findings)


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
                  view?.contentWindow?.history.back();
                }
              }
              function goForward() {
                window.history.forward();
              }
              return <iframe ref={iframeRef} src="https://example.com/app" />;
            }
            """,
        )
    ]
    findings = _run_rules(tmp_path, files, only={"R1", "R2", "R23_cross_origin_iframe_history"})
    rule_ids = {finding.rule_id for finding in findings}
    assert "R1" in rule_ids
    assert "R2" in rule_ids
    assert "R23_cross_origin_iframe_history" in rule_ids


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
    findings = _run_rules(tmp_path, files, only={"R3"})
    assert findings == []


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
    findings = _run_rules(tmp_path, files, only={"R4", "R5", "R6", "R7"})
    rule_ids = {finding.rule_id for finding in findings}
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
    findings = _run_rules(tmp_path, files, only={"R9"})
    rule_ids = {finding.rule_id for finding in findings}
    assert "R9" in rule_ids


def test_robot_captcha_risk(tmp_path: Path) -> None:
    files = [
        (
            "desktop/main.ts",
            """
            const DESKTOP_USER_AGENT = 'HeadlessChrome/120.0';
            export function bootstrap() {
              console.log('boot');
            }
            """,
        )
    ]
    findings = _run_rules(tmp_path, files, only={"R26_robot_captcha_risk"})
    assert findings
    assert any(f.rule_id == "R26_robot_captcha_risk" for f in findings)


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
    findings = _run_rules(tmp_path, files, only={"R10"})
    rule_ids = {finding.rule_id for finding in findings}
    assert "R10" in rule_ids


def test_proxy_cors_mismatch(tmp_path: Path) -> None:
    files = [
        (
            "frontend/next.config.mjs",
            """
            const DEFAULT_API_BASE_URL = 'http://127.0.0.1:4000';
            export default {
              async rewrites() {
                return [{ source: '/api/:path*', destination: 'http://127.0.0.1:4000/api/:path*' }];
              }
            };
            """,
        ),
        (
            "backend/app/__init__.py",
            """
            from flask import Flask
            from flask_cors import CORS

            app = Flask(__name__)
            CORS(app, resources={r'/*': {'origins': ['http://localhost:3100']}})
            """,
        ),
        (".env.example", "BACKEND_PORT=5050\n"),
    ]
    findings = _run_rules(tmp_path, files, only={"R25_proxy_cors_mismatch"})
    assert findings
    assert any(f.rule_id == "R25_proxy_cors_mismatch" for f in findings)


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
    findings = _run_rules(tmp_path, files, only={"R11"})
    rule_ids = {finding.rule_id for finding in findings}
    assert "R11" in rule_ids


def test_llm_stream_integrity(tmp_path: Path) -> None:
    files = [
        ("desktop/main.ts", "export const noop = true;"),
        ("desktop/preload.ts", "export const noop = true;"),
        ("frontend/src/hooks/useLlmStream.ts", "export function useLlmStream() { return null as any; }")
    ]
    findings = _run_rules(tmp_path, files, only={"R20_stream_integrity"})
    rule_ids = {finding.rule_id for finding in findings}
    assert "R20_stream_integrity" in rule_ids


def test_stream_render_required(tmp_path: Path) -> None:
    files = [
        (
            "frontend/src/hooks/useLlmStream.ts",
            """
            export function useLlmStream() {
              return {
                state: { requestId: null, frames: 0, text: '', done: false, metadata: null, final: null, error: null },
                start: async () => {},
                abort: () => {},
                supported: true,
              };
            }
            """,
        )
    ]
    findings = _run_rules(tmp_path, files, only={"R24_stream_render_required"})
    assert findings
    assert findings[0].rule_id == "R24_stream_render_required"


def test_llm_stream_accumulator_detection(tmp_path: Path) -> None:
    files = [
        (
            "backend/app/api/chat.py",
            """
class _StreamAccumulator:
    def __init__(self) -> None:
        self.answer = ""

    def update(self, chunk):
        content = chunk.get("message", {}).get("content", "").strip()
        if content and content != self.answer:
            self.answer = content
            return {"delta": content}
        return None
            """,
        ),
    ]
    findings = _run_rules(tmp_path, files, only={"R20_stream_integrity"})
    rule_ids = {finding.rule_id for finding in findings}
    assert "R20_stream_integrity" in rule_ids


def test_env_keys_missing_from_example(tmp_path: Path) -> None:
    files = [
        (
            "backend/core/config.py",
            """
import os

API_TOKEN = os.getenv("API_TOKEN")
            """,
        ),
        (".env.example", "# Sample env file\nEXISTING=1\n"),
    ]
    findings = _run_rules(tmp_path, files, only={"R14"})
    assert findings
    assert findings[0].rule_id == "R14"
    assert "API_TOKEN" in findings[0].summary


def test_env_keys_documented(tmp_path: Path) -> None:
    files = [
        (
            "backend/core/config.py",
            """
import os

API_TOKEN = os.environ["API_TOKEN"]
            """,
        ),
        (".env.example", "API_TOKEN=changeme\n"),
    ]
    findings = _run_rules(tmp_path, files, only={"R14"})
    assert findings == []


def test_pyproject_vs_requirements_drift(tmp_path: Path) -> None:
    files = [
        (
            "pyproject.toml",
            """
[project]
dependencies = ["fastapi>=0.100", "uvicorn[standard]"]
            """,
        ),
        (
            "requirements.txt",
            """
fastapi==0.101
requests>=2.31
            """,
        ),
    ]
    findings = _run_rules(tmp_path, files, only={"R21_dependency_sync"})
    summaries = {finding.summary for finding in findings}
    assert any("requests" in summary for summary in summaries)
    assert any("uvicorn" in summary for summary in summaries)
    severities = {finding.severity for finding in findings}
    assert Severity.MEDIUM in severities
    assert Severity.LOW in severities


def test_pyproject_vs_requirements_aligned(tmp_path: Path) -> None:
    files = [
        (
            "pyproject.toml",
            """
[project]
dependencies = ["fastapi>=0.100", "uvicorn[standard]"]
            """,
        ),
        (
            "requirements.txt",
            """
fastapi==0.101
uvicorn[standard]==0.22
            """,
        ),
    ]
    findings = _run_rules(tmp_path, files, only={"R21_dependency_sync"})
    assert findings == []
