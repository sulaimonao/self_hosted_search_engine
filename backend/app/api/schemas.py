"""Shared Pydantic schemas for HTTP APIs."""

from __future__ import annotations

from typing import Any, Iterable, Literal, Sequence

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}
_CHAT_ROLES = {"system", "user", "assistant", "tool"}


class ChatMessage(BaseModel):
    """Single chat message exchanged with the LLM."""

    role: str
    content: str = ""
    images: list[str] | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("role")
    @classmethod
    def _normalize_role(cls, value: str) -> str:
        role = (value or "").strip().lower()
        if role not in _CHAT_ROLES:
            raise ValueError("role must be one of system, user, assistant, or tool")
        return role

    @field_validator("content")
    @classmethod
    def _normalize_content(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("images", mode="before")
    @classmethod
    def _normalize_images(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = [value]
        if isinstance(value, Iterable):
            images: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    images.append(item.strip())
            return images or None
        raise ValueError("images must be a sequence of base64 strings")


class ChatRequest(BaseModel):
    """Validated chat invocation payload."""

    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool | None = None
    url: str | None = None
    text_context: str | None = None
    image_context: str | None = None
    client_timezone: str | None = None
    server_time: str | None = None
    server_timezone: str | None = None
    server_time_utc: str | None = None
    request_id: str | None = Field(
        default=None,
        alias="request_id",
        validation_alias=AliasChoices("request_id", "requestId"),
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator(
        "model",
        "url",
        "text_context",
        "image_context",
        "client_timezone",
        "server_time",
        "server_timezone",
        "server_time_utc",
        "request_id",
        mode="before",
    )
    @classmethod
    def _trim_optional_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value

    @model_validator(mode="after")
    def _require_messages(self) -> "ChatRequest":
        if not self.messages:
            raise ValueError("messages must contain at least one entry")
        return self

    @field_validator("stream", mode="before")
    @classmethod
    def _coerce_stream(cls, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _BOOL_TRUE:
                return True
            if lowered in _BOOL_FALSE:
                return False
            if not lowered:
                return None
        if isinstance(value, (int, float)):
            return bool(value)
        raise ValueError("stream must be a boolean flag")


class AutopilotToolDirective(BaseModel):
    """Actionable tool exposed to the frontend for follow-up execution."""

    label: str
    endpoint: str
    method: Literal["GET", "POST"] | None = None
    payload: dict[str, Any] | None = None
    description: str | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("label", "endpoint", mode="before")
    @classmethod
    def _trim_required(cls, value: Any) -> str:
        trimmed = str(value or "").strip()
        if not trimmed:
            raise ValueError("tool label and endpoint must be provided")
        return trimmed

    @field_validator("description", mode="before")
    @classmethod
    def _trim_optional(cls, value: Any) -> str | None:
        if value is None:
            return None
        trimmed = str(value).strip()
        return trimmed or None


class AutopilotDirective(BaseModel):
    """Directive requesting the UI to run follow-up autonomous actions."""

    mode: Literal["browser"]
    query: str
    reason: str | None = None
    tools: list[AutopilotToolDirective] | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: Any) -> str:
        trimmed = str(value or "").strip()
        if not trimmed:
            raise ValueError("query must be provided")
        return trimmed

    @field_validator("reason", mode="before")
    @classmethod
    def _trim_reason(cls, value: Any) -> str | None:
        if value is None:
            return None
        trimmed = str(value).strip()
        return trimmed or None


class ChatResponsePayload(BaseModel):
    """Canonical chat response returned to the frontend."""

    reasoning: str = ""
    answer: str = ""
    citations: list[str] = Field(default_factory=list)
    model: str | None = None
    trace_id: str | None = None
    autopilot: AutopilotDirective | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("reasoning", "answer", mode="before")
    @classmethod
    def _normalize_response_text(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("citations", mode="before")
    @classmethod
    def _coerce_citations(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (str, int, float)):
            value = [value]
        if isinstance(value, Iterable):
            citations = [str(item).strip() for item in value if str(item).strip()]
            return citations
        raise ValueError("citations must be an iterable of primitives")


class ChatStreamMetadata(BaseModel):
    """Initial metadata event for streamed chat responses."""

    type: Literal["metadata"] = "metadata"
    attempt: int = Field(ge=1)
    model: str | None = None
    trace_id: str | None = Field(default=None, alias="trace_id")
    request_id: str | None = Field(
        default=None,
        alias="request_id",
        validation_alias=AliasChoices("request_id", "requestId"),
    )

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ChatStreamDelta(BaseModel):
    """Incremental update event while streaming chat responses."""

    type: Literal["delta"] = "delta"
    answer: str | None = None
    reasoning: str | None = None
    citations: list[str] | None = None
    delta: str | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("answer", "reasoning", mode="before")
    @classmethod
    def _trim_optional(cls, value: Any) -> str | None:
        if value is None:
            return None
        trimmed = str(value).strip()
        return trimmed or None

    @field_validator("delta", mode="before")
    @classmethod
    def _trim_delta(cls, value: Any) -> str | None:
        if value is None:
            return None
        trimmed = str(value)
        return trimmed if trimmed else None

    @field_validator("citations", mode="before")
    @classmethod
    def _coerce_optional_citations(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, (str, int, float)):
            value = [value]
        if isinstance(value, Iterable):
            citations = [str(item).strip() for item in value if str(item).strip()]
            return citations or None
        raise ValueError("citations must be iterable")


class ChatStreamComplete(BaseModel):
    """Terminal streaming event containing the full chat payload."""

    type: Literal["complete"] = "complete"
    payload: ChatResponsePayload

    model_config = ConfigDict(extra="ignore")


class ChatStreamError(BaseModel):
    """Terminal streaming error event."""

    type: Literal["error"] = "error"
    error: str
    hint: str | None = None
    trace_id: str | None = Field(default=None, alias="trace_id")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class SearchHit(BaseModel):
    """Lightweight representation of a search result."""

    id: str | None = None
    url: str
    title: str
    snippet: str
    score: float | None = None
    blended_score: float | None = Field(default=None, alias="blendedScore")
    lang: str | None = None
    source_type: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class SearchResponsePayload(BaseModel):
    """Structured payload returned from the search endpoint."""

    status: str
    results: list[SearchHit] = Field(default_factory=list)
    llm_used: bool = Field(alias="llm_used")
    hits: list[SearchHit] | None = None
    answer: str | None = None
    sources: Sequence[dict[str, Any]] | None = None
    k: int | None = None
    job_id: str | None = None
    last_index_time: int | None = None
    confidence: float | None = None
    trigger_reason: str | None = None
    seed_count: int | None = None
    llm_model: str | None = None
    code: str | None = None
    detail: str | None = None
    error: str | None = None
    action: str | None = None
    candidates: list[dict[str, Any]] | None = None
    embedder_status: dict[str, Any] | None = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @field_validator("status")
    @classmethod
    def _require_status(cls, value: str) -> str:
        status = (value or "").strip()
        if not status:
            raise ValueError("status must be a non-empty string")
        return status

    @field_validator("job_id", "llm_model", "trigger_reason", mode="before")
    @classmethod
    def _trim_optional_identifiers(cls, value: Any) -> str | None:
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value


class SearchQueryParams(BaseModel):
    """Validated query parameters for /api/search."""

    q: str = Field(alias="query")
    llm: bool = False
    model: str | None = None
    page: int = 1
    size: int = 10
    shipit: bool = False

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("q", mode="before")
    @classmethod
    def _coerce_query(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("query parameter is required")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("query parameter is required")
        return trimmed

    @field_validator("model", mode="before")
    @classmethod
    def _trim_optional_model(cls, value: Any) -> str | None:
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value

    @field_validator("page", "size", mode="before")
    @classmethod
    def _parse_positive_int(cls, value: Any) -> int:
        if value in (None, "", "0"):
            return 1 if value != "0" else 0
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("must be an integer") from exc

    @field_validator("page")
    @classmethod
    def _validate_page(cls, value: int) -> int:
        return max(1, value)

    @field_validator("size")
    @classmethod
    def _validate_size(cls, value: int) -> int:
        return max(1, min(value, 100))

    @field_validator("llm", "shipit", mode="before")
    @classmethod
    def _parse_flag(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _BOOL_TRUE:
                return True
            if lowered in _BOOL_FALSE:
                return False
        return bool(value)


__all__ = [
    "AutopilotDirective",
    "AutopilotToolDirective",
    "ChatMessage",
    "ChatRequest",
    "ChatResponsePayload",
    "ChatStreamMetadata",
    "ChatStreamDelta",
    "ChatStreamComplete",
    "ChatStreamError",
    "SearchHit",
    "SearchResponsePayload",
    "SearchQueryParams",
]
