from typing import Any, Mapping


def capture(
    event_name: str, props: Mapping[str, Any] | None = None, **kwargs: Any
) -> bool:
    return True
