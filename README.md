# Coding-Agent Trace Validation

**Status:** Ongoing independent research project — preliminary findings only  
**Started:** October 15, 2026  
**Research update:** November 7, 2026

## Research objective

This project investigates how reliably public GitHub repository traces can indicate coding-agent adoption. It builds on the published methodology and implementation by Robbes et al., *Agentic Much? Adoption of Coding Agents on GitHub* (ACM TOSEM, 2026).

The upstream detector is the object of study. This project does not claim to have developed the original detector or reproduced the paper's large-scale study. Pipeline labels are treated as observations to investigate, not as ground truth for actual coding-agent use.

The full research report is available in [`docs/Research-Report-2026-11-07.md`](docs/Research-Report-2026-11-07.md). The same report is published as an article on my personal website.

## Research questions

- **RQ1 — Signal disagreement:** How often do file-based and commit-based detection signals disagree in this selected repository sample?
- **RQ2 — Evidence quality:** What public evidence supports selected classifications, and where does that evidence remain ambiguous?
- **RQ3 — Missed traces:** Are there repositories with credible public evidence of coding-agent use for which the pipeline does not identify the corresponding trace?
- **RQ4 — Trace resilience:** How do detection outcomes change when selected trace markers are removed or altered in controlled repository copies or test fixtures?

RQ1 has preliminary descriptive results. Two initial public-source spot checks have been recorded for RQ2, but the systematic evidence audit is incomplete. RQ3 and RQ4 remain planned work.

## Key findings so far

- The original pipeline was run on **59 self-selected public repositories**. It produced **56 successful report rows** and **3 failed repository analyses**.
- File-based and commit-based signals disagreed in **23 of 56 reports**: 21 commit-only cases and 2 file-only cases.
- A 33-repository evidence-review sample has been prepared: all 23 disagreement cases and 10 controls.
- Two initial commit-only spot checks found public commit attribution consistent with Claude Code use. These spot checks do not validate every AI-labelled commit or establish the overall accuracy of the detector.

## Sample and execution

The sample was drawn from my GitHub starred list. It is a personal convenience sample, not a random or representative sample of GitHub. I did not pre-filter the list using the repository-selection thresholds from the original study.

The original local run used `data/sina-starred.csv` and was launched from the upstream project's `code/` directory:

```bash
cd ~/Desktop/agent-impact-main/code
python run.py ../data/sina-starred.csv ../data/sina-starred.csv sina-starred-59 --max-workers 2 --output-dir ../temp
```

No analysis-date override was supplied. The local upstream parser defaulted to `2025-01-01`. The run used two workers and took **1 hour, 54 minutes, and 33 seconds**. It produced 56 rows in `analysis_report_56.csv` and three failed repository records in `retry_list.csv`.

The repository also contains `data/sample_repositories.csv` as its tracked sample file. The local execution filename (`sina-starred.csv`) and the tracked filename (`sample_repositories.csv`) are different; verify that the tracked file contains the same 59 URLs before treating it as an exact reproduction of the original input.

The three recorded failures were:

- `labri-progress/agent-impact` — Git branch-reference check failure.
- `diegosouzapw/OmniRoute` — GitHub GraphQL HTTP 502.
- `SinaMombeiny/sinamombeiny.github.io` — file-list retrieval failure in my personal HTML/CSS website repository.

The failures are kept separate from the 56 successful report rows. Their underlying causes have not been fully established.

## Preliminary results

All counts below describe the 56 rows in `analysis_report_56.csv`. They are outputs of the upstream pipeline, not independently verified counts of actual coding-agent use.

| Pipeline signal | True | False |
|---|---:|---:|
| `tool_use` — file-based signal | 19 | 37 |
| `commit_use` — commit-based signal | 38 | 18 |
| `ignored_tools` — `.gitignore`-related signal | 15 | 41 |
| All three signals false | 16 | — |
| File-based and commit-based signals disagreed | 23 | — |

The joint signal combinations were:

| `tool_use` | `commit_use` | `ignored_tools` | Repositories |
|---|---|---|---:|
| false | false | false | 16 |
| false | true | false | 14 |
| true | true | false | 9 |
| true | true | true | 8 |
| false | true | true | 7 |
| true | false | false | 2 |

The 23 disagreements split into 21 commit-only cases (`tool_use=false`, `commit_use=true`) and 2 file-only cases (`tool_use=true`, `commit_use=false`).

The `ratio` field contained 38 values. Its median was **11.818%**, with a minimum of **0.081%** and a maximum of **100%**. In the inspected upstream code, this ratio counts commits classified as AI divided by commits classified as AI plus Human. Bot-classified commits are excluded, and the calculation is performed after the upstream file filter. It is a commit-count ratio, not a measure of AI-generated lines or code volume. A blank ratio is not automatically zero.

## What the upstream pipeline measures

The source inspection traced the main detection and measurement path:

- **File-based signal:** Patterns from `config/patterns/files.csv` are compiled as regular expressions and matched against repository paths. `tool_use` is set when file analysis returns matching tool results.
- **Ignored-file signal:** The analyzer separately checks `.gitignore`. `ignored_tools` is set when configured tool patterns match ignored entries. A `.gitignore` entry does not establish that the ignored path exists in the repository tree.
- **Direct commit attribution:** The pipeline checks the commit author and extracts `Co-authored-by: Name <email>` entries from commit messages. The resulting identities are matched against `config/patterns/authors.csv`. A general product reference in commit-message prose is not, by itself, the same as a matching author or co-author attribution.
- **Pull-request-derived attribution:** A second pass can be triggered by matching branch names or labels, or by a specific Codex task URL marker in the PR body. Branch or label patterns can provide a tool classification for the first PR commit and follow-up commits. A body-only trigger does not identify a tool by itself; the tagger falls back to the PR's existing commit-author classifications.
- **Merge mapping:** PR commit SHAs are mapped to main-branch commits for merge, squash, rebase, partial-rebase, and fast-forward cases. PR-derived labels are applied to mapped main-branch commits.
- **Ratio calculation:** `AI-FOLLOWUP` is simplified to `AI` before ratio calculation. The overall commit ratio counts AI-classified commits divided by AI- plus Human-classified commits after the upstream file filter. Bot commits are excluded.
- **Report-level flag:** `commit_use` is set when the overall computed commit ratio is positive.

This means `commit_use=true` does not necessarily mean that every AI-labelled commit has an AI identity in its author or co-author fields. PR-derived attribution is another possible route. The pipeline's own label is not independent evidence of adoption.

## Source-code observations to verify

The code review identified implementation details that need careful interpretation. Their effects on the 56 reports have not yet been measured in controlled tests.

1. In `CommitTagger.maybe_filter_commits_after_first_author()`, the code compares a tag value with the string `AI-PR-authored`. The tagger's declared `TypeTool` values and inspected assignments are tuples such as `("AI", "Claude Code")`. This appears to be a type mismatch, and the intended first-AI-commit trimming branch may not run as written.
2. File patterns are compiled as regular expressions; shell-style wildcard conversion is not performed. For example, `.copilot-*.md` should not be assumed to behave like a conventional filename glob because `*` retains its regular-expression meaning.
3. PR merge classification records a confidence value, but the inspected commit-classification code applies available SHA mappings without using that confidence as a threshold.

These are source-code observations, not measured estimates of false positives, false negatives, or changes in detection accuracy. The upstream detector has not been modified in this project.

## Evidence-audit preparation

A 33-repository candidate set has been prepared:

| Selection group | Repositories |
|---|---:|
| All commit-only cases | 21 |
| Both file-only cases | 2 |
| Both signals true (controls) | 5 |
| Both signals false (controls) | 5 |
| **Total** | **33** |

The control cases were selected using the two main signals, `tool_use` and `commit_use`, with random seed `20261107`. Their `ignored_tools` values are mixed; the both-true group does not mean all three flags are true.

Two initial public-source spot checks (`anthropics/claude-plugins-official` and `victorantos/pdfClaw`) found commit attribution consistent with Claude Code use. This does not validate every AI-labelled commit in either repository, and it is not a completed systematic audit. The remaining 31 candidates still require review.

The updated `scripts/build_evidence_inventory.py` is an automated triage helper. It reuses the upstream author and file-pattern expressions, records author and co-author matches separately, and keeps file-list matches and `.gitignore` matches distinct. An AI-labelled commit without a recovered author/co-author pattern match is recorded as unresolved; the script does not assume that it must have come from PR-derived attribution.

The inventory script reads existing local pipeline outputs and the audit candidate CSV. It does not rerun the upstream pipeline. From the project root, run:

```bash
python3 scripts/build_evidence_inventory.py
```

The expected local inputs include:

- `temp/sina-starred-59/analysis_report_56.csv`
- `audit/manual_audit_candidates.csv`
- The repository analysis directories referenced by the report
- Pattern files under `config/patterns/`

The script writes `audit/evidence_inventory.csv` and per-repository notes under `audit/evidence_notes/`. A fresh clone will need the local analysis outputs and `audit/manual_audit_candidates.csv` before the script can run. Generated inventory files are automated triage outputs, not manually reviewed results.

## Limitations

- The sample is small and self-selected.
- Three of the 59 repository analyses failed.
- File, commit, and PR traces are imperfect proxies for actual agent use.
- PR metadata can cause inferred commit labels.
- A `.gitignore` match does not prove that the ignored file or directory exists.
- Absence of a marker does not prove absence of agent use.
- Presence of a marker or author string does not prove that an agent generated the code under study.
- Manual evidence validation and controlled trace-resilience tests are incomplete.
- The current results do not estimate precision, recall, false-positive rates, or false-negative rates, and do not establish which upstream signal is more accurate.

## Next steps

1. Complete the evidence-review protocol and manually review the 33 selected cases, preserving exact public URLs, commit SHAs, file paths, review decisions, and uncertainty.
2. Investigate AI-labelled commits with no recovered direct author/co-author pattern match, including whether PR-derived labels explain the classification.
3. For RQ3, start with repositories where all three pipeline flags are false and look for credible independent public evidence, such as maintainer statements, issue or PR discussions, commit-level attributions, and tool or author identities not covered by the current author patterns. Record the exact source, commit or PR, date, and signal that was missed.
4. Run controlled marker-removal and marker-modification tests on isolated repository copies or fixtures, never on upstream repositories.
5. Update the reported results only after the audit and controlled tests are complete.

## Repository contents

- `data/sample_repositories.csv` — repository list currently tracked in this repository. The original local run used the filename `data/sina-starred.csv`; verify the two lists match before claiming they are identical.
- `audit/manual_audit_candidates.csv` — selected 33-repository review sample; required by the inventory helper.
- `scripts/summarize_results.py` — helper that summarizes existing pipeline CSV outputs; it does not perform coding-agent detection.
- `scripts/build_evidence_inventory.py` — automated evidence-inventory helper for the selected audit candidates.
- `docs/Research-Report-2026-11-07.md` — full report mirrored in the website article.
- `docs/Research-Log-Update-2026-11-07.md` — source-inspection and research-status addendum.
- `results/repository_summary.csv`, `results/summary.json`, and `results/failed_repositories.csv` — summary outputs produced by `summarize_results.py`, when included in the repository.

Generated files such as `audit/evidence_inventory.csv` and `audit/evidence_notes/` are produced locally by the inventory script and should be treated as automated triage outputs, not manually reviewed results.

## Summarizing existing results

After running the upstream pipeline, the existing results can be summarized with:

```bash
python3 scripts/summarize_results.py \
  /path/to/analysis_report_56.csv \
  /path/to/retry_list.csv \
  results
```

This helper processes existing CSV output. It does not rerun repository mining or implement the upstream detection heuristics.

## Attribution

Robbes, R., Matricon, T., Degueule, T., Hora, A., & Zacchiroli, S. *Agentic Much? Adoption of Coding Agents on GitHub.*

- Paper: https://arxiv.org/abs/2601.18341
- Original implementation: https://github.com/labri-progress/agent-impact
- Published dataset: https://zenodo.org/records/19256968
- DOI: https://doi.org/10.1145/3822180

The original research methodology and upstream detector are credited to their authors. This repository documents an independent exploratory analysis and follow-up validation work; it does not claim to introduce a new detection algorithm.
