"""Embedding manager that ensures Ollama models are available on demand."""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import threading
import time
from typing import Callable, Optional

from urllib.parse import urlparse

import requests


ProgressCallback = Optional[Callable[[int, str], None]]


class EmbeddingManager:
    """Co-ordinates Ollama embedding availability with optional auto-install."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        embed_model: str | None = None,
        auto_install: bool | None = None,
        fallbacks: Optional[list[str]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        env_base = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_URL", "")) or "http://127.0.0.1:11434"
        env_model = os.getenv("EMBED_MODEL") or embed_model or "embeddinggemma"
        env_auto = os.getenv("EMBED_AUTO_INSTALL", "true").lower() == "true"
        env_fallbacks = os.getenv("EMBED_FALLBACKS", "nomic-embed-text,gte-small")
        parsed_fallbacks = [item.strip() for item in env_fallbacks.split(",") if item.strip()]

        self.base_url = (base_url or env_base).rstrip("/")
        self.embed_model = env_model
        self.auto_install = env_auto if auto_install is None else bool(auto_install)
        if fallbacks is None:
            self.fallbacks = list(parsed_fallbacks)
        else:
            self.fallbacks = list(fallbacks)

        self.logger = logger or logging.getLogger(__name__)
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._installing = False
        self._active_model = self.embed_model
        self._last_status: dict = {
            "state": "unknown",
            "progress": 0,
            "model": self.embed_model,
            "error": None,
            "detail": None,
            "auto_install": self.auto_install,
            "fallbacks": list(self.fallbacks),
            "ollama": {"base_url": self.base_url, "alive": False},
        }

    # ------------------------------------------------------------------
    # Ollama helpers
    # ------------------------------------------------------------------
    def ollama_alive(self, timeout: float = 1.0) -> bool:
        try:
            result = subprocess.run(
                ["ollama", "ps"],
                check=False,
                capture_output=True,
                text=True,
                timeout=max(timeout, 0.1),
            )
        except subprocess.TimeoutExpired:
            return False
        except (OSError, subprocess.SubprocessError):
            return False

        if result.returncode != 0:
            if result.stderr and "command not found" in result.stderr.lower():
                self.logger.warning("ollama command not found; auto-start disabled")
            return False

        output = (result.stdout or "").strip()
        if not output:
            return True

        lines = [line for line in output.splitlines() if line.strip()]
        if not lines:
            return True

        header_line = lines[0]
        status_pos = header_line.upper().find("STATUS")
        header_tokens = header_line.upper().split()
        token_index = header_tokens.index("STATUS") if "STATUS" in header_tokens else None

        for line in lines[1:]:
            status_text: str = ""
            if token_index is not None:
                parts = line.split()
                if len(parts) > token_index:
                    status_text = " ".join(parts[token_index:])
            if not status_text and status_pos != -1 and len(line) > status_pos:
                status_text = line[status_pos:].strip()
            status_text = status_text.strip()
            if not status_text:
                continue
            lowered = status_text.lower()
            if any(term in lowered for term in ("error", "offline", "fail")):
                return False
            return True

        return True

    def try_start_ollama(self) -> Optional[str]:
        system = platform.system().lower()
        parsed = urlparse(self.base_url)
        serve_cmd = ["ollama", "serve"]
        host = parsed.hostname
        port = parsed.port
        host_arg: Optional[str] = None
        if host and port:
            if host not in {"127.0.0.1", "localhost"} or port != 11434:
                host_arg = f"{host}:{port}"
        elif host:
            if host not in {"127.0.0.1", "localhost"}:
                host_arg = host
        elif port and port != 11434:
            host_arg = f"127.0.0.1:{port}"
        if host_arg:
            serve_cmd.extend(["--host", host_arg])

        errors: list[str] = []
        popen_kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if system == "windows":
            creationflags = 0
            if hasattr(subprocess, "DETACHED_PROCESS"):
                creationflags |= getattr(subprocess, "DETACHED_PROCESS")
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
            if creationflags:
                popen_kwargs["creationflags"] = creationflags
        else:
            popen_kwargs["start_new_session"] = True

        try:
            subprocess.Popen(serve_cmd, **popen_kwargs)
            return None
        except Exception as exc:  # pragma: no cover - depends on environment
            errors.append(f"ollama serve spawn failed: {exc}")

        commands: list[list[str]] = []
        if system == "darwin":
            commands = [["brew", "services", "start", "ollama"]]
        elif system == "linux":
            commands = [["systemctl", "--user", "start", "ollama"], ["systemctl", "start", "ollama"]]
        elif system == "windows":
            commands = [["powershell", "-Command", "Start-Service Ollama"]]
        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd,
                    check=False,
                    timeout=10,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except Exception as exc:  # pragma: no cover - best effort per platform
                errors.append(f"{' '.join(cmd)} invocation failed: {exc}")
                continue
            if result.returncode == 0:
                return None
            message = (result.stderr or result.stdout or "").strip()
            if message:
                errors.append(f"{' '.join(cmd)} exited with code {result.returncode}: {message}")
            else:
                errors.append(f"{' '.join(cmd)} exited with code {result.returncode}")

        if errors:
            return "; ".join(errors)
        return "unable to start Ollama"

    def list_models(self) -> list[str]:
        try:
            result = subprocess.run(
                ["ollama", "list"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except subprocess.TimeoutExpired:
            return []
        except (OSError, subprocess.SubprocessError):
            return []

        if result.returncode != 0:
            if result.stderr and "command not found" in result.stderr.lower():
                self.logger.warning("ollama command not found; auto-install disabled")
            return []

        output = result.stdout or ""
        models: list[str] = []
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line or line.lower().startswith("name"):
                continue
            if line.lower().startswith("no models"):
                continue
            name = line.split()[0]
            if name:
                models.append(name.rstrip("*"))
        return models

    def _collect_available_tags(self) -> dict[str, list[str]]:
        tags: dict[str, list[str]] = {}
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            payload = None
        if isinstance(payload, dict):
            models = payload.get("models")
            if isinstance(models, list):
                for entry in models:
                    if not isinstance(entry, dict):
                        continue
                    name = entry.get("model") or entry.get("name") or entry.get("tag")
                    if not isinstance(name, str):
                        continue
                    tag_name = name.strip()
                    if not tag_name:
                        continue
                    base = tag_name.split(":", 1)[0]
                    bucket = tags.setdefault(base, [])
                    if tag_name not in bucket:
                        bucket.append(tag_name)
        if not tags:
            try:
                model_list = self.list_models()
            except Exception:  # pragma: no cover - defensive
                self.logger.debug("list_models failed during tag collection", exc_info=True)
                model_list = []
            for name in model_list:
                tag_name = (name or "").strip()
                if not tag_name:
                    continue
                base = tag_name.split(":", 1)[0]
                bucket = tags.setdefault(base, [])
                if tag_name not in bucket:
                    bucket.append(tag_name)
        return tags

    def resolve_model_tag(self, name: str) -> tuple[Optional[str], bool]:
        if not name:
            return None, False
        base = name.split(":", 1)[0]
        inventory = self._collect_available_tags()
        matches = inventory.get(base, [])
        if not matches:
            return None, False
        for candidate in matches:
            if candidate == name:
                return candidate, True
        preferred = next((item for item in matches if item == f"{base}:latest"), None)
        if preferred:
            return preferred, True
        preferred = next((item for item in matches if item.startswith(f"{base}:")), None)
        if preferred:
            return preferred, True
        return matches[0], True

    def model_present(self, name: str) -> bool:
        _, present = self.resolve_model_tag(name)
        return present

    # ------------------------------------------------------------------
    # Installation logic
    # ------------------------------------------------------------------
    def pull_model(self, name: str, on_progress: ProgressCallback = None) -> None:
        try:
            with requests.post(
                f"{self.base_url}/api/pull",
                json={"name": name},
                stream=True,
                timeout=600,
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_lines():
                    if not chunk:
                        continue
                    try:
                        payload = json.loads(chunk.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    total = payload.get("total")
                    completed = payload.get("completed")
                    if isinstance(total, int) and total > 0 and isinstance(completed, int):
                        pct = int(min(max(completed * 100 // total, 0), 100))
                    else:
                        pct = int(payload.get("status", 0)) if "status" in payload else 0
                    message = payload.get("status")
                    if on_progress:
                        on_progress(pct, message or "")
            return
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
        else:
            last_error = None
        if last_error is None:
            return
        try:
            process = subprocess.Popen(
                ["ollama", "pull", name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:  # pragma: no cover - subprocess spawn failure
            raise RuntimeError(str(exc)) from exc
        assert process.stdout is not None
        for line in process.stdout:
            if on_progress:
                on_progress(0, line.strip())
        try:
            process.wait(timeout=1800)
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
            process.kill()
            raise RuntimeError("ollama pull timed out") from exc
        if process.returncode and process.returncode != 0:
            raise RuntimeError(f"ollama pull exited with status {process.returncode}")

    # ------------------------------------------------------------------
    # Status utilities
    # ------------------------------------------------------------------
    def _status_snapshot(self) -> dict:
        snapshot = dict(self._last_status)
        snapshot["fallbacks"] = list(self._last_status.get("fallbacks", []))
        snapshot["ollama"] = dict(self._last_status.get("ollama", {}))
        snapshot["auto_install"] = bool(self._last_status.get("auto_install", False))
        return snapshot

    def _status_copy(self) -> dict:
        with self._lock:
            return self._status_snapshot()

    def _update_status(
        self,
        *,
        state: Optional[str] = None,
        progress: Optional[int] = None,
        model: Optional[str] = None,
        error: Optional[str] = None,
        detail: Optional[str] = None,
        alive: Optional[bool] = None,
    ) -> dict:
        with self._lock:
            if state is not None:
                self._last_status["state"] = state
            if progress is not None:
                self._last_status["progress"] = max(0, min(int(progress), 100))
            if model:
                self._last_status["model"] = model
            if error is not None:
                self._last_status["error"] = error
            if detail is not None:
                self._last_status["detail"] = detail or None
            self._last_status["fallbacks"] = list(self.fallbacks)
            self._last_status["auto_install"] = self.auto_install
            ollama_state = dict(self._last_status.get("ollama", {}))
            ollama_state["base_url"] = self.base_url
            if alive is not None:
                ollama_state["alive"] = bool(alive)
            elif "alive" not in ollama_state:
                ollama_state["alive"] = False
            self._last_status["ollama"] = ollama_state
            snapshot = self._status_snapshot()
            self._cond.notify_all()
            return snapshot

    def get_status(self, *, refresh: bool = False) -> dict:
        if refresh:
            self.refresh()
        return self._status_copy()

    def refresh(self) -> dict:
        alive = self.ollama_alive()
        model = self.active_model
        resolved_name, present = self.resolve_model_tag(model) if alive else (None, False)
        active_name = resolved_name or model
        if alive and present:
            with self._lock:
                self._active_model = active_name
            return self._update_status(state="ready", progress=100, model=active_name, error=None, alive=True)
        if self._installing:
            return self._status_copy()
        if not alive:
            return self._update_status(state="error", progress=0, model=active_name, error="ollama_offline", alive=False)
        if not self.auto_install:
            return self._update_status(state="absent", progress=0, model=active_name, error="auto_install_disabled", alive=True)
        return self._update_status(state="missing", progress=0, model=active_name, error=None, alive=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def active_model(self) -> str:
        with self._lock:
            return self._active_model or self.embed_model

    def ensure(self, preferred_model: str | None = None) -> dict:
        target = preferred_model or self.embed_model
        alive = self.ollama_alive()
        start_detail: Optional[str] = None
        if not alive:
            start_detail = self.try_start_ollama()
            time.sleep(1.5)
            alive = self.ollama_alive()
            if not alive:
                detail_message = "Ollama service is not reachable."
                if start_detail:
                    detail_message = f"{detail_message} ({start_detail})"
                return self._update_status(
                    state="error",
                    progress=0,
                    model=target,
                    error="ollama_offline",
                    detail=detail_message,
                    alive=False,
                )
        resolved_name, present = self.resolve_model_tag(target)
        active_name = resolved_name or target
        if present:
            with self._lock:
                self._active_model = active_name
            return self._update_status(state="ready", progress=100, model=active_name, error=None, alive=True)

        if not self.auto_install:
            detail_message = "Automatic installation disabled via configuration."
            if preferred_model is not None and preferred_model != target:
                detail_message = (
                    f"{detail_message} Fallback '{preferred_model}' is not available."
                )
            status = self._update_status(
                state="absent",
                progress=0,
                model=active_name,
                error="auto_install_disabled",
                detail=detail_message,
                alive=True,
            )
            if preferred_model is not None:
                return status
            for fallback in self.fallbacks:
                if not fallback or fallback == target:
                    continue
                status = self.ensure(preferred_model=fallback)
                if status.get("state") == "ready":
                    return status
            return status

        with self._lock:
            if self._installing:
                return self._status_copy()
            self._installing = True
            self._active_model = active_name
        self._update_status(state="installing", progress=0, model=active_name, error=None, detail=None, alive=True)

        def _progress(pct: int, message: str) -> None:
            self._update_status(state="installing", progress=pct, model=self.active_model, error=None, detail=message, alive=True)

        last_error: Optional[str] = None
        try:
            self.pull_model(target, on_progress=_progress)
            deadline = time.time() + 1200
            while time.time() < deadline:
                resolved_name, present = self.resolve_model_tag(target)
                if present:
                    final_name = resolved_name or target
                    with self._lock:
                        self._active_model = final_name
                    return self._update_status(
                        state="ready",
                        progress=100,
                        model=final_name,
                        error=None,
                        detail=None,
                        alive=True,
                    )
                time.sleep(1)
            raise RuntimeError("model_not_listed_after_pull")
        except Exception as exc:  # pragma: no cover - network/ollama failures dominate
            last_error = str(exc)
        finally:
            with self._lock:
                self._installing = False
                self._cond.notify_all()

        if last_error:
            self._update_status(
                state="error",
                progress=0,
                model=active_name,
                error=last_error,
                detail=last_error,
                alive=True,
            )

        if preferred_model is not None:
            return self._status_copy()

        for fallback in self.fallbacks:
            if not fallback or fallback == target:
                continue
            status = self.ensure(preferred_model=fallback)
            if status.get("state") == "ready":
                return status

        return self._status_copy()

    def wait_until_ready(self, timeout: float = 900.0) -> dict:
        status = self.ensure()
        if status.get("state") != "installing":
            return status
        deadline = time.time() + timeout
        with self._lock:
            while self._last_status.get("state") == "installing":
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._cond.wait(timeout=min(1.0, remaining))
            return self._status_copy()

    def embed(self, texts: list[str], *, model: str | None = None) -> list[float]:
        model_name = model or self.active_model
        response = requests.post(
            f"{self.base_url}/api/embeddings",
            json={"model": model_name, "prompt": "\n".join(texts)},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        embedding = payload.get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError("Invalid embedding payload returned by Ollama")
        return embedding


__all__ = ["EmbeddingManager"]
