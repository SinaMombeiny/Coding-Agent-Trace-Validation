# Research Log Update — 7 November 2026

**Project:** Investigating the Reliability of GitHub Traces for Coding-Agent Detection  
**Status:** Pipeline-output analysis and source-code inspection completed; manual evidence audit remains in progress.

## Research-question structure

The research questions are now standardized across the README and research log:

- **RQ1 — Signal disagreement:** How often do file-based and commit-based detection signals disagree in this selected repository sample?
- **RQ2 — Evidence quality:** What public evidence supports selected classifications, and where does that evidence remain ambiguous?
- **RQ3 — Missed traces:** Are there repositories with credible public evidence of coding-agent use for which the pipeline does not identify the corresponding trace?
- **RQ4 — Trace resilience:** How do detection outcomes change when selected trace markers are removed or altered in controlled repository copies or test fixtures?

RQ1 has a preliminary descriptive result. RQ2–RQ4 remain open.

## Source-code inspection

The upstream implementation was inspected locally without modifying its detection logic.

### File and ignored-file signals

- `code/repo_analyzer.py` calls file analysis and sets `tool_use=True` when the resulting `tool_results` collection is nonempty.
- The same analyzer separately scans `.gitignore` and sets `ignored_tools=True` when configured patterns match ignored entries.
- File patterns come from `config/patterns/files.csv` and are compiled as regular expressions by `code/heuristics.py`.

A `.gitignore` match is therefore a separate trace. It does not establish that the matched directory or file exists in the repository tree.

### Direct commit attribution

`code/heuristics.py` checks the commit's author and extracts co-authors from commit messages with this format:

`Co-authored-by: Name <email>`

The resulting author identity is matched against `config/patterns/authors.csv`. A general product reference in a commit-message body is not, by itself, the same as a matching author or co-author attribution.

### PR-derived attribution

The commit tagger has a second route. When no direct AI-authored commit is found in a PR, matching PR branch names or labels (and a specific PR-body marker) can cause the first PR commit to receive an AI label; later commits can receive follow-up labels.

`code/pr_merge_types.py` maps PR commit SHAs to main-branch commit SHAs:
- merge and fast-forward cases can use identity mappings;
- squash mapping sends PR commit SHAs to the squash commit SHA;
- rebase mapping compares commit messages and author email addresses;
- partial rebase can map only some PR commits.

`code/compute_metrics.py` applies PR tags to mapped main-branch commits. The mapping's `confidence` is retained in the classified-PR object, but the inspected tagging application does not use that value as a filter.

This inspection establishes that the pipeline's `commit_use` is a derived signal that may include PR-inferred commit labels. It is not independent proof of coding-agent use.

### Ratio calculation

Before calculating ratios, the upstream code simplifies `AI-FOLLOWUP` to `AI`. The overall commit ratio counts commits classified as AI divided by the sum of commits classified as AI and Human. Bot commits are excluded. The main analysis also applies the upstream file filter before ratio calculation. The ratio does not measure AI-generated lines.

At report level, `commit_use` is set when the overall commit ratio is positive. A missing ratio should not be converted to zero automatically.

## Implementation observations for later verification

Two source-level details need to be retained in the limitations and tested before making claims about their effect:

1. `CommitTagger.maybe_filter_commits_after_first_author()` tests whether `tags.get(c.sha) == 'AI-PR-authored'`. However, the declared `TypeTool` is a tuple of `(AuthorType, tool_name)`, and the inspected tagger returns tuple values. The comparison appears inconsistent and may leave the intended first-AI-commit trimming branch inactive.
2. The file pattern loader compiles configured patterns as regular expressions; it does not convert shell-style wildcards to regular expressions. Therefore, `.copilot-*.md` should not be assumed to behave like a conventional filename glob.

These are source-code observations. No controlled test has yet quantified their effects on the current sample.

## Audit inventory preparation

The audit candidate set contains 33 repositories:
- 21 commit-only disagreements;
- 2 file-only disagreements;
- 5 both-true controls (`tool_use=true`, `commit_use=true`);
- 5 both-false controls (`tool_use=false`, `commit_use=false`).

The both-true control group is not a group in which all three flags are true; `ignored_tools` is mixed in this selection.

Two initial public-source spot checks have been marked `supported`. A systematic audit has not been completed. The automated inventory for all 33 cases is a triage aid and must not be described as 33 manually verified repositories.

The first inventory script used a broad keyword expression over commit messages. That count was noisy because product names and discussion terms can occur without indicating agent authorship. The replacement script removes the general keyword count and instead:
- reuses the upstream author-pattern expressions against serialized author and co-author fields;
- separately records pipeline AI labels with no recovered author-pattern match as unresolved;
- applies the upstream file-pattern regex behavior to the repository file list and changed-file records;
- keeps `.gitignore` matches and ignored-file metric rows separate;
- labels all results as automated inventory, not independent confirmation.

The inventory script does not infer that an unmatched AI row definitely came from PR metadata. Such a row is unresolved and requires review of the PR path or other supporting output.

## Current evidence and next work

The existing 56-row report still gives these preliminary results:

| Signal | True |
|---|---:|
| `tool_use` | 19/56 |
| `commit_use` | 38/56 |
| `ignored_tools` | 15/56 |
| File/commit disagreement | 23/56 (21 commit-only; 2 file-only) |

Two initial spot checks of commit-only cases found public traces supporting Claude Code use, but this does not establish the accuracy of the heuristic across the remaining candidates or the full sample.

The next work session should begin with the manual evidence protocol and the 33-candidate table. For each repository, record the exact public artifact (file path, commit SHA, PR URL, or `.gitignore` entry), what it supports, what it does not support, the review decision, and uncertainty. Keep the original pipeline CSVs unchanged.

After manual review, proceed to missed-trace cases and controlled marker-removal experiments on isolated copies or test fixtures. Do not report precision, recall, false-positive rates, or false-negative rates until a defensible reference-label procedure exists.
