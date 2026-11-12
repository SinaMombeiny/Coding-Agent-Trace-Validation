#!/usr/bin/env python3
"""Read-only evidence triage for Coding-Agent Trace Validation (v2).

This helper scans saved local outputs only. It does not contact GitHub and does
not modify the candidate CSV, evidence inventory, or upstream pipeline data.

Run from the agent-impact project root:
    python3 batch_audit_v2.py

Optional:
    python3 batch_audit_v2.py --root . --output-dir audit/v2_outputs

Important distinctions:
- commit_stats_main.csv contains upstream commit classifications when the
  upstream adopter gate caused commit analysis to run.
- commit_list.csv and pr_commits.csv contain raw commit records. They do not
  establish an AI/Human classification by themselves.
- Missing commit_stats_main.csv is reported as classification unavailable,
  never silently interpreted as Human or as evidence of non-use.
- Direct traces in raw commits with unavailable classification are kept in an
  unclassified bucket. They are not called confirmed RQ3 misses.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPT_VERSION = "2.0.0"
DEFAULT_CANDIDATES = Path("audit/manual_audit_candidates.csv")
DEFAULT_REPORT = Path("temp/sina-starred-59/analysis_report_56.csv")
DEFAULT_INVENTORY = Path("audit/evidence_inventory.csv")
DEFAULT_OUTPUT = Path("audit/v2_outputs")

TRAILER_RE = re.compile(r"(?im)^\s*co-?authored-by\s*:\s*(.*?)\s*$")
GENERATED_RE = re.compile(
    r"(?i)\b(?:generated|created|written)\s+(?:with|by)\s+"
    r"(Claude\s+Code|Codex(?:\s+CLI)?|Cursor|GitHub\s+Copilot|Copilot)\b"
)
COPILOT_AUTOFIX_RE = re.compile(r"(?i)\bCopilot\s+Autofix\s+powered\s+by\s+AI\b")
EMAIL_RE = re.compile(r"^(.*?)\s*<([^<>]+)>\s*$")

STRICT_TRAILER_IDENTITIES = {
    "claude": {"noreply@anthropic.com"},
    "cursor": {"cursoragent@cursor.com"},
    "codex": {"noreply@openai.com"},
}
TOOL_CANONICAL = {
    "claude code": "Claude Code",
    "claude": "Claude Code",
    "codex": "Codex",
    "codex cli": "Codex",
    "cursor": "Cursor",
    "github copilot": "GitHub Copilot",
    "copilot": "GitHub Copilot",
}
SHA_FIELDS = ("sha", "commit_sha", "commitSha", "oid", "commit_oid")
PR_NUMBER_FIELDS = ("number", "pr_number", "pull_number", "pull_request_number", "pullRequestNumber")
AI_TYPES = {"AI", "AI-FOLLOWUP"}
KNOWN_NON_AI_TYPES = {"HUMAN", "BOT"}


@dataclass(frozen=True)
class Evidence:
    repository: str
    commit_sha: str
    tool: str
    evidence_type: str
    source_file: str
    detail: str
    commit_pipeline_type: str = "NOT_AVAILABLE"
    linked_pr_number: str = ""
    linked_commit_shas: str = ""


def read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_repo_url(value: str) -> str:
    return (value or "").strip().rstrip("/").lower()


def first_nonempty(row: dict[str, Any], names: Iterable[str]) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return value


def exact_trailer_tool(trailer: str) -> str | None:
    """Return a tool only for a strict known agent co-author identity."""
    match = EMAIL_RE.match((trailer or "").strip())
    if not match:
        return None
    display_name = match.group(1).strip().lower()
    email = match.group(2).strip().lower()

    if display_name.startswith("claude") and email in STRICT_TRAILER_IDENTITIES["claude"]:
        return "Claude Code"
    if display_name in {"cursor", "cursor agent"} and email in STRICT_TRAILER_IDENTITIES["cursor"]:
        return "Cursor"
    if display_name in {"codex", "openai codex"} and email in STRICT_TRAILER_IDENTITIES["codex"]:
        return "Codex"
    return None


def explicit_message_evidence(message: str) -> list[tuple[str, str, str]]:
    """Return explicit (tool, evidence_type, detail) traces from message text."""
    found: list[tuple[str, str, str]] = []
    content = message or ""

    for trailer in TRAILER_RE.findall(content):
        tool = exact_trailer_tool(trailer)
        if tool:
            found.append((tool, "exact_agent_coauthor_trailer", trailer.strip()))

    for match in GENERATED_RE.finditer(content):
        label = re.sub(r"\s+", " ", match.group(1).strip()).lower()
        tool = TOOL_CANONICAL.get(label)
        if tool:
            found.append((tool, "explicit_generated_with_by_statement", match.group(0).strip()))

    if COPILOT_AUTOFIX_RE.search(content):
        found.append(("GitHub Copilot", "explicit_copilot_autofix_signature", "Copilot Autofix powered by AI"))

    unique: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def normalise_number(value: str) -> str:
    return str(value or "").strip().removeprefix("#")


def parse_list(value: Any) -> list[str]:
    parsed = parse_jsonish(value)
    if isinstance(parsed, list):
        values: list[str] = []
        for item in parsed:
            if isinstance(item, dict):
                label = first_nonempty(item, ("name", "label", "title"))
                values.append(label or json.dumps(item, ensure_ascii=False))
            else:
                values.append(str(item))
        return values
    if isinstance(parsed, dict):
        label = first_nonempty(parsed, ("name", "label", "title"))
        return [label or json.dumps(parsed, ensure_ascii=False)]
    if parsed in (None, ""):
        return []
    return [str(parsed)]


def build_pr_index(pr_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in pr_rows:
        number = normalise_number(first_nonempty(row, PR_NUMBER_FIELDS))
        if number:
            index[number] = row
    return index


def build_commit_to_pr_map(pr_commit_rows: list[dict[str, str]]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = defaultdict(set)
    for row in pr_commit_rows:
        sha = first_nonempty(row, SHA_FIELDS).lower()
        number = normalise_number(first_nonempty(row, PR_NUMBER_FIELDS))
        if sha and number:
            mapping[sha].add(number)
    return mapping


def weak_pr_clues(pr: dict[str, str]) -> list[str]:
    clues: list[str] = []
    branch = first_nonempty(pr, ("branch_name", "head_ref", "headRefName", "branch"))
    if branch:
        for tool, pattern in (
            ("Codex", re.compile(r"(^|[/_-])codex([/_-]|$)", re.I)),
            ("Claude Code", re.compile(r"(^|[/_-])claude([/_-]|$)", re.I)),
            ("Cursor", re.compile(r"(^|[/_-])cursor([/_-]|$)", re.I)),
            ("GitHub Copilot", re.compile(r"(^|[/_-])copilot([/_-]|$)", re.I)),
        ):
            if pattern.search(branch):
                clues.append(f"branch name resembles {tool}: {branch}")
    labels = parse_list(first_nonempty(pr, ("labels", "label_names")))
    known = {"codex", "claude", "claude code", "cursor", "copilot", "github copilot"}
    for label in labels:
        if label.strip().lower() in known:
            clues.append(f"PR label: {label.strip()}")
    return clues


def discover_repo_dir(root: Path, report_row: dict[str, str]) -> Path | None:
    raw = first_nonempty(report_row, ("path", "repo_path", "directory", "local_path"))
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    tries = [candidate] if candidate.is_absolute() else [root / "code" / candidate, root / candidate]
    for path in tries:
        try:
            resolved = path.resolve()
            if resolved.is_dir() and (root.resolve() == resolved or root.resolve() in resolved.parents):
                return resolved
        except OSError:
            continue
    return None


def find_data_file(repo_dir: Path, basename: str) -> Path | None:
    matches = sorted(repo_dir.rglob(basename))
    return matches[0] if matches else None


def relative_source(path: Path | None, root: Path, fallback: str) -> str:
    if path is None:
        return fallback
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def analyse_repository(
    root: Path,
    candidate: dict[str, str],
    report_row: dict[str, str] | None,
    inventory_row: dict[str, str] | None,
) -> tuple[dict[str, Any], list[Evidence]]:
    repo_url = candidate.get("github_url", "")
    summary: dict[str, Any] = {
        "github_url": repo_url,
        "selection_group": candidate.get("selection_group", ""),
        "current_manual_status": (candidate.get("audit_status") or "").strip() or "pending",
        "tool_use": candidate.get("tool_use", ""),
        "commit_use": candidate.get("commit_use", ""),
        "ignored_tools": candidate.get("ignored_tools", ""),
        "local_directory_found": False,
        "commit_stats_found": False,
        "commit_list_found": False,
        "pr_list_found": False,
        "pr_commits_found": False,
        "classification_availability": "not_available",
        "commit_stats_rows": 0,
        "raw_commit_list_rows": 0,
        "pr_commit_rows": 0,
        "unique_commit_shas_scanned": 0,
        "pipeline_ai_label_rows": 0,
        "direct_attribution_commit_shas": 0,
        "direct_attribution_ai_labeled_shas": 0,
        "direct_attribution_ai_followup_shas": 0,
        "direct_attribution_human_or_bot_labeled_shas": 0,
        "direct_attribution_unclassified_shas": 0,
        "linked_pr_disclosure_prs_with_ai_commit": 0,
        "linked_pr_disclosure_prs_with_human_or_bot_commit": 0,
        "linked_pr_disclosure_prs_with_unclassified_commit": 0,
        "linked_prs_with_explicit_disclosure": 0,
        "linked_prs_with_weak_clues": 0,
        "repo_level_evidence_recommendation": "manual_review",
        "review_reason": "",
        "inventory_file_markers": "",
        "inventory_gitignore_matches": "",
        "data_warnings": "",
    }
    evidence: list[Evidence] = []

    if not report_row:
        summary["review_reason"] = "No matching row in the main analysis report."
        summary["data_warnings"] = "main report row missing"
        return summary, evidence

    repo_dir = discover_repo_dir(root, report_row)
    if not repo_dir:
        summary["review_reason"] = "Local analysis directory could not be resolved from the report path."
        summary["data_warnings"] = "repository output directory missing or outside project root"
        return summary, evidence

    summary["local_directory_found"] = True

    stats_file = find_data_file(repo_dir, "commit_stats_main.csv")
    raw_commit_file = find_data_file(repo_dir, "commit_list.csv")
    pr_file = find_data_file(repo_dir, "pr_list.csv")
    pr_commit_file = find_data_file(repo_dir, "pr_commits.csv")

    stats_rows = read_csv(stats_file)
    raw_commit_rows = read_csv(raw_commit_file)
    pr_rows = read_csv(pr_file)
    pr_commit_rows = read_csv(pr_commit_file)

    summary["commit_stats_found"] = stats_file is not None
    summary["commit_list_found"] = raw_commit_file is not None
    summary["pr_list_found"] = pr_file is not None
    summary["pr_commits_found"] = pr_commit_file is not None
    summary["classification_availability"] = "available" if stats_file is not None else "not_available"
    summary["commit_stats_rows"] = len(stats_rows)
    summary["raw_commit_list_rows"] = len(raw_commit_rows)
    summary["pr_commit_rows"] = len(pr_commit_rows)
    summary["pipeline_ai_label_rows"] = sum(
        first_nonempty(row, ("auth_type", "type")).upper() == "AI"
        for row in stats_rows
    )

    stats_type_by_sha: dict[str, str] = {}
    for row in stats_rows:
        sha = first_nonempty(row, SHA_FIELDS).lower()
        if sha:
            stats_type_by_sha[sha] = first_nonempty(row, ("auth_type", "type")).upper() or "UNKNOWN"

    # Build a union of trace-bearing commit records from all available files.
    # Prefer the classified row's message, then commit_list, then PR commit rows.
    records: list[tuple[dict[str, str], Path | None, str]] = []
    records.extend((row, stats_file, "commit_stats_main") for row in stats_rows)
    records.extend((row, raw_commit_file, "commit_list") for row in raw_commit_rows)
    records.extend((row, pr_commit_file, "pr_commits") for row in pr_commit_rows)

    all_sha_values = {
        first_nonempty(row, SHA_FIELDS).lower()
        for row, _, _ in records
        if first_nonempty(row, SHA_FIELDS)
    }
    summary["unique_commit_shas_scanned"] = len(all_sha_values)

    direct_by_sha: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    seen_evidence: set[tuple[str, str, str, str]] = set()

    for row, source_path, source_kind in records:
        sha = first_nonempty(row, SHA_FIELDS).lower()
        if not sha:
            continue
        pipeline_type = stats_type_by_sha.get(sha, "NOT_AVAILABLE")
        message = first_nonempty(row, ("message", "commit_message", "message_body"))
        for tool, evidence_type, detail in explicit_message_evidence(message):
            signature = (sha, tool, evidence_type, detail)
            direct_by_sha[sha].add((tool, evidence_type, detail))
            if signature in seen_evidence:
                continue
            seen_evidence.add(signature)
            evidence.append(Evidence(
                repository=repo_url,
                commit_sha=sha,
                tool=tool,
                evidence_type=evidence_type,
                source_file=relative_source(source_path, root, source_kind),
                detail=detail[:500],
                commit_pipeline_type=pipeline_type,
                linked_pr_number=(normalise_number(first_nonempty(row, PR_NUMBER_FIELDS)) if source_kind == "pr_commits" else ""),
            ))

    direct_shas = set(direct_by_sha)
    summary["direct_attribution_commit_shas"] = len(direct_shas)
    summary["direct_attribution_ai_labeled_shas"] = sum(
        stats_type_by_sha.get(sha) == "AI" for sha in direct_shas
    )
    summary["direct_attribution_ai_followup_shas"] = sum(
        stats_type_by_sha.get(sha) == "AI-FOLLOWUP" for sha in direct_shas
    )
    summary["direct_attribution_human_or_bot_labeled_shas"] = sum(
        stats_type_by_sha.get(sha) in KNOWN_NON_AI_TYPES for sha in direct_shas
    )
    summary["direct_attribution_unclassified_shas"] = sum(
        stats_type_by_sha.get(sha, "NOT_AVAILABLE") not in (AI_TYPES | KNOWN_NON_AI_TYPES)
        for sha in direct_shas
    )

    pr_index = build_pr_index(pr_rows)
    commit_to_pr = build_commit_to_pr_map(pr_commit_rows)
    pr_to_shas: dict[str, set[str]] = defaultdict(set)
    for sha, numbers in commit_to_pr.items():
        for number in numbers:
            pr_to_shas[number].add(sha)

    for number, pr in pr_index.items():
        merge_sha = first_nonempty(pr, ("merge_commit_sha", "mergeCommitSha")).lower()
        if merge_sha:
            pr_to_shas[number].add(merge_sha)

    disclosed_pr_numbers: set[str] = set()
    disclosed_ai_prs: set[str] = set()
    disclosed_non_ai_prs: set[str] = set()
    disclosed_unclassified_prs: set[str] = set()
    weak_pr_numbers: set[str] = set()

    for number, pr in pr_index.items():
        related_shas = pr_to_shas.get(number, set())
        body = first_nonempty(pr, ("bodyText", "body", "description"))
        pr_evidence = explicit_message_evidence(body)

        if pr_evidence and related_shas:
            disclosed_pr_numbers.add(number)
            types = {stats_type_by_sha.get(sha, "NOT_AVAILABLE") for sha in related_shas}
            if "AI" in types:
                disclosed_ai_prs.add(number)
            if types & KNOWN_NON_AI_TYPES:
                disclosed_non_ai_prs.add(number)
            if "NOT_AVAILABLE" in types or not types:
                disclosed_unclassified_prs.add(number)

            linked_shas = ";".join(sorted(related_shas))
            merged_at = first_nonempty(pr, ("merged_at", "mergedAt"))
            for tool, evidence_type, detail in pr_evidence:
                evidence.append(Evidence(
                    repository=repo_url,
                    commit_sha="",
                    tool=tool,
                    evidence_type="linked_pr_" + evidence_type,
                    source_file=relative_source(pr_file, root, "pr_list.csv"),
                    detail=(detail + (f"; merged_at={merged_at}" if merged_at else "; merged_at is empty in saved PR data"))[:500],
                    commit_pipeline_type="PR_LEVEL",
                    linked_pr_number=number,
                    linked_commit_shas=linked_shas,
                ))
        elif weak_pr_clues(pr):
            weak_pr_numbers.add(number)

    summary["linked_prs_with_explicit_disclosure"] = len(disclosed_pr_numbers)
    summary["linked_pr_disclosure_prs_with_ai_commit"] = len(disclosed_ai_prs)
    summary["linked_pr_disclosure_prs_with_human_or_bot_commit"] = len(disclosed_non_ai_prs)
    summary["linked_pr_disclosure_prs_with_unclassified_commit"] = len(disclosed_unclassified_prs)
    summary["linked_prs_with_weak_clues"] = len(weak_pr_numbers)

    inv = inventory_row or {}
    file_markers = parse_list(inv.get("file_markers"))
    gitignore = parse_list(inv.get("gitignore_matches"))
    summary["inventory_file_markers"] = "; ".join(file_markers)
    summary["inventory_gitignore_matches"] = "; ".join(gitignore)

    has_direct = bool(direct_shas or disclosed_pr_numbers)
    has_weak = bool(weak_pr_numbers or file_markers or gitignore)
    if has_direct:
        summary["repo_level_evidence_recommendation"] = "supported_candidate"
        summary["review_reason"] = (
            "Strict direct attribution was recovered from a saved commit message or an explicitly disclosed PR "
            "with an exact SHA relationship. This is a repository-level candidate for human confirmation; "
            "it does not validate every pipeline-labelled commit."
        )
    elif has_weak:
        summary["repo_level_evidence_recommendation"] = "ambiguous_candidate"
        summary["review_reason"] = (
            "Only indirect clues were recovered (branch/label, file marker, or .gitignore match). "
            "These do not independently establish coding-agent use."
        )
    else:
        summary["repo_level_evidence_recommendation"] = "manual_review"
        summary["review_reason"] = (
            "No strict direct evidence was recovered from the available local files. "
            "This does not establish non-use; the result remains unresolved."
        )

    warnings: list[str] = []
    if stats_file is None:
        warnings.append("commit_stats_main.csv missing; upstream commit classification is not available")
    if raw_commit_file is None:
        warnings.append("commit_list.csv missing; raw commit-message coverage may be incomplete")
    if pr_file is None:
        warnings.append("pr_list.csv missing; PR-body evidence unavailable")
    if pr_commit_file is None:
        warnings.append("pr_commits.csv missing; exact PR-to-commit mapping may be incomplete")
    if not inventory_row:
        warnings.append("evidence_inventory.csv row missing; file/.gitignore markers unavailable")
    summary["data_warnings"] = "; ".join(warnings)

    return summary, evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="agent-impact project root")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()

    def resolve_path(path: Path) -> Path:
        return path.expanduser().resolve() if path.is_absolute() else (root / path).resolve()

    candidates_path = resolve_path(args.candidates)
    report_path = resolve_path(args.report)
    inventory_path = resolve_path(args.inventory)
    output_dir = resolve_path(args.output_dir)

    for required in (candidates_path, report_path):
        if not required.is_file():
            print(f"ERROR: required file not found: {required}", file=sys.stderr)
            return 2

    candidates = read_csv(candidates_path)
    report_rows = read_csv(report_path)
    reports = {canonical_repo_url(row.get("github_url", "")): row for row in report_rows}
    inventories = {canonical_repo_url(row.get("github_url", "")): row for row in read_csv(inventory_path)}
    if not candidates:
        print("ERROR: manual audit candidate CSV contains no rows.", file=sys.stderr)
        return 2

    summaries: list[dict[str, Any]] = []
    all_evidence: list[Evidence] = []
    for candidate in candidates:
        key = canonical_repo_url(candidate.get("github_url", ""))
        summary, repo_evidence = analyse_repository(root, candidate, reports.get(key), inventories.get(key))
        summaries.append(summary)
        all_evidence.extend(repo_evidence)

    # Preserve earlier runs instead of overwriting a non-empty output directory.
    if output_dir.exists() and any(output_dir.iterdir()):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = output_dir.parent / f"{output_dir.name}_run_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_fields = list(summaries[0].keys())
    write_csv(output_dir / "batch_audit_v2_summary.csv", summaries, summary_fields)
    evidence_fields = list(asdict(all_evidence[0]).keys()) if all_evidence else list(Evidence.__dataclass_fields__.keys())
    write_csv(output_dir / "batch_audit_v2_evidence.csv", [asdict(item) for item in all_evidence], evidence_fields)

    counts = Counter(row["repo_level_evidence_recommendation"] for row in summaries)
    warnings_count = sum(bool(row["data_warnings"]) for row in summaries)
    report_lines = [
        "# Batch Audit v2 — Read-only Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Script version: {SCRIPT_VERSION}",
        "",
        "This run is read-only with respect to the candidate CSV, evidence inventory, and upstream pipeline outputs.",
        "The helper does not make live GitHub requests.",
        "Direct evidence is restricted to exact agent co-author trailers, explicit generated-with/by statements, and explicit Copilot Autofix signatures.",
        "Commit author and committer identity fields are not used for direct attribution. Generic #123 references are not used to link pull requests.",
        "Raw commit records without a matching commit_stats_main.csv row retain pipeline type NOT_AVAILABLE; they are not assumed to be Human.",
        "",
        "## Repository-level triage",
        "",
        "| Recommendation | Repositories |",
        "|---|---:|",
        f"| supported_candidate | {counts.get('supported_candidate', 0)} |",
        f"| ambiguous_candidate | {counts.get('ambiguous_candidate', 0)} |",
        f"| manual_review | {counts.get('manual_review', 0)} |",
        "",
        f"Repositories with data warnings: {warnings_count}/{len(summaries)}",
        "",
        "## Findings",
        "",
    ]
    for row in summaries:
        report_lines.extend([
            f"### {row['github_url']}",
            "",
            f"- Current manual status: `{row['current_manual_status']}`",
            f"- Recommendation: **{row['repo_level_evidence_recommendation']}**",
            f"- Commit classification available: `{row['classification_availability']}`",
            f"- Commit-stat rows: {row['commit_stats_rows']}",
            f"- Raw commit-list rows: {row['raw_commit_list_rows']}",
            f"- PR commit rows: {row['pr_commit_rows']}",
            f"- Unique commit SHAs scanned: {row['unique_commit_shas_scanned']}",
            f"- Pipeline AI-labelled rows: {row['pipeline_ai_label_rows']}",
            f"- Direct traces on any commit SHA: {row['direct_attribution_commit_shas']}",
            f"- Direct traces on AI-labelled commits: {row['direct_attribution_ai_labeled_shas']}",
            f"- Direct traces on AI-FOLLOWUP commits: {row['direct_attribution_ai_followup_shas']}",
            f"- Direct traces on known Human/Bot-labelled commits: {row['direct_attribution_human_or_bot_labeled_shas']}",
            f"- Direct traces on commits with no available pipeline classification: {row['direct_attribution_unclassified_shas']}",
            f"- Exactly linked PR disclosures whose linked commit set includes an AI-labelled SHA (PR count): {row['linked_pr_disclosure_prs_with_ai_commit']}",
            f"- Exactly linked PR disclosures whose linked commit set includes a known Human/Bot-labelled SHA (PR count): {row['linked_pr_disclosure_prs_with_human_or_bot_commit']}",
            f"- Exactly linked PR disclosures whose linked commit set includes an unclassified SHA (PR count): {row['linked_pr_disclosure_prs_with_unclassified_commit']}",
            f"- Linked PRs with explicit disclosure: {row['linked_prs_with_explicit_disclosure']}",
            f"- PRs with indirect branch/label clues: {row['linked_prs_with_weak_clues']}",
            f"- Data warnings: {row['data_warnings'] or 'None'}",
            f"- Interpretation: {row['review_reason']}",
            "",
        ])
    report_lines.extend([
        "## Required interpretation",
        "",
        "- These are triage recommendations, not final human audit labels.",
        "- `supported_candidate` means at least one strict direct trace was recovered from saved public commit/PR records; human confirmation is still required.",
        "- `ambiguous_candidate` means indirect clues were found; those clues are not proof.",
        "- `manual_review` means the local evidence was insufficient; it does not mean no agent was used.",
        "- Direct traces on commits explicitly labelled Human or Bot are RQ3 candidates; traces on commits with unavailable classification remain unclassified and are not counted as confirmed RQ3 misses.",
        "- Missing input files reduce coverage and must be reported, not interpreted as negative evidence.",
        "",
    ])
    (output_dir / "batch_audit_v2_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    manifest = {
        "script_version": SCRIPT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "read-only local triage; no network requests",
        "candidate_count": len(candidates),
        "input_files": {
            str(path.relative_to(root) if root in path.parents else path): {
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in (candidates_path, report_path, inventory_path)
            if path.is_file()
        },
        "output_files": [
            "batch_audit_v2_summary.csv",
            "batch_audit_v2_evidence.csv",
            "batch_audit_v2_report.md",
            "run_manifest.json",
        ],
        "recommendation_counts": dict(counts),
        "repositories_with_data_warnings": warnings_count,
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("===== BATCH AUDIT V2 COMPLETE =====")
    print("Version:", SCRIPT_VERSION)
    print("Mode: READ-ONLY")
    print("Network requests: NONE")
    print("Repositories:", len(summaries))
    print("Unique evidence rows:", len(all_evidence))
    print("Recommendations:", dict(counts))
    print("Repositories with data warnings:", warnings_count)
    print("Output:", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
