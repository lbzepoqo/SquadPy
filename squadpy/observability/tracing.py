"""Lightweight in-memory tracing for critical runtime paths."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from threading import Lock
from typing import Any

TraceAttributeValue = str | int | float | bool


@dataclass(frozen=True, slots=True)
class TraceSpan:
    """One trace span record."""

    name: str
    started_at_epoch_ms: int
    duration_ms: float
    status: str
    attributes: dict[str, TraceAttributeValue]


class TraceRecorder:
    """Thread-safe ring buffer for recent trace spans."""

    def __init__(self, max_spans: int = 2000):
        self._max_spans = max(1, int(max_spans))
        self._spans: list[TraceSpan] = []
        self._lock = Lock()

    def record_span(
        self,
        *,
        name: str,
        started_at_epoch_ms: int,
        duration_ms: float,
        status: str,
        attributes: dict[str, TraceAttributeValue] | None = None,
    ) -> None:
        span = TraceSpan(
            name=name,
            started_at_epoch_ms=int(started_at_epoch_ms),
            duration_ms=float(duration_ms),
            status=str(status).strip().lower() or "unknown",
            attributes=dict(attributes or {}),
        )
        with self._lock:
            self._spans.append(span)
            if len(self._spans) > self._max_spans:
                self._spans = self._spans[-self._max_spans :]

    def recent_spans(
        self,
        *,
        name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        trace_name = str(name).strip() or None if name is not None else None
        max_items = max(1, int(limit))
        with self._lock:
            spans = list(self._spans)
        if trace_name is not None:
            spans = [span for span in spans if span.name == trace_name]
        return [self._span_as_dict(span) for span in spans[-max_items:]]

    def summary(self, *, name: str | None = None) -> dict[str, Any]:
        trace_name = str(name).strip() or None if name is not None else None
        with self._lock:
            spans = list(self._spans)
        if trace_name is not None:
            spans = [span for span in spans if span.name == trace_name]

        status_counts = Counter(span.status for span in spans)
        return {
            "total": len(spans),
            "ok": status_counts.get("ok", 0),
            "error": status_counts.get("error", 0),
            "other": max(0, len(spans) - status_counts.get("ok", 0) - status_counts.get("error", 0)),
        }

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()

    @staticmethod
    def _span_as_dict(span: TraceSpan) -> dict[str, Any]:
        return {
            "name": span.name,
            "started_at_epoch_ms": span.started_at_epoch_ms,
            "duration_ms": round(span.duration_ms, 3),
            "status": span.status,
            "attributes": dict(span.attributes),
        }


_TRACE_RECORDER = TraceRecorder()


def get_trace_recorder() -> TraceRecorder:
    """Return the process-level trace recorder."""
    return _TRACE_RECORDER
