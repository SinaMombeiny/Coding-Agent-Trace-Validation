import csv
import json
import sys
from pathlib import Path
from collections import Counter
from statistics import median

report, retry, output = map(Path, sys.argv[1:])
output.mkdir(parents=True, exist_ok=True)

def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

rows = read_csv(report)
failures = read_csv(retry)

if not rows:
    raise SystemExit("ERROR: The analysis report is empty.")

fields = [
    "github_url", "tool_use", "commit_use", "ignored_tools",
    "adoption_date", "ratio", "adoption_ratio", "recent_ratio",
    "since_adoption_commits", "recent_commits", "duration"
]
fields = [f for f in fields if f in rows[0]]

with (output / "repository_summary.csv").open(
    "w", encoding="utf-8", newline=""
) as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows({k: r.get(k, "") for k in fields} for r in rows)

def counts(field):
    return {
        value: sum(r.get(field, "").lower() == value for r in rows)
        for value in ("true", "false")
    }

combinations = Counter(
    tuple(r.get(k, "").lower() for k in
          ("tool_use", "commit_use", "ignored_tools"))
    for r in rows
)

ratios = []
for r in rows:
    try:
        if r.get("ratio", "").strip():
            ratios.append(float(r["ratio"]))
    except ValueError:
        pass

summary = {
    "successful_report_rows": len(rows),
    "failed_repositories": len(failures),
    "tool_use": counts("tool_use"),
    "commit_use": counts("commit_use"),
    "ignored_tools": counts("ignored_tools"),
    "signal_combinations": [
        {"signals": list(k), "count": v}
        for k, v in combinations.most_common()
    ],
    "file_commit_signal_disagreements": sum(
        r.get("tool_use", "").lower() !=
        r.get("commit_use", "").lower()
        for r in rows
    ),
    "ratio": {
        "count": len(ratios),
        "median": median(ratios) if ratios else None,
        "minimum": min(ratios) if ratios else None,
        "maximum": max(ratios) if ratios else None
    }
}

(output / "summary.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)

with (output / "failed_repositories.csv").open(
    "w", encoding="utf-8", newline=""
) as f:
    writer = csv.DictWriter(
        f, fieldnames=["github_url", "failure_category"]
    )
    writer.writeheader()
    for r in failures:
        error = r.get("error", "")
        if "502 Server Error" in error:
            category = "GitHub API HTTP 502"
        elif "git show-ref" in error:
            category = "Git branch reference check failed"
        elif "failed to get file list" in error:
            category = "Repository file-list retrieval failed"
        else:
            category = "Other analysis error"
        writer.writerow({
            "github_url": r.get("github_url", ""),
            "failure_category": category
        })

print(json.dumps(summary, indent=2))
print("\nSummary files created successfully.")
