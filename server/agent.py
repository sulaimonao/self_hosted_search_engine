"""Planner agent orchestrating tool calls via LangGraph state machine."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from logging import Logger
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph

from langsmith import Client

from .llm import LLMError, OllamaJSONClient
from .logging_utils import get_logger
from .runlog import add_run_log_line
from .tools import ToolDispatcher

LOGGER = get_logger("agent")

SYSTEM_PROMPT = (
    "You are the autonomous planner for a self-hosted search stack. "
    "Always respond with a single JSON object. "
    "When you need information use {\"type\": \"tool\", \"tool\": <name>, \"params\": {...}}. "
    "When you are ready to answer return {\"type\": \"final\", \"answer\": <summary>, \"sources\": []}. "
    "Do not include commentary outside the JSON object."
)

FEW_SHOT_MESSAGES: Sequence[Mapping[str, str]] = (
    {
        "role": "user",
        "content": json.dumps(
            {
                "type": "query",
                "query": "Find recent docs about crawling ethics",
            }
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "type": "tool",
                "tool": "index.search",
                "params": {"query": "crawling ethics", "k": 3},
            }
        ),
    },
    {
        "role": "tool",
        "name": "index.search",
        "content": json.dumps(
            {
                "ok": True,
                "tool": "index.search",
                "result": {"results": []},
            }
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "type": "final",
                "answer": "No indexed documents found. Recommend triggering a crawl.",
                "sources": [],
            }
        ),
    },
)

CRITIQUE_PROMPT = (
    "You critique answers for the research planner. "
    "Respond with JSON containing should_retry (bool) and feedback (string). "
    "Request a retry when the answer is empty, contradicts the query, or lacks sources when evidence was requested."
)


@dataclass
class PlannerAgent:
    llm: OllamaJSONClient
    tools: ToolDispatcher
    default_model: str | None = None
    fallback_model: str | None = None
    max_iterations: int = 6
    node_timeout: float = 45.0
    llm_max_attempts: int = 3
    llm_initial_backoff: float = 1.0
    logger: Logger = field(default=LOGGER)
    langsmith_project: str | None = None

    def __post_init__(self) -> None:
        self.langsmith_project = (
            self.langsmith_project
            or os.getenv("LANGSMITH_PROJECT")
            or os.getenv("LANGCHAIN_PROJECT")
            or "self-hosted-search"
        )
        try:
            self._langsmith_client: Client | None = Client()
        except Exception:  # pragma: no cover - optional instrumentation
            self._langsmith_client = None
            self.logger.debug("planner.langsmith disabled", exc_info=True)
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(
        self,
        query: str,
        *,
        context: Mapping[str, Any] | None = None,
        model: str | None = None,
    ) -> Mapping[str, Any]:
        self.logger.info("planner starting query=%s", query)
        add_run_log_line(f"planner start: {query[:80]}")
        initial_state: dict[str, Any] = {
            "query": query,
            "context": dict(context or {}),
            "messages": list(self._bootstrap_messages(query, context)),
            "steps": [],
            "loop_count": 0,
            "graph_events": [],
            "model_override": model,
            "start_time": time.perf_counter(),
        }
        run_id = self._start_langsmith_run(query, initial_state["context"])
        try:
            final_state: MutableMapping[str, Any] = self._graph.invoke(
                initial_state,
                config={
                    "recursion_limit": max(self.max_iterations * 2, 8),
                    "metadata": {
                        "query": query,
                        "max_iterations": self.max_iterations,
                    },
                },
            )
        except GraphRecursionError as exc:
            self.logger.warning("planner graph recursion limit reached; using fallback", exc_info=True)
            fallback = self._fallback_run(query, context or {}, model)
            if run_id:
                self._finish_langsmith_run(run_id, outputs=fallback)
                fallback["langsmith_run_id"] = str(run_id)
            add_run_log_line("planner fallback")
            return fallback
        except Exception as exc:
            if run_id:
                self._finish_langsmith_run(run_id, error=str(exc))
            self.logger.exception("planner graph failed")
            add_run_log_line("planner error")
            raise
        final_payload = self._finalize_payload(final_state)
        if run_id:
            self._finish_langsmith_run(run_id, outputs=final_payload)
            final_payload["langsmith_run_id"] = str(run_id)
        add_run_log_line("planner finished")
        self.logger.info("planner completed query=%s", query)
        return final_payload

    def _fallback_run(
        self,
        query: str,
        context: Mapping[str, Any],
        model: str | None,
    ) -> Mapping[str, Any]:
        messages = list(self._bootstrap_messages(query, context))
        steps: list[dict[str, Any]] = []
        current_model = model or getattr(self.llm, "default_model", None)
        for iteration in range(1, self.max_iterations + 1):
            response = self.llm.chat_json(messages, model=current_model)
            if not isinstance(response, Mapping):
                raise LLMError("Planner fallback received non-JSON response")
            payload = dict(response)
            steps.append({"iteration": iteration, "response": payload, "model": current_model})
            messages.append({"role": "assistant", "content": json.dumps(payload)})
            message_type = payload.get("type")
            if message_type == "tool":
                tool_name = str(payload.get("tool") or "")
                params = payload.get("params") if isinstance(payload.get("params"), Mapping) else {}
                try:
                    result = self.tools.execute(tool_name, params)
                except Exception as exc:  # pragma: no cover - defensive
                    raise LLMError(f"Tool execution failed: {exc}") from exc
                messages.append(
                    {
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(result),
                    }
                )
                continue
            if message_type == "final":
                return self._normalize_final(payload, steps, current_model)
        return {
            "type": "final",
            "answer": "",
            "sources": [],
            "error": "iteration limit reached",
            "steps": steps,
        }

    # ------------------------------------------------------------------
    # Graph wiring
    # ------------------------------------------------------------------
    def _build_graph(self) -> Any:
        graph: StateGraph = StateGraph(dict)
        graph.add_node("plan", self._node_plan)
        graph.add_node("tool_select", self._node_tool_select)
        graph.add_node("tool_run", self._node_tool_run)
        graph.add_node("retrieve_context", self._node_retrieve_context)
        graph.add_node("respond", self._node_respond)
        graph.add_node("critique", self._node_critique)
        graph.add_node("decide_retry", self._node_decide_retry)

        graph.set_entry_point("plan")
        graph.add_conditional_edges(
            "plan",
            self._route_plan,
            {
                "tool": "tool_select",
                "respond": "respond",
                "retry": "decide_retry",
            },
        )
        graph.add_edge("tool_select", "tool_run")
        graph.add_edge("tool_run", "retrieve_context")
        graph.add_edge("retrieve_context", "decide_retry")
        graph.add_edge("respond", "critique")
        graph.add_edge("critique", "decide_retry")
        graph.add_conditional_edges(
            "decide_retry",
            self._route_decision,
            {
                "continue": "plan",
                "stop": END,
            },
        )
        return graph.compile()

    # ------------------------------------------------------------------
    # Node helpers
    # ------------------------------------------------------------------
    def _node_plan(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        iteration = state.get("loop_count", 0) + 1
        state["loop_count"] = iteration
        start_time = time.perf_counter()
        try:
            response, model_used = self._call_llm_json(
                state.get("messages", []),
                state.get("model_override") or self.default_model,
            )
            if not isinstance(response, Mapping):
                raise LLMError("Planner LLM returned non-JSON payload")
            payload = dict(response)
            state["last_model_used"] = model_used
            state["current_action"] = payload
            step = {"iteration": iteration, "response": payload, "model": model_used}
            state.setdefault("steps", []).append(step)
            state.setdefault("messages", []).append(
                {"role": "assistant", "content": json.dumps(payload)}
            )
            duration = time.perf_counter() - start_time
            self._record_event(
                state,
                node="plan",
                status="success",
                duration=duration,
                model=model_used,
            )
        except Exception as exc:  # pragma: no cover - defensive branch
            duration = time.perf_counter() - start_time
            state["current_action"] = None
            state.setdefault("errors", []).append(str(exc))
            state["pending_error"] = {"node": "plan", "error": str(exc)}
            self._record_event(
                state,
                node="plan",
                status="error",
                duration=duration,
                error=str(exc),
            )
        return state

    def _route_plan(self, state: Mapping[str, Any]) -> str:
        action = state.get("current_action")
        if not isinstance(action, Mapping):
            return "retry"
        message_type = action.get("type")
        if message_type == "tool":
            return "tool"
        if message_type == "final":
            return "respond"
        return "retry"

    def _node_tool_select(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        action = state.get("current_action")
        start_time = time.perf_counter()
        tool_name = action.get("tool") if isinstance(action, Mapping) else None
        params = action.get("params") if isinstance(action, Mapping) else None
        if not isinstance(tool_name, str) or not tool_name:
            state["pending_error"] = {"node": "tool_select", "error": "missing tool name"}
            duration = time.perf_counter() - start_time
            self._record_event(
                state,
                node="tool_select",
                status="error",
                duration=duration,
                error="missing tool name",
            )
            return state
        if not self.tools.has_tool(tool_name):
            state["pending_error"] = {
                "node": "tool_select",
                "error": f"unknown tool: {tool_name}",
            }
            duration = time.perf_counter() - start_time
            self._record_event(
                state,
                node="tool_select",
                status="error",
                duration=duration,
                error=f"unknown tool: {tool_name}",
            )
            return state
        state["selected_tool"] = tool_name
        state["tool_params"] = dict(params) if isinstance(params, Mapping) else {}
        duration = time.perf_counter() - start_time
        self._record_event(
            state,
            node="tool_select",
            status="success",
            duration=duration,
            tool=tool_name,
        )
        return state

    def _node_tool_run(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        tool = state.get("selected_tool")
        params = state.get("tool_params") or {}
        start_time = time.perf_counter()
        if not isinstance(tool, str):
            state["pending_error"] = {"node": "tool_run", "error": "no tool selected"}
            duration = time.perf_counter() - start_time
            self._record_event(
                state,
                node="tool_run",
                status="error",
                duration=duration,
                error="no tool selected",
            )
            return state

        def _call() -> Mapping[str, Any]:
            return self.tools.execute(tool, params if isinstance(params, Mapping) else {})

        try:
            result = self._run_with_timeout(_call, self.node_timeout, f"tool {tool}")
        except Exception as exc:  # pragma: no cover - network/tool failures
            duration = time.perf_counter() - start_time
            state["tool_result"] = {"ok": False, "tool": tool, "error": str(exc)}
            state["pending_error"] = {"node": "tool_run", "error": str(exc)}
            self._record_event(
                state,
                node="tool_run",
                status="error",
                duration=duration,
                error=str(exc),
                tool=tool,
            )
            return state
        duration = time.perf_counter() - start_time
        state["tool_result"] = result
        steps = state.setdefault("steps", [])
        if steps:
            steps[-1]["tool"] = result
        self._record_event(
            state,
            node="tool_run",
            status="success",
            duration=duration,
            tool=tool,
            ok=bool(result.get("ok")),
        )
        return state

    def _node_retrieve_context(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        start_time = time.perf_counter()
        tool = state.get("selected_tool")
        result = state.get("tool_result")
        if isinstance(result, Mapping):
            state.setdefault("messages", []).append(
                {
                    "role": "tool",
                    "name": str(tool or "unknown"),
                    "content": json.dumps(result),
                }
            )
            if not result.get("ok"):
                state["pending_error"] = {
                    "node": "tool_run",
                    "error": str(result.get("error", "tool failed")),
                }
        duration = time.perf_counter() - start_time
        self._record_event(
            state,
            node="retrieve_context",
            status="success",
            duration=duration,
            tool=str(tool) if tool else None,
        )
        state.pop("selected_tool", None)
        state.pop("tool_params", None)
        return state

    def _node_respond(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        start_time = time.perf_counter()
        action = state.get("current_action")
        payload = dict(action) if isinstance(action, Mapping) else None
        if payload is None:
            state["pending_error"] = {"node": "respond", "error": "missing final payload"}
            duration = time.perf_counter() - start_time
            self._record_event(
                state,
                node="respond",
                status="error",
                duration=duration,
                error="missing final payload",
            )
            return state
        final = self._normalize_final(payload, state.get("steps", []), state.get("last_model_used"))
        state["final_candidate"] = final
        duration = time.perf_counter() - start_time
        self._record_event(
            state,
            node="respond",
            status="success",
            duration=duration,
        )
        return state

    def _node_critique(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        start_time = time.perf_counter()
        final = state.get("final_candidate")
        if not isinstance(final, Mapping):
            state["critique"] = {"should_retry": True, "feedback": "no final candidate"}
            duration = time.perf_counter() - start_time
            self._record_event(
                state,
                node="critique",
                status="error",
                duration=duration,
                error="no final candidate",
            )
            return state
        state["critique"] = {
            "should_retry": False,
            "feedback": "",
            "model": state.get("last_model_used"),
        }
        duration = time.perf_counter() - start_time
        self._record_event(
            state,
            node="critique",
            status="success",
            duration=duration,
            model=state.get("last_model_used"),
            should_retry=False,
        )
        return state

    def _node_decide_retry(self, state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        pending_error = state.pop("pending_error", None)
        critique = state.get("critique") if isinstance(state.get("critique"), Mapping) else {}
        loop_count = state.get("loop_count", 0)
        decision: dict[str, Any] = {"action": "continue", "reason": ""}
        if loop_count >= self.max_iterations:
            decision = {"action": "stop", "reason": "max_loops"}
            state["final"] = {
                "type": "final",
                "answer": "",
                "sources": [],
                "error": "iteration limit reached",
                "steps": state.get("steps", []),
            }
        elif pending_error:
            decision["reason"] = pending_error.get("error")
        elif critique and critique.get("should_retry"):
            decision["reason"] = critique.get("feedback") or "critique retry"
        elif state.get("final_candidate"):
            decision = {"action": "stop", "reason": "finalized"}
            final = dict(state.get("final_candidate") or {})
            final.setdefault("steps", state.get("steps", []))
            if state.get("last_model_used"):
                final.setdefault("planner_model_used", state["last_model_used"])
            state["final"] = final
        state["decision"] = decision
        if (
            decision.get("action") == "continue"
            and isinstance(state.get("current_action"), Mapping)
            and str(state["current_action"].get("type")) == "final"
        ):
            decision = {"action": "stop", "reason": "finalized"}
            state["final"] = self._normalize_final(
                state["current_action"],
                state.get("steps", []),
                state.get("last_model_used"),
            )
            state["decision"] = decision
        if decision["action"] == "continue":
            state.pop("final_candidate", None)
            state.pop("tool_result", None)
            state.pop("current_action", None)
        duration = 0.0
        self._record_event(
            state,
            node="decide_retry",
            status="success",
            duration=duration,
            action=decision.get("action"),
            reason=decision.get("reason"),
        )
        return state

    def _route_decision(self, state: Mapping[str, Any]) -> str:
        decision = state.get("decision")
        if isinstance(decision, Mapping) and decision.get("action") == "stop":
            return "stop"
        return "continue"

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _bootstrap_messages(
        self, query: str, context: Mapping[str, Any] | None
    ) -> Sequence[Mapping[str, Any]]:
        yield {"role": "system", "content": SYSTEM_PROMPT}
        yield from FEW_SHOT_MESSAGES
        payload = {
            "type": "query",
            "query": query,
            "context": dict(context or {}),
        }
        yield {"role": "user", "content": json.dumps(payload)}

    @staticmethod
    def _normalize_final(
        payload: Mapping[str, Any],
        steps: Sequence[Mapping[str, Any]],
        model_used: str | None,
    ) -> Mapping[str, Any]:
        final = {
            "type": "final",
            "answer": payload.get("answer", ""),
            "sources": payload.get("sources", []),
            "context": payload.get("context", {}),
            "steps": list(steps),
        }
        if "error" in payload:
            final["error"] = payload["error"]
        if model_used:
            final["planner_model_used"] = model_used
        return final

    def _record_event(
        self,
        state: MutableMapping[str, Any],
        *,
        node: str,
        status: str,
        duration: float,
        **details: Any,
    ) -> None:
        event = {
            "node": node,
            "status": status,
            "timestamp": time.time(),
            "duration": duration,
            "details": details,
        }
        state.setdefault("graph_events", []).append(event)
        summary = {
            "node": node,
            "status": status,
            "duration": round(duration, 3),
            **{k: v for k, v in details.items() if v is not None},
        }
        self.logger.info("planner.node %s", json.dumps(summary, default=str))

    def _run_with_timeout(
        self, func: Callable[[], Any], timeout: float, label: str
    ) -> Any:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError as exc:  # pragma: no cover - timeout guard
                future.cancel()
                raise TimeoutError(f"{label} timed out after {timeout} seconds") from exc

    def _call_llm_json(
        self,
        messages: Sequence[Mapping[str, Any]],
        model_hint: str | None,
    ) -> tuple[Mapping[str, Any], str | None]:
        attempts = 0
        delay = self.llm_initial_backoff
        last_error: Exception | None = None
        candidates = self._model_candidates(model_hint)
        while attempts < self.llm_max_attempts:
            attempts += 1
            for candidate in candidates:
                model_name = candidate or getattr(self.llm, "default_model", None)
                try:
                    response = self._run_with_timeout(
                        lambda: self.llm.chat_json(messages, model=candidate),
                        self.node_timeout,
                        f"llm ({model_name or '<auto>'})",
                    )
                    if not isinstance(response, Mapping):
                        raise LLMError("LLM returned non-JSON payload")
                    payload = dict(response)
                    used_model = candidate or getattr(self.llm, "default_model", None)
                    if used_model:
                        payload.setdefault("planner_model_used", used_model)
                    return payload, used_model
                except Exception as exc:
                    last_error = exc
                    self.logger.warning(
                        "planner.llm failure attempt=%s model=%s error=%s",
                        attempts,
                        model_name or "<auto>",
                        exc,
                    )
                    time.sleep(min(delay, 5.0))
            delay = min(delay * 2, 10.0)
        raise LLMError(str(last_error) if last_error else "LLM unavailable")

    def _model_candidates(self, preferred: str | None) -> tuple[str | None, ...]:
        primary = preferred or self.default_model
        if not self.fallback_model or self.fallback_model == primary:
            return (primary,)
        return (primary, self.fallback_model)

    def _start_langsmith_run(
        self, query: str, context: Mapping[str, Any]
    ) -> str | None:
        client = self._langsmith_client
        if client is None:
            return None
        try:
            run = client.create_run(
                name="planner.graph",
                inputs={
                    "query": query,
                    "context": self._jsonable(context),
                },
                run_type="chain",
                project_name=self.langsmith_project,
                metadata={"max_iterations": self.max_iterations},
            )
            return run.get("id") if isinstance(run, Mapping) else None
        except Exception:  # pragma: no cover - observability optional
            self.logger.debug("planner.langsmith create_run failed", exc_info=True)
            return None

    def _finish_langsmith_run(
        self,
        run_id: str,
        *,
        outputs: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        client = self._langsmith_client
        if client is None:
            return
        try:
            client.update_run(
                run_id=run_id,
                outputs=self._jsonable(outputs) if outputs is not None else None,
                error=error,
            )
        except Exception:  # pragma: no cover - observability optional
            self.logger.debug("planner.langsmith update_run failed", exc_info=True)

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if value is None:
            return None
        try:
            json.dumps(value)
            return value
        except TypeError:
            return json.loads(json.dumps(value, default=str))

    def _finalize_payload(self, state: Mapping[str, Any]) -> Mapping[str, Any]:
        final = state.get("final")
        if isinstance(final, Mapping):
            payload = dict(final)
        else:
            payload = {
                "type": "final",
                "answer": "",
                "sources": [],
                "error": "planner did not complete",
                "steps": state.get("steps", []),
            }
        events = state.get("graph_events", [])
        payload["events"] = list(events)
        if state.get("last_model_used"):
            payload.setdefault("planner_model_used", state.get("last_model_used"))
        return payload


__all__ = ["PlannerAgent", "SYSTEM_PROMPT", "FEW_SHOT_MESSAGES"]
