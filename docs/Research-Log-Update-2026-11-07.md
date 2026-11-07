# Research Log Update — November 7, 2026

This note records the source-code review and evidence-audit preparation completed after the initial pipeline run. The original `agent-impact` implementation was inspected but not modified.

## Source-code review

I traced how the upstream pipeline produces its file-based, ignored-file, and commit-based signals.

### File-based and ignored-file signals

The file-based detector loads patterns from `config/patterns/files.csv`, compiles them as regular expressions, and matches them against repository paths. The `tool_use` flag is set when file analysis returns tool matches.

The analyzer separately reads `.gitignore` entries. A matching ignored path sets `ignored_tools`, but this does not establish that the ignored path exists in the repository tree.

### Direct commit attribution

The commit classifier checks the main commit author and extracts co-author identities from `Co-authored-by: Name <email>` entries in commit messages. These identities are matched against `config/patterns/authors.csv`.

A product name appearing in ordinary commit-message prose is not equivalent to a matching author or co-author identity.

### Pull-request-derived attribution

The tagger can perform a second pass when pull-request branch names or labels match configured AI patterns. A specific Codex task URL marker in a PR body can also trigger the second pass. The body marker does not identify the tool by itself; the tagger then relies on the PR's existing author classifications.

When branch or label metadata provides a tool classification, the tagger can assign an AI classification to the first PR commit and follow-up classifications to later commits by the same PR author.

### Merge mapping and ratios

The pipeline classifies PR merge strategies and maps PR commit SHAs to main-branch commit SHAs. The inspected code covers merge, squash, rebase, partial-rebase, and fast-forward cases.

`AI-FOLLOWUP` classifications are simplified to `AI` before ratio calculation. The overall commit ratio counts AI-classified commits divided by AI- plus Human-classified commits; Bot commits are excluded. The upstream file filter is applied before this calculation. At report level, `commit_use` is set when the overall commit ratio is positive.

This means that `commit_use=true` can result from PR-derived attribution as well as direct author or co-author matching. The pipeline's own classification is therefore not independent evidence that an agent was used.

## Source-code observations requiring tests

Three implementation details were noted. Their effects on the 56 successful repository reports have not been measured.

1. In `CommitTagger.maybe_filter_commits_after_first_author()`, the code compares a tag value with the string `AI-PR-authored`, while the inspected tag assignments use `TypeTool` tuples such as `("AI", "Claude Code")`. This appears to be a type mismatch. The practical effect has not been tested.
2. File patterns are compiled as regular expressions; shell-style wildcard conversion is not performed. The pattern `.copilot-*.md` therefore does not behave like a conventional filename glob.
3. PR merge classification records a confidence value, but the inspected commit-classification function applies available SHA mappings without using confidence as a threshold.

These remain source-code observations. The upstream detector was not modified, and no conclusion has been drawn about the impact of these details on detection accuracy.

## Evidence-audit preparation

A 33-repository candidate set was prepared from the 56 successful report rows:

| Selection group | Repositories |
|---|---:|
| Commit-only (`tool_use=false`, `commit_use=true`) | 21 |
| File-only (`tool_use=true`, `commit_use=false`) | 2 |
| Both main signals true (controls) | 5 |
| Both main signals false (controls) | 5 |
| **Total** | **33** |

The five controls in each group were selected using the two main signals, `tool_use` and `commit_use`, with random seed `20261107`. `ignored_tools` was not used to define these control groups, so its values are mixed among the both-true controls.

Two initial public-source spot checks were recorded:

- `anthropics/claude-plugins-official`: the inspected commit history included a `Generated with Claude Code` message and a Claude-related co-author attribution.
- `victorantos/pdfClaw`: several inspected commits included `Co-authored-by: Claude Opus 4.6`.

Both repositories had `tool_use=false`, `commit_use=true`, and `ignored_tools=true`. These spot checks support the presence of Claude Code-related activity in the inspected repositories, but they do not verify every AI-labelled commit. The remaining 31 candidates have not been manually reviewed.

## Evidence inventory helper

The updated `scripts/build_evidence_inventory.py` is an automated triage helper. It reuses the upstream author and file-pattern expressions, records author and co-author matches separately, and keeps file-list matches distinct from `.gitignore` matches.

An AI-labelled commit for which the helper cannot recover a matching author or co-author pattern is recorded as unresolved. The helper does not automatically assume that such a classification came from PR metadata.

The script reads existing local pipeline output and `audit/manual_audit_candidates.csv`; it does not rerun the upstream pipeline. It also requires the repository analysis directories referenced by the report and the pattern files under `config/patterns/`. A fresh clone does not contain all of these local analysis outputs unless they are supplied separately.

The generated `audit/evidence_inventory.csv` and `audit/evidence_notes/` files are triage outputs. They are not manual validation.

## Next steps

1. Complete the manual review of the 33 selected repositories and record exact public URLs, commit SHAs, file paths, decisions, and uncertainty.
2. Investigate AI-labelled commits without a recovered author or co-author pattern match, including whether PR-derived attribution explains their classification.
3. For missed-trace candidates, start with repositories where all three pipeline flags are false and look for independent public evidence such as maintainer statements, issue or PR discussions, commit attributions, and tool or author identities absent from the current author patterns.
4. Run controlled marker-removal and marker-modification tests on isolated repository copies or fixtures.
5. Update the reported findings only after the manual audit and controlled tests are complete.
