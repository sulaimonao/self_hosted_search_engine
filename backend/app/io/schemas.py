from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from .models import (
    ALLOWED_VERBS,
    Directive,
    Incident,
    Step,
    VERB_EXECUTION_METADATA,
    VERB_MAP,
)


def _ordered(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {key: mapping[key] for key in sorted(mapping)}


def _schema(model: type[Directive] | type[Incident] | type[Step]) -> dict[str, Any]:
    return model.model_json_schema(by_alias=True)


@lru_cache(maxsize=1)
def chat_schema() -> dict[str, Any]:
    from backend.app.api.schemas import (
        AutopilotDirective,
        AutopilotToolDirective,
        ChatMessage,
        ChatRequest,
        ChatResponsePayload,
        ChatStreamComplete,
        ChatStreamDelta,
        ChatStreamError,
        ChatStreamMetadata,
    )

    return {
        "request": ChatRequest.model_json_schema(by_alias=True),
        "message": ChatMessage.model_json_schema(by_alias=True),
        "response": ChatResponsePayload.model_json_schema(by_alias=True),
        "stream": {
            "metadata": ChatStreamMetadata.model_json_schema(by_alias=True),
            "delta": ChatStreamDelta.model_json_schema(by_alias=True),
            "complete": ChatStreamComplete.model_json_schema(by_alias=True),
            "error": ChatStreamError.model_json_schema(by_alias=True),
        },
        "autopilot": {
            "directive": AutopilotDirective.model_json_schema(by_alias=True),
            "tool": AutopilotToolDirective.model_json_schema(by_alias=True),
        },
    }


@lru_cache(maxsize=1)
def self_heal_schema() -> dict[str, Any]:
    directive_schema = _schema(Directive)
    incident_schema = _schema(Incident)
    step_schema = _schema(Step)

    return {
        "incident": incident_schema,
        "directive": directive_schema,
        "step": step_schema,
        "allowedVerbs": sorted(ALLOWED_VERBS),
        "verbMap": _ordered(VERB_MAP),
        "verbMetadata": [
            {"verb": verb, **VERB_EXECUTION_METADATA.get(verb, {})}
            for verb in sorted(ALLOWED_VERBS)
        ],
    }


__all__ = ["chat_schema", "self_heal_schema"]
