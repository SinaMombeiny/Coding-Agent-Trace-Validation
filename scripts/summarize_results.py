#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "temp/sina-starred-59/analysis_report_56.csv"
AUDIT = ROOT / "audit/manual_audit_candidates.csv"
AUTHOR_PATTERNS = ROOT / "config/patterns/authors.csv"
FILE_PATTERNS = ROOT / "config/patterns/files.csv"
OUT = ROOT / "audit/evidence_inventory.csv"
NOTES = ROOT / "audit/evidence_notes"

COAUTHOR_RE = re.compile(
    r"[Cc]o-[Aa]uthored-[Bb]y:\s*([^<]+)<([^>]+)>"
)
AI_TYPES = {"AI", "AI-FOLLOWUP"}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_author_patterns() -> list[dict[str, Any]]:
    """Read AI-author regexes using the upstream CSV's pattern semantics."""
    rows = read_csv(AUTHOR_PATTERNS)
    compiled = []
    for row in rows:
        if row.get("type", "").strip() != "AI":
            continue
        raw = row.get("pattern", "").strip()
        if not raw:
            continue
        try:
            compiled.append({
                "pattern": raw,
                "subtype": row.get("subtype", "").strip(),
                "regex": re.compile(raw),
            })
        except re.error as exc:
            print(f"WARNING: invalid author regex {raw!r}: {exc}")
    return compiled


def load_file_patterns() -> list[dict[str, Any]]:
    """
    Reproduce code/heuristics.py::load_patterns(..., is_files=True):
    escape bare dots and anchor each pattern to the beginning of a path
    or to a slash boundary. A '*' remains a regex quantifier, as upstream.
    """
    rows = read_csv(FILE_PATTERNS)
    compiled = []
    for row in rows:
        raw = row.get("pattern", "").strip()
        subtype = row.get("subtype", "").strip()
        if not raw:
            continue
        pattern = raw
        if "." in pattern and r"\." not in pattern:
            pattern = pattern.replace(".", r"\.")
        if not pattern.startswith("(?:^|/)") and not pattern.startswith("^"):
            pattern = "(?:^|/)" + pattern
        try:
            compiled.append({
                "source_pattern": raw,
                "compiled_pattern": pattern,
                "subtype": subtype,
                "regex": re.compile(pattern),
            })
        except re.error as exc:
            print(f"WARNING: invalid file regex {raw!r}: {exc}")
    return compiled


def parse_json_cell(value: str | None, fallback: Any) -> Any:
    if value is None or not value.strip():
        return fallback
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def person_fields(person: Any) -> list[str]:
    """Return identity fields from a JSON-serialized Author or plain string."""
    if isinstance(person, dict):
        return [
            str(person.get(key, "")).strip()
            for key in ("login", "name", "email")
            if person.get(key) not in (None, "")
        ]
    if isinstance(person, str):
        parsed = parse_json_cell(person, None)
        if parsed is not None:
            return person_fields(parsed)
        return [person.strip()] if person.strip() else []
    if isinstance(person, list):
        values: list[str] = []
        for item in person:
            values.extend(person_fields(item))
        return values
    return []


def person_label(person: Any) -> str:
    fields = person_fields(person)
    return " | ".join(fields) if fields else "(identity unavailable)"


def pattern_hits(fields: list[str], patterns: list[dict[str, Any]]) -> list[str]:
    hits = []
    for item in patterns:
        if any(item["regex"].search(field) for field in fields):
            label = item["subtype"] or "unspecified"
            hits.append(f"{label}: {item['pattern']}")
    return list(dict.fromkeys(hits))


def message_coauthors(message: str) -> list[dict[str, str]]:
    results = []
    for name, email in COAUTHOR_RE.findall(message or ""):
        results.append({"login": "", "name": name.strip(), "email": email.strip()})
    return results


def dedupe_people(people: list[Any]) -> list[Any]:
    seen = set()
    result = []
    for person in people:
        key = tuple(person_fields(person))
        if key and key not in seen:
            seen.add(key)
            result.append(person)
    return result


def configured_file_hits(paths: list[str], patterns: list[dict[str, Any]]) -> list[dict[str, str]]:
    hits = []
    for path in paths:
        path = path.strip()
        if not path:
            continue
        for item in patterns:
            if item["regex"].search(path):
                hits.append({
                    "path": path,
                    "subtype": item["subtype"],
                    "pattern": item["source_pattern"],
                })
    # Keep exact path/pattern combinations; duplicates are not informative.
    unique = {}
    for hit in hits:
        unique[(hit["path"], hit["subtype"], hit["pattern"])] = hit
    return list(unique.values())


def short_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    reports = read_csv(REPORT)
    candidates = read_csv(AUDIT)
    if not reports:
        raise SystemExit(f"Missing or empty report: {REPORT}")
    if not candidates:
        raise SystemExit(f"Missing or empty audit candidate file: {AUDIT}")

    by_url = {row.get("github_url", ""): row for row in reports}
    author_patterns = load_author_patterns()
    file_patterns = load_file_patterns()
    inventory: list[dict[str, str]] = []
    missing: list[str] = []
    NOTES.mkdir(parents=True, exist_ok=True)

    for candidate in candidates:
        url = candidate.get("github_url", "")
        result = by_url.get(url)
        if result is None:
            missing.append(url)
            continue

        # report paths are relative to code/ in the upstream pipeline output
        repo = (ROOT / "code" / result.get("path", "")).resolve()
        commit_rows = read_csv(repo / "commit_stats_main.csv")
        file_rows = read_csv(repo / "commit_stats_files.csv")
        ignored_rows = read_csv(repo / "tools/tool_ignored_files.csv")
        file_list = [
            line.strip()
            for line in read_text(repo / "files.txt").splitlines()
            if line.strip()
        ]
        gitignore_text = read_text(repo / "tools/_gitignore")

        ai_rows = [
            row for row in commit_rows
            if row.get("auth_type", "").strip() in AI_TYPES
        ]
        human_rows = [
            row for row in commit_rows
            if row.get("auth_type", "").strip() == "Human"
        ]
        bot_rows = [
            row for row in commit_rows
            if row.get("auth_type", "").strip() == "Bot"
        ]
        tool_counts = Counter(
            row.get("tool", "").strip() or "(empty)"
            for row in ai_rows
        )

        ai_commit_evidence = []
        direct_author_count = 0
        coauthor_count = 0
        author_unmatched_count = 0

        for row in ai_rows:
            author = parse_json_cell(row.get("author", ""), {})
            structured_coauthors = parse_json_cell(row.get("co_authors", ""), [])
            if not isinstance(structured_coauthors, list):
                structured_coauthors = []
            trailer_coauthors = message_coauthors(row.get("message", ""))
            all_coauthors = dedupe_people(structured_coauthors + trailer_coauthors)

            author_hits = pattern_hits(person_fields(author), author_patterns)
            coauthor_hits = []
            coauthor_labels = []
            for coauthor in all_coauthors:
                hits = pattern_hits(person_fields(coauthor), author_patterns)
                if hits:
                    coauthor_hits.extend(hits)
                    coauthor_labels.append(person_label(coauthor))

            author_has_match = bool(author_hits)
            coauthor_has_match = bool(coauthor_hits)
            direct_author_count += int(author_has_match)
            coauthor_count += int(coauthor_has_match)
            if not author_has_match and not coauthor_has_match:
                author_unmatched_count += 1

            if author_has_match and coauthor_has_match:
                source = "author_and_coauthor_pattern_match"
            elif author_has_match:
                source = "author_pattern_match"
            elif coauthor_has_match:
                source = "coauthor_pattern_match"
            else:
                source = "AI_label_without_recovered_author_pattern"

            message = (row.get("message", "") or "").replace("\r", "")
            ai_commit_evidence.append({
                "sha": row.get("sha", ""),
                "date": row.get("date", ""),
                "pipeline_auth_type": row.get("auth_type", ""),
                "pipeline_tool": row.get("tool", ""),
                "source_assessment": source,
                "author": person_label(author),
                "author_pattern_matches": author_hits,
                "coauthors": coauthor_labels,
                "coauthor_pattern_matches": list(dict.fromkeys(coauthor_hits)),
                "message_first_line": message.splitlines()[0][:240] if message else "",
            })

        # Exact file-marker matching mirrors the upstream regex behavior.
        listed_file_hits = configured_file_hits(file_list, file_patterns)
        changed_paths = [row.get("path", "") for row in file_rows]
        changed_file_hits = configured_file_hits(changed_paths, file_patterns)

        ignored_matches = []
        tools_dir = repo / "tools"
        if tools_dir.exists():
            for path in sorted(tools_dir.glob("_gitignore_tool_matches_*")):
                for line in read_text(path).splitlines():
                    if line.strip():
                        ignored_matches.append({
                            "source_file": path.name,
                            "matched_entry": line.strip(),
                        })

        group = candidate.get("selection_group", "")
        path_parts = [part for part in url.rstrip("/").split("/") if part]
        owner_repo = path_parts[-2:] if len(path_parts) >= 2 else path_parts
        note_name = "__".join(
            re.sub(r"[^a-z0-9]+", "-", part.lower()) for part in owner_repo
        ) or "repository"
        note_name += ".md"
        note = NOTES / note_name

        note_lines = [
            f"# Evidence inventory: {url}",
            "",
            "> Automated inventory only. This is not a manual audit or independent confirmation of coding-agent use.",
            "",
            "## Pipeline report flags",
            f"- `tool_use`: {result.get('tool_use', '')}",
            f"- `commit_use`: {result.get('commit_use', '')}",
            f"- `ignored_tools`: {result.get('ignored_tools', '')}",
            f"- `adoption_date`: {result.get('adoption_date', '')}",
            f"- Selection group: {group}",
            f"- Existing audit status: {candidate.get('audit_status', '')}",
            "",
            "## Commit statistics",
            f"- Total main-branch commit rows: {len(commit_rows)}",
            f"- Pipeline AI-labelled rows: {len(ai_rows)}",
            f"- Human-labelled rows: {len(human_rows)}",
            f"- Bot-labelled rows: {len(bot_rows)}",
            f"- Pipeline AI tool labels: {dict(tool_counts)}",
            f"- AI rows with author-field pattern match: {direct_author_count}",
            f"- AI rows with co-author-field pattern match: {coauthor_count}",
            f"- AI rows without a recovered author/co-author pattern match: {author_unmatched_count}",
            "",
            "The author/co-author pattern checks above reuse the upstream `authors.csv` expressions. They help locate the likely attribution route; they are not independent validation.",
            "An AI-labelled row without a recovered author match is unresolved. It may reflect PR-derived tagging, serialization differences, or another upstream path; this inventory does not decide which.",
            "",
            "## Configured file-pattern matches in repository file list",
        ]
        if listed_file_hits:
            note_lines.extend(
                f"- `{hit['path']}` — {hit['subtype']} (`{hit['pattern']}`)"
                for hit in listed_file_hits
            )
        else:
            note_lines.append("- None found")
        note_lines += ["", "## Configured file-pattern matches in changed-file records"]
        if changed_file_hits:
            note_lines.extend(
                f"- `{hit['path']}` — {hit['subtype']} (`{hit['pattern']}`)"
                for hit in changed_file_hits
            )
        else:
            note_lines.append("- None found")
        note_lines += [
            "",
            "## `.gitignore` source",
            "```text",
            gitignore_text.strip() or "(not available)",
            "```",
            "",
            "## Pipeline-detected ignored entries",
        ]
        if ignored_matches:
            note_lines.extend(
                f"- `{hit['matched_entry']}` (from `{hit['source_file']}`)"
                for hit in ignored_matches
            )
        else:
            note_lines.append("- None found")
        note_lines += [
            "",
            "## Ignored-file metric rows",
            "```json",
            json.dumps(ignored_rows, ensure_ascii=False, indent=2),
            "```",
            "",
            "## AI-labelled commit records (first 30)",
            "```json",
            json.dumps(ai_commit_evidence[:30], ensure_ascii=False, indent=2),
            "```",
            "",
            "## Review status",
            "- Manual public-source review: not performed by this script.",
            "- Pipeline AI labels, configured-pattern matches, and GitHub traces must be evaluated separately.",
            "- Do not interpret missing markers as proof of non-use.",
        ]
        note.write_text("\n".join(note_lines) + "\n", encoding="utf-8")

        inventory.append({
            "github_url": url,
            "selection_group": group,
            "audit_status": candidate.get("audit_status", ""),
            "directory_exists": str(repo.is_dir()),
            "tool_use": result.get("tool_use", ""),
            "commit_use": result.get("commit_use", ""),
            "ignored_tools": result.get("ignored_tools", ""),
            "commit_rows": str(len(commit_rows)),
            "ai_pipeline_rows": str(len(ai_rows)),
            "human_rows": str(len(human_rows)),
            "bot_rows": str(len(bot_rows)),
            "ai_tool_labels": short_json(dict(tool_counts)),
            "ai_rows_author_pattern_match": str(direct_author_count),
            "ai_rows_coauthor_pattern_match": str(coauthor_count),
            "ai_rows_no_author_pattern_match": str(author_unmatched_count),
            "file_list_pattern_hits": short_json(listed_file_hits),
            "changed_file_pattern_hits": short_json(changed_file_hits),
            "gitignore_detected_entries": short_json(ignored_matches),
            "ignored_file_rows": short_json(ignored_rows),
            "evidence_note": str(note.relative_to(ROOT)),
        })

    if inventory:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(inventory[0]))
            writer.writeheader()
            writer.writerows(inventory)

    print("===== INVENTORY SUMMARY =====")
    print("Candidate rows:", len(candidates))
    print("Inventories created:", len(inventory))
    print("Missing from main report:", len(missing))
    print("Directories present:", sum(row["directory_exists"] == "True" for row in inventory))
    print("Previously reviewed:", sum(bool(row["audit_status"]) for row in inventory))
    print("Author patterns loaded:", len(author_patterns))
    print("File patterns loaded:", len(file_patterns))
    print("\nCSV:", OUT)
    print("Evidence notes:", NOTES)
    for url in missing:
        print("MISSING:", url)


if __name__ == "__main__":
    main()
