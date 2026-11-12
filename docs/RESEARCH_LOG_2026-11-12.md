# Research Log — 12 November 2026

## Project status

This is an independent exploratory follow-up to Robbes et al., *Agentic Much? Adoption of Coding Agents on GitHub* (ACM TOSEM 2026). The initial pipeline run and preliminary RQ1 analysis are complete. RQ2 is in progress; RQ3 has early candidates; RQ4 has not started.

## RQ1 baseline retained

The initial run covered 59 repositories selected from the researcher's GitHub starred list. It produced 56 successful main-report rows and 3 failures. Among the 56 successful rows:

- `tool_use=true`: 19
- `commit_use=true`: 38
- `ignored_tools=true`: 15
- all three false: 16
- file/commit signal disagreement: 23 (21 commit-only and 2 file-only)

The `ratio` field had 38 numeric values, a median of 11.818%, and a range of 0.081%–100%. It is based on AI-classified commits divided by AI- plus Human-classified commits, excluding Bot-classified commits. It is not an AI-generated code percentage.

These are pipeline outputs, not independently verified use counts. The 59-repository sample is self-selected and does not represent GitHub as a whole.

## RQ2 sample and manual review

The manual review sample contains 33 repositories: all 23 discordant repositories, 5 both-main-signals-true controls, and 5 both-main-signals-false controls. Control selection used `tool_use` and `commit_use`, with seed `20261107`; `ignored_tools` did not define the controls.

The current candidate CSV contains statuses, but those counts are not final results. Some earlier status changes came from an automated triage pass and must be distinguished from human-verified decisions.

### Manual evidence review notes

- `sindresorhus/awesome`: retained as ambiguous. The `codex/` branch name and PR #4146 explain a detector clue, but no explicit disclosure was found in the reviewed material.
- `hudra0/qosmate`: repository-level Codex activity has supporting evidence from Codex-labelled commits, PR links, and a PR label applied by the ChatGPT Codex Connector. This does not validate every pipeline-labelled commit individually.
- `3b1b/manim`: repository-level Claude Code activity has supporting traces, including pipeline labels and an external commit-level report with a sampled SHA match. The pipeline's labelled commit count is not assumed to validate every commit.
- `SagerNet/sing-box`: a raw commit message contains `Co-authored-by: Cursor <cursoragent@cursor.com>`. The evidence inventory's extracted `co_authors` field did not recover that trailer; this is an extraction discrepancy to preserve and investigate.
- `aiwithremy/claude-skills-llm-council`: a raw commit message contains a Claude co-author trailer. The inventory's extracted co-author field did not recover it; preserve this discrepancy.
- `openwrt/openwrt`: repository-level Claude Code activity is supported by explicit co-author traces. Some Codex-labelled cases were branch-derived and remain individually unconfirmed.
- `dmlc/xgboost`: repository-level coding-agent activity has explicit Copilot and Claude attribution examples. Many Codex-labelled commits appear to be branch-derived and should not be treated as individually verified.
- `anthropics/skills`: multiple commits contain explicit Claude Code co-author or generated-with traces. The repository-level evidence is strong. Separate non-AI-labelled commit traces are RQ3 candidates, not RQ2 validation.
- `iina/iina`: manual review found direct Codex/Claude-related evidence in selected commit/PR records, including explicit Codex co-author attribution and a PR disclosure. The attempt to save the decision failed because the helper expected `review_note`, while the CSV column is `review_notes`. The CSV therefore did not record that review at the time of this log.

These are working notes from the local terminal review. Exact SHA, PR number, and evidence excerpts still need to be preserved in the manual evidence notes before they are presented as final results.

### Batch Audit v1 limitation

The local `batch_audit.py` helper applied a broad regular expression to full author identity text:

```python
'Claude': re.compile(r'\bclaude\b|anthropic\.com', re.I)
```

This can match human names such as `Stanislas Daniel Claude Dolcini` or `Jean-Claude Joanna`, and it can treat an employee address at `anthropic.com` as agent attribution. Those are not sufficient evidence of coding-agent use.

The problem is in the local batch-triage helper, not evidence that the upstream `agent-impact` detector uses the same author matching rule. Batch v1 recommendations are not treated as final manual audit results.

The helper also attempted to connect PRs using generic `#number` references. Such references can refer to issues as well as PRs, so they do not establish a commit–PR relationship.

## Upstream pipeline behavior inspected on 12 November

Source inspection established the following behavior in the saved upstream implementation:

- `is_commit_adopter` returns true when a PR has an AI-related branch or label, when a PR contains an AI-classified commit, or when a repository commit is AI-classified.
- A sampled repository can enter this check even when no file marker was found.
- `compute_adoption_and_metrics` writes `commit_stats_main.csv` and `commit_stats_files.csv` after the adopter gate is passed.
- `commit_use` is set true only when an `overall` commit ratio is present and greater than zero.

This explains why some repositories can have raw commit or PR records but no `commit_stats_main.csv`. The missing classification file is not evidence that all commits were Human or that the repository had no coding-agent use.

### Two both-false controls with unavailable commit statistics

The local data inventory identified two examples:

**`georgd/EB-Garamond`**

- `commit_list.csv` has a header but no data rows.
- The saved clone has zero commits across available refs since 1 January 2025.
- Two PR records and two PR commit rows are available.
- The saved PR rows have no `merged_at` timestamp or `merge_commit_sha`.
- No commit statistics file was produced.

Interpretation: no eligible repository commit was present in the saved observation window, but the two PR commit records remain part of the review scope. The missing classification is recorded as unavailable, not as Human.

**`Fox-Fig/slipstream-rust-plus-deploy`**

- `commit_list.csv` contains 80 raw commit rows.
- The saved Git references contain 80 commits across refs and 61 commits on `master` since 1 January 2025.
- The saved PR list and PR-commit file contain zero data rows.
- `commit_stats_main.csv` and `commit_stats_files.csv` are absent.
- The upstream log records a 404 response when requesting `.gitignore`.

Interpretation: 80 raw commits are available, but their pipeline classifications are unavailable in the saved stats output. They must not be presumed Human. The missing `.gitignore` response is a data-availability issue, not a negative coding-agent trace.

## V2 development checkpoint

The read-only v2 helper has been revised to address the data structures observed in the 33-repository sample:

- it scans `commit_stats_main.csv` when available for pipeline classification;
- it also scans `commit_list.csv` and `pr_commits.csv` for raw public commit messages;
- a raw commit without a matching pipeline row receives classification `NOT_AVAILABLE`, not `Human`;
- PR-body disclosures are counted only when the PR has an exact `pr_commits.csv` SHA link or an exact `merge_commit_sha` match;
- generic `#123` references are not used as commit–PR links;
- author and committer identity strings are not used for direct attribution;
- direct traces on known Human/Bot rows, AI-labelled rows, AI-FOLLOWUP rows, and unclassified rows are reported separately;
- outputs are written separately from the input CSV and upstream data;
- each run records input hashes in a manifest and does not make network requests.

Fourteen synthetic unit/integration tests pass in the current draft. They include regression checks for human names containing `Claude`, exact agent trailers, raw commit records with unavailable classification, exact PR-SHA linkage, and read-only input behavior. This does not replace validation against the 33 real repositories.

## RQ3 and RQ4

An initial lead was identified in `anthropics/skills`: direct public traces may exist on commits that the pipeline did not label AI. These require exact SHA-level review. A direct trace on a known Human/Bot-labelled commit is a candidate for RQ3; a trace on a commit with no available pipeline classification remains unclassified and is not a confirmed miss.

RQ4 has not started. The planned work is to use isolated copies or fixtures, remove or modify selected trace markers, and rerun the pipeline to measure output changes.

## Limitations and publication rules

- The sample is small and self-selected, not representative of GitHub.
- Public traces are imperfect proxies for actual coding-agent use.
- The current audit is incomplete.
- No precision, recall, false-positive rate, or false-negative rate is reported without an independently justified ground-truth procedure.
- Do not generalize sample proportions to GitHub.
- Keep pipeline classifications, raw public traces, manual decisions, and hypotheses separate.
- Sentinel values such as future timestamps and `-1` metrics are not interpreted as real activity without source-level confirmation.

## Next actions

1. Run the revised v2 helper on all 33 local candidate repositories.
2. Inspect every v2 evidence row against the underlying saved commit or PR record.
3. Correctly record the IINA manual decision using the actual `review_notes` CSV column, after preserving a backup and verifying the exact evidence notes.
4. Review v2 differences from v1, especially the false-positive cases involving human author names and generic PR references.
5. Continue RQ2 manual review; do not convert automated recommendations to human statuses.
6. Review the `anthropics/skills` non-AI-labelled direct traces as RQ3 candidates.
7. Design RQ4 after the trace types and baseline outputs are documented.
