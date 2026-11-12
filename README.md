# Coding-Agent Trace Validation

**Status:** Ongoing independent research project — preliminary findings only  
**Started:** October 2026  
**Last updated:** November 12, 2026

**Website:** [Sina Mombeiny](https://sinamombeiny.com/) — [read the full research article](https://sinamombeiny.com/articles/investigating-the-reliability-of-github-traces-for-coding-agent-detection).  
**Research repository:** [SinaMombeiny/Coding-Agent-Trace-Validation](https://github.com/SinaMombeiny/Coding-Agent-Trace-Validation)  
**Research log:** [Source-code review and research update — November 7, 2026](https://github.com/SinaMombeiny/Coding-Agent-Trace-Validation/blob/main/docs/Research-Log-Update-2026-11-07.md)

This project investigates how reliably public GitHub traces can indicate coding-agent use. It builds on the methodology and implementation of Robbes et al., [*Agentic Much? Adoption of Coding Agents on GitHub*](https://dl.acm.org/doi/10.1145/3822180).

The upstream `agent-impact` detector is the subject of this study. This project does not introduce a new detection algorithm or reproduce the original paper's large-scale study.

## Research questions

1. **Signal disagreement:** How often do file-based and commit-based signals disagree?
2. **Evidence quality:** What public evidence supports selected classifications, and where is it ambiguous?
3. **Missed traces:** Are there cases of credible coding-agent use that the pipeline does not detect?
4. **Trace resilience:** How do results change when trace markers are removed or modified in controlled tests?

## Initial results

I ran the published pipeline on **59 repositories** from my GitHub starred list. It produced **56 successful reports** and **3 failed analyses**.

| Pipeline signal | Result |
|---|---:|
| File-based (`tool_use`) | 19 / 56 |
| Commit-based (`commit_use`) | 38 / 56 |
| `.gitignore`-related (`ignored_tools`) | 15 / 56 |
| File/commit disagreement | 23 / 56 |

The 23 disagreements consist of **21 commit-only** and **2 file-only** cases. These are pipeline outputs, not independently verified counts of actual coding-agent use.

A **33-repository review sample** has been prepared: all 23 disagreement cases and 10 controls. The initial two commit-only spot checks have been followed by additional commit- and PR-level reviews. For example, an exact `Co-authored-by: Cursor <cursoragent@cursor.com>` trailer was found in `SagerNet/sing-box`, and six AI-labelled commits in `anthropics/skills` contain explicit Claude co-author trailers. These findings support repository-level adoption, but they do not validate every commit labelled AI by the pipeline. The systematic review is still in progress.

## Current work

- Reviewing the upstream source code to understand author, co-author, pull-request, file, and `.gitignore` signals.
- Preparing repository-level evidence records with `scripts/build_evidence_inventory.py`.
- Manually checking public evidence for selected repositories.
- Checking false-positive risks in the local batch-triage helper and testing a revised read-only v2 helper with synthetic regression cases; validation against the full 33-repository sample remains pending.
- Planning controlled trace-removal and trace-modification tests.

The sample is a personal convenience sample, not a random or representative sample of GitHub. The current results do not establish precision, recall, or which signal is more accurate.

## Repository contents

- `data/` — repository sample list.
- `scripts/summarize_results.py` — summarizes existing pipeline CSV outputs.
- `scripts/build_evidence_inventory.py` — prepares evidence inventories for selected repositories; it does not perform manual validation.
- `results/` — summary outputs from the initial pipeline run.
- `docs/Research-Log-Update-2026-11-07.md` — notes on the earlier source-code review and research progress.
- `batch_audit_v2.py` — revised read-only evidence-triage helper (under validation).
- `tests/test_batch_audit_v2.py` — synthetic regression tests for attribution and data-linking rules.
- `docs/AUDIT_PROTOCOL.md` — evidence categories and manual-review rules for RQ2.
- `docs/RESEARCH_LOG_2026-11-12.md` — dated update on the current source review and audit-helper work.

The evidence-inventory script requires the original local pipeline outputs and `audit/manual_audit_candidates.csv`; it cannot run from a fresh clone without those inputs.

## Next steps

1. Validate the revised v2 helper against the saved outputs for the 33 selected repositories and complete the manual review.
2. Investigate possible missed traces using independent public evidence.
3. Run controlled tests on isolated repository copies or test fixtures.

## References

- **Paper:** [*Agentic Much? Adoption of Coding Agents on GitHub*](https://dl.acm.org/doi/10.1145/3822180)
- **Original implementation:** [labri-progress/agent-impact](https://github.com/labri-progress/agent-impact)
- **Published dataset:** [Zenodo](https://zenodo.org/records/19256968)
