"""Linter/report generator for migrated TOML mapping inventories."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import tomllib
from typing import Any, Literal, TypedDict

from squadpy.migration.reporting import MappingCategory

Severity = Literal["info", "warning", "error"]

SAFE_TARGETS = {
    "admin_request",
    "auto_kick_unassigned",
    "discord_chat_bridge",
    "discord_admin_broadcast",
    "discord_admin_cam_logs",
    "discord_killfeed",
    "discord_round_events",
    "discord_squad_created",
    "discord_teamkill",
    "switch_command",
    "tk_warn",
}

REVIEW_TARGETS = {
    "chat_commands",
    "db_log",
    "end_match_vote",
    "fog_of_war",
    "heli_crash_broadcast",
    "intervalled_broadcasts",
    "max_player_in_squad",
    "seeding_mode",
    "squad_name_validator",
    "team_randomizer",
}


class LintFinding(TypedDict):
    """One actionable linter result entry."""

    source: str
    target: str | None
    category: MappingCategory
    severity: Severity
    message: str
    fixup: str


def lint_migrated_toml(config_path: Path) -> dict[str, Any]:
    """Lint migrated mapping TOML and emit categorized remediation report."""
    findings: list[LintFinding] = []

    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        findings.append({
            "source": str(config_path),
            "target": None,
            "category": "unsupported",
            "severity": "error",
            "message": f"Invalid TOML syntax: {exc}",
            "fixup": "Fix TOML syntax errors before running migration validation.",
        })
        return _build_report(config_path, findings)

    raw_mappings = parsed.get("mappings")
    if not isinstance(raw_mappings, list):
        findings.append({
            "source": "mappings",
            "target": None,
            "category": "unsupported",
            "severity": "error",
            "message": "Missing [[mappings]] entries in migrated TOML.",
            "fixup": "Add one [[mappings]] table per source plugin with source and target fields.",
        })
        return _build_report(config_path, findings)

    for index, mapping in enumerate(raw_mappings):
        if not isinstance(mapping, dict):
            findings.append({
                "source": f"mappings[{index}]",
                "target": None,
                "category": "unsupported",
                "severity": "error",
                "message": "Mapping entry must be a TOML table.",
                "fixup": "Use [[mappings]] with key/value pairs instead of scalar entries.",
            })
            continue

        source = mapping.get("source")
        target = mapping.get("target")
        source_name = source.strip() if isinstance(source, str) else f"mappings[{index}]"
        normalized_target = target.strip() if isinstance(target, str) and target.strip() else None
        category = _resolve_category(normalized_target)
        severity = _severity_for_category(category)
        findings.append({
            "source": source_name,
            "target": normalized_target,
            "category": category,
            "severity": severity,
            "message": _message_for_category(source_name, normalized_target, category),
            "fixup": _fixup_for_category(normalized_target, category),
        })

    _append_duplicate_target_findings(findings)
    return _build_report(config_path, findings)


def _resolve_category(target: str | None) -> MappingCategory:
    if target is None:
        return "unsupported"
    if target in SAFE_TARGETS:
        return "safe"
    if target in REVIEW_TARGETS:
        return "review"
    return "unsupported"


def _severity_for_category(category: MappingCategory) -> Severity:
    if category == "safe":
        return "info"
    if category == "review":
        return "warning"
    return "error"


def _message_for_category(source: str, target: str | None, category: MappingCategory) -> str:
    if category == "safe" and target is not None:
        return f"{source} maps cleanly to SquadPy plugin {target}."
    if category == "review" and target is not None:
        return f"{source} maps to {target} but needs manual behavior review."
    if target is None:
        return f"{source} has no mapped SquadPy target plugin."
    return f"{source} maps to unknown target plugin {target}."


def _fixup_for_category(target: str | None, category: MappingCategory) -> str:
    if category == "safe" and target is not None:
        return f"Copy baseline settings into config/plugins/{target}.toml and validate in staging."
    if category == "review" and target is not None:
        return f"Review config/plugins/{target}.toml thresholds and command permissions before cutover."
    if target is None:
        return "Define an explicit supported target plugin or keep this capability external until implemented."
    return (
        f"Target plugin {target} is not in the migration inventory. "
        "Re-map to a supported plugin or implement a custom SquadPy plugin."
    )


def _append_duplicate_target_findings(findings: list[LintFinding]) -> None:
    target_counts = Counter(
        finding["target"]
        for finding in findings
        if finding["target"] is not None
    )
    for target, count in target_counts.items():
        if target is None or count <= 1:
            continue
        findings.append({
            "source": target,
            "target": target,
            "category": "review",
            "severity": "warning",
            "message": f"Target plugin {target} is mapped from {count} source entries.",
            "fixup": "Confirm duplicate mappings are intentional and de-duplicate if the behavior should remain singular.",
        })


def _build_report(config_path: Path, findings: list[LintFinding]) -> dict[str, Any]:
    category_counts = Counter(finding["category"] for finding in findings)
    severity_counts = Counter(finding["severity"] for finding in findings)
    return {
        "source": "migrated_toml_linter",
        "input_path": str(config_path),
        "writes": [],
        "summary": {
            "total_findings": len(findings),
            "safe": category_counts.get("safe", 0),
            "review": category_counts.get("review", 0),
            "unsupported": category_counts.get("unsupported", 0),
            "info": severity_counts.get("info", 0),
            "warning": severity_counts.get("warning", 0),
            "error": severity_counts.get("error", 0),
            "has_blockers": severity_counts.get("error", 0) > 0,
        },
        "findings": findings,
    }
