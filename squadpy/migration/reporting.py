"""Shared report builders for migration analyzers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TypedDict

MappingCategory = Literal["safe", "review", "unsupported"]


class InventoryItem(TypedDict):
    """One source-to-target mapping inventory record."""

    source_key: str
    source_value: str
    target: str | None
    category: MappingCategory
    note: str


def load_json_config(config_path: Path) -> dict[str, Any]:
    """Load a JSON config object for report-first analyzers."""
    raw_text = config_path.read_text(encoding="utf-8")
    try:
        loaded = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"Expected top-level object in {config_path}")
    return loaded


def build_inventory_report(
    *,
    source: str,
    input_path: Path,
    inventory: list[InventoryItem],
    warnings: list[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Build a deterministic inventory report payload."""
    safe_count = sum(1 for item in inventory if item["category"] == "safe")
    review_count = sum(1 for item in inventory if item["category"] == "review")
    unsupported_count = sum(1 for item in inventory if item["category"] == "unsupported")

    return {
        "source": source,
        "input_path": str(input_path),
        "dry_run": dry_run,
        "writes": [],
        "warnings": warnings or [],
        "summary": {
            "total": len(inventory),
            "safe": safe_count,
            "review": review_count,
            "unsupported": unsupported_count,
        },
        "inventory": inventory,
    }
