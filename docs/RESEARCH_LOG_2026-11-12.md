# Research Log Update — November 12, 2026

This note records the additional source-code review, repository-level evidence checks, and audit-helper work completed since the November 7 update. The original `agent-impact` implementation was inspected but not modified. The manual review of the 33-repository sample is still in progress.

## Source-code review

I continued tracing how the upstream pipeline decides which repositories receive commit-level analysis and when it writes the commit-classification files.

### Commit-adoption gate

The function `is_commit_adopter()` in `code/heuristics.py` returns `True` when at least one of the following conditions is met: a pull request has a matching AI-related branch name or label; a pull request contains a commit already classified as AI; or the repository commit list contains an AI-classified commit.

The sampled-repository path in `RepoAnalyzer.do_analysis()` calls `run_commit_analysis_internal([])`. Being selected for sampling does not, by itself, guarantee that commit statistics will be written. Inside that function, `compute_adoption_and_metrics()` runs only when the repository has file-based tool matches or `is_commit_adopter()` returns `True`.

At report level, `commit_use` is set to `True` only when the calculated overall commit ratio is present and greater than zero. Therefore, `sampled=True`, `commit_use=False`, and the absence of `commit_stats_main.csv` can occur together. The absence of that CSV must not be interpreted as evidence that the repository has no commit history or that its commits are human-authored.

### Raw commit records and classified commit statistics

The analyzer writes the retrieved commit history to `commit_list.csv`. It writes `commit_stats_main.csv` and `commit_stats_files.csv` later, after commit classification and metric calculation have been triggered. These files have different meanings: `commit_list.csv` contains raw commit records, while `commit_stats_main.csv` contains the upstream pipeline's author-type and tool classifications.

I also inspected `code/clone_missing_repos.py`. Its fallback for a missing `commit_stats_main.csv` converts records from `commit_list.csv` into `StatSummary` rows with `auth_type="Human"`. This is a convenience step used by that helper script; it is not an independent attribution check. I will not use this fallback output as ground truth or as manually validated evidence in this study.

### Pull-request classification and commit mapping

The inspected `classify_commits_classified_prs()` function first assigns types using commit-level author information, then applies classifications derived from classified pull requests. It uses SHA mappings to transfer PR-derived classifications to main-branch commits when the PR commit SHA is not itself present in the main-branch commit set.

The `is_ai_pr_meta()` function checks the PR branch name and labels. `is_commit_adopter()` also checks for AI-classified commits in PRs and in the repository commit list. This confirms that `commit_use` may depend on PR-derived heuristics as well as direct author or co-author patterns. A pipeline classification is still a detector output; it is not independent proof of coding-agent use.

## Source-code observations requiring tests

The November 7 update recorded three upstream implementation observations that had not been tested. I have continued to keep those observations separate from measured effects. The upstream detection code has not been modified, and I have not measured whether those observations change the 56 successful report rows.

A separate review of the local `batch_audit.py` helper identified two risks in its triage logic:

1. Its Claude pattern uses `\bclaude\b|anthropic\.com` and is applied to author identity text. This can match a human name such as `Stanislas Daniel Claude Dolcini` or `Jean-Claude Joanna`, and an `@anthropic.com` address alone does not establish that an identity is an AI agent. The `KenneyNL/Adobe-Alternatives` result was reset to pending after this false-positive risk was identified.
2. Its PR-number expression accepts both `/pull/123` and a generic `#123` reference. A generic issue reference should not be treated as a verified link to a pull request. A commit-to-PR association should rely on an exact commit SHA or a directly verified PR URL and repository context.

These are weaknesses in the local batch-triage helper, not demonstrated defects in the upstream `agent-impact` detector. They are being addressed separately.

## Evidence-audit preparation

The 33-repository review sample remains the same sample prepared in the November 7 update:

| Selection group | Repositories |
|---|---:|
| Commit-only (`tool_use=false`, `commit_use=true`) | 21 |
| File-only (`tool_use=true`, `commit_use=false`) | 2 |
| Both main signals true (controls) | 5 |
| Both main signals false (controls) | 5 |
| **Total** | **33** |

The controls were selected using `tool_use` and `commit_use` with random seed `20261107`. `ignored_tools` was not used to define the control groups.

The current `audit/manual_audit_candidates.csv` records 9 repositories as `supported`, 1 as `ambiguous`, and 23 as pending. These are the current audit-record statuses, not final study-level accuracy estimates. The 33-repository review has not been completed.

Additional public-source checks recorded since the previous update include:

- `sindresorhus/awesome`: the `codex/` branch name and PR metadata explain why the pipeline raised a commit-related signal, but no explicit public disclosure was found in the reviewed PR. The case remains ambiguous; a branch name alone is not direct confirmation of agent use.
- `hudra0/qosmate`: three Codex-labelled commits were linked to PRs #60, #61, and #64. The reviewed PR #64 included a `codex` label whose public timeline attributed the label addition to ChatGPT Codex Connector. This supports repository-level Codex activity, but it does not independently validate every labelled commit.
- `3b1b/manim`: the repository had 67 Claude Code-labelled commits in the local pipeline output. An independent report described 69 Claude Code-assisted commits in a set of 126, and a sample SHA was matched. This supports repository-level activity; it does not validate all 67 pipeline-labelled commits. Some ignored-file metadata in the local output contained invalid future timestamps and `-1` values, which were not treated as evidence.
- `SagerNet/sing-box`: commit `1beb4cb00234187019d5d64428262ed9e562e26f` contains an explicit `Co-authored-by: Cursor <cursoragent@cursor.com>` trailer. The evidence inventory did not recover the co-author, so the extraction discrepancy is recorded separately from the raw commit evidence.
- `aiwithremy/claude-skills-llm-council`: a raw commit message contains `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`. The extracted `co_authors` field was empty, so the raw trailer and parser output remain separate records.
- `openwrt/openwrt`: the local output contains 29 AI-labelled commits (26 Claude Code and 3 Codex). Multiple Claude co-author trailers were found. The three Codex cases were associated with `codex/` branches but did not have equivalent explicit Codex attribution in the reviewed records; those individual commits remain unconfirmed.
- `dmlc/xgboost`: the local output contains 144 AI-labelled commits (85 Codex, 47 Copilot, and 12 Claude Code). The review found explicit Copilot attribution examples and one Claude attribution example. Many of the Codex classifications appear to be branch-derived and remain unconfirmed at the individual-commit level.
- `anthropics/skills`: six AI-labelled commits in the reviewed sample contain explicit Claude co-author trailers. This supports repository-level adoption, but does not validate every AI-labelled commit. The batch helper also identified direct-trace candidates among commits not labelled AI by the pipeline; those are leads for RQ3 and have not yet been independently reviewed as missed traces.

I also manually reviewed `iina/iina`. The local report contains 642 commit rows and 15 AI-labelled commits (9 Claude Code, 5 Codex, and 1 Cursor), while the repository-level flags are `tool_use=false` and `commit_use=true`. The review found explicit co-author evidence and a PR disclosure, including a separate Codex trailer in a commit associated with a contributor whose name contains “Jean-Claude.” The human name itself is not evidence; the explicit Codex trailer and PR disclosure are the relevant traces. The attempt to record this review in the CSV failed because the update script expected `review_note`, while the actual column is `review_notes`. The manual decision has therefore not yet been saved to `manual_audit_candidates.csv` and must not be counted as a recorded status change.

## Evidence inventory helper

`scripts/build_evidence_inventory.py` continues to be used to organize the existing local pipeline outputs for manual review. It prepares candidate evidence records; it does not independently validate whether a coding agent was used. Missing extraction results, unmatched co-authors, and absent auxiliary files must remain distinguishable from negative evidence.

A read-only v2 batch-triage helper was drafted to address the false-positive risks found in v1. Its intended behavior is to inspect `commit_stats_main.csv` when available and retain `commit_list.csv` as raw, unclassified commit data when classification output is absent. It also uses exact SHA-based PR links rather than treating a generic `#123` reference as a PR association, and it does not update the original audit CSV automatically.

The draft helper was checked with synthetic regression cases, including human names containing “Claude,” explicit co-author trailers, generic email-domain matches, and PR references without a verified SHA link. Those synthetic tests passed in the draft environment. The helper has not yet been run against the complete 33-repository sample, so no v2 repository-level counts or revised RQ2 results are reported here.

## Local output integrity check

I checked the expected evidence files for all 33 selected repositories. The saved local directories contained `files.txt`, `pull_requests/pr_list.csv`, and `pull_requests/pr_commits.csv` for all 33 repositories. `commit_stats_main.csv` and `commit_stats_files.csv` were present for 31 of 33 repositories. The auxiliary `tools/_gitignore` file was present for 27 repositories, and `tools/tool_ignored_files.csv` was present for 10. The absent auxiliary files are not, by themselves, evidence that the corresponding trace was absent from a repository.

The two repositories without the commit-statistics CSVs require different handling:

- `georgd/EB-Garamond`: the saved `commit_list.csv` contained only its header, and the local Git query found no commits on the available refs since the analysis start date, 1 January 2025. The separate PR output contained two PRs and two PR-associated commits dated in 2025; the saved PR rows had blank `merged_at` values. These PR records remain available for review, but they should not be confused with main-branch commits in the observation window.
- `Fox-Fig/slipstream-rust-plus-deploy`: `commit_list.csv` contained 80 raw commit records, all dated on or after 1 January 2025; 61 were reported on `master` since that date. The PR files contained no PR records. The request for a root `.gitignore` returned HTTP 404. The missing classification CSV is therefore not a missing raw-commit history. The 80 raw commits remain unclassified by the saved upstream output and must not be relabelled as Human by the audit helper.

These checks explain why the earlier inventory reported 33 missing expected files: the total included absent auxiliary files as well as the four missing commit-statistics files. It did not mean that 33 repositories were incomplete.

## Next steps

1. Run the revised read-only v2 helper against the saved outputs for all 33 selected repositories. Check the manifest and per-repository evidence rows before using any summaries.
2. Correctly record the `iina/iina` manual review using the existing `review_notes` column, while preserving the current CSV and its backups.
3. Continue the manual review of the pending repositories. Record exact public URLs, commit SHAs, PR numbers, raw evidence, pipeline classifications, decisions, and uncertainty separately.
4. Review the RQ3 candidates from `anthropics/skills` and other repositories before describing any of them as missed traces.
5. Keep the upstream source observations and the local batch-helper defects separate. Test any proposed upstream behavior claims with controlled cases before reporting their effects.
6. Run controlled marker-removal and marker-modification tests on isolated repository copies or fixtures for RQ4.
7. Update the public README and website article with the existing structure and wording retained. Add only the verified progress from this update; do not replace preliminary RQ1 findings or present the incomplete RQ2 audit as a final result.
