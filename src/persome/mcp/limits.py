"""Small input guards shared by MCP tool entry points."""

from __future__ import annotations

import math
from collections.abc import Sequence


def bounded_int(value: int, *, minimum: int, maximum: int) -> int:
    """Clamp an integer knob to a documented resource-safe range."""
    return min(maximum, max(minimum, int(value)))


def bounded_text(name: str, value: str, *, maximum: int, allow_empty: bool = False) -> str:
    """Validate a model/client supplied string before expensive processing."""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{name} is required")
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return value


def bounded_optional_text(name: str, value: str | None, *, maximum: int) -> str | None:
    """Validate an optional string while preserving ``None``."""
    if value is None:
        return None
    return bounded_text(name, value, maximum=maximum, allow_empty=True)


def bounded_text_list(
    name: str,
    values: Sequence[str] | None,
    *,
    maximum_items: int,
    maximum_item_chars: int,
) -> list[str] | None:
    """Validate a bounded list of bounded strings."""
    if values is None:
        return None
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be a list of strings")
    if len(values) > maximum_items:
        raise ValueError(f"{name} exceeds {maximum_items} items")
    return [
        bounded_text(
            f"{name}[{index}]",
            value,
            maximum=maximum_item_chars,
            allow_empty=False,
        )
        for index, value in enumerate(values)
    ]


def bounded_float(value: float, *, minimum: float, maximum: float) -> float:
    """Clamp a finite float knob to a resource-safe range."""
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError("numeric value must be finite")
    return min(maximum, max(minimum, converted))
