# Investigating the Reliability of GitHub Traces for Coding-Agent Detection

**Oct 15, 2026**  
*Independent research project in progress*  
**Last updated: Nov 7, 2026**

[GitHub repository](https://github.com/SinaMombeiny/Coding-Agent-Trace-Validation)

I chose "Agentic Much? Adoption of Coding Agents on GitHub" because I found its topic interesting and it matches my research interests. Since this is my first independent research project (if it can even be called that), I wanted to start with a published study that provides both a research method and open-source code. My first step was to run the authors' pipeline, understand its outputs, and use the initial results to define the next research questions.

The next steps for this research study are to investigate how reliably public GitHub traces can identify coding-agent adoption, and how detection results change when traces are missing or modified.

Since the initial analysis, I have organized the follow-up work around four questions: how often file-based and commit-based signals disagree (RQ1), what public evidence supports selected classifications (RQ2), whether credible evidence of coding-agent use can be missed by the pipeline (RQ3), and how detection changes when trace markers are removed or modified in controlled copies or test fixtures (RQ4). RQ1 has preliminary descriptive results. I have started the evidence review for RQ2, while RQ3 and RQ4 remain planned work.

#### Sample and execution

I selected repositories from my own GitHub starred list. I expected about 63 repositories, but the GitHub API returned 59. I have not confirmed why the counts differed. The request saved the list to `data/sina-starred.csv`, so the URLs did not appear in the terminal. `wc -l` showed 60 lines, meaning one header and 59 repository URLs. I did not measure the time spent fetching the starred list separately.

I deliberately did not apply the original paper's repository-selection filters before running the pipeline. The authors required at least 10 stars, 5,000 lines of code, 100 commits, and recent activity, and excluded forks. I wanted to include smaller repositories as well, including projects that might not meet those thresholds, so I could explore how the detection pipeline behaves on them. I did not pre-filter my list by these criteria. This was a deliberate choice for an exploratory test, but it means my sample-selection method differs from the original study and is not representative of GitHub as a whole.

I set up Python 3.13 and installed the dependencies for the original project. An early import check failed because I ran it from the wrong working directory. Running it from `code/` fixed the relative-path issue. A one-repository test on [ifixai-ai/iFixAi](https://github.com/ifixai-ai/iFixAi) completed in 40.47 seconds.

I then ran the original `agent-impact` code on all 59 repositories:

```bash
cd ~/Desktop/agent-impact-main/code
python run.py ../data/sina-starred.csv ../data/sina-starred.csv sina-starred-59 --max-workers 2 --output-dir ../temp
```

The local default analysis start date was 1 January 2025. The full run took 1 hour, 54 minutes, and 33 seconds. This was the analysis time, not the time needed to fetch the starred list. At first, the progress indicator stayed at 0%, and CPU and network activity did not seem to show much work. The first task completed after 10 minutes and 12 seconds. The log does not establish what caused the delay, but the run later completed normally.

#### Preliminary results

The run produced 56 successful main-report rows and 3 failures.

| Pipeline signal | Result |
|---|---:|
| File-based signal (`tool_use`) | 19 of 56 |
| Commit-based signal (`commit_use`) | 38 of 56 |
| `.gitignore`-related signal (`ignored_tools`) | 15 of 56 |
| All three flags were false | 16 of 56 |
| File and commit signals disagreed | 23 of 56 |

Of the 23 disagreements, 21 had a commit signal without a file signal, while 2 had a file signal without a commit signal. These are outputs of the published heuristics, not verified counts of actual coding-agent use.

The ratio field had 38 numeric values, with a median of 11.818% and a range from 0.081% to 100%. It measures AI-classified commits divided by AI- plus Human-classified commits, excluding Bot-classified commits. It does not measure the percentage of code written by AI. A blank ratio should not automatically be treated as zero.

I spent additional time reviewing the original source code to understand how these signals are produced. The file-based signal checks repository paths against predefined patterns in `config/patterns/files.csv`. These include coding-agent configuration and instruction files such as `CLAUDE.md`, `.cursor/`, and `AGENTS.md`.

The ignored-file signal follows a separate path. The pipeline checks `.gitignore` entries against configured tool patterns and sets `ignored_tools` when it finds a match. An ignored path such as `.claude/` does not necessarily mean that the directory actually exists in the repository.

For commit attribution, the pipeline checks the main commit author and extracts `Co-authored-by: Name <email>` entries from commit messages. It matches these identities against predefined patterns in `config/patterns/authors.csv`. A general mention of a product in commit-message text is not, by itself, the same as a matching author or co-author attribution.

Commit classification can also come from pull request information. The second pass can be triggered by matching branch names or labels, or by a specific Codex task URL marker in the pull request body. When a branch or label pattern identifies a tool, the tagger can classify the first PR commit as AI and later commits by the same PR author as follow-ups. A body-only trigger does not identify a tool by itself; the tagger then relies on the PR's existing commit-author classifications.

The pipeline handles different pull request merge strategies, including merge commits, squash merges, rebases, partial rebases, and fast-forward merges. It maps pull request commits to commits on the main branch before applying PR-derived classifications. Commits classified as `AI-FOLLOWUP` are treated as AI commits in the final ratio calculation.

I also looked at how the commit ratio is calculated. The pipeline counts commits classified as AI and divides them by the total number of commits classified as AI or Human. Bot-classified commits are excluded. The calculation is performed after the upstream file filter is applied. This is a commit-based ratio, not a measurement of AI-generated lines of code. At the report level, `commit_use` is set when the overall computed commit ratio is positive.

During the source-code review, I noticed three implementation details that need further testing. First, a condition in `tag_commits.py` compares a tag with the string `AI-PR-authored`, while the tagging function returns `(type, tool)` tuples. This appears to be a type mismatch, but I have not tested its effect on the results. Second, file patterns are compiled as regular expressions rather than shell-style globs, so a pattern such as `.copilot-*.md` does not behave like a conventional filename wildcard. Third, pull request merge classifications include confidence values, but the inspected commit-classification code applies available SHA mappings without using confidence as a threshold. I have not measured the effects of these observations, and I have not modified the upstream detection code.

I also prepared a sample of 33 repositories for the manual evidence review:

| Selection group | Repositories |
|---|---:|
| Commit-only | 21 |
| File-only | 2 |
| Both signals true (control group) | 5 |
| Both signals false (control group) | 5 |
| **Total** | **33** |

The control groups were selected using the two main signals, `tool_use` and `commit_use`, with random seed `20261107`. The `ignored_tools` values were mixed among the both-true controls.

To help with this stage, I added a new script called `build_evidence_inventory.py`. It reuses the upstream author and file-pattern expressions and collects information from the existing pipeline outputs, including commit classifications, author and co-author matches, file-list markers, and ignored paths. AI-labelled commits without a recovered author or co-author pattern match are kept unresolved; the script does not automatically assume that they were classified through pull request metadata. The script is intended to organize evidence for manual review, not to provide independent proof of coding-agent use.

I have manually examined two repositories so far. In [Anthropic's claude-plugins-official repository](https://github.com/anthropics/claude-plugins-official), I found a commit message containing `Generated with Claude Code`, as well as a Claude-related co-author attribution. In [victorantos/pdfClaw](https://github.com/victorantos/pdfClaw), several commits included `Co-authored-by: Claude Opus 4.6`.

Both repositories had `tool_use=false`, `commit_use=true`, and `ignored_tools=true`. Their `.gitignore` files contained a `.claude/` entry, while the expected Claude configuration files were absent from the pipeline's file listing. These public commit records support the presence of Claude Code-related activity in the two repositories, but they do not independently verify every commit classified by the pipeline. The remaining 31 candidates have not yet been manually reviewed.

#### Problems and limitations

Three repositories failed: `labri-progress/agent-impact` returned a `git show-ref` subprocess error, `diegosouzapw/OmniRoute` returned a GitHub GraphQL HTTP 502, and `SinaMombeiny/sinamombeiny.github.io`, my personal website repository built with HTML and CSS, had a file-list retrieval error. I have not confirmed the underlying causes. The pilot also contained future timestamps and `-1` values in some ignored-file metrics that need further investigation.

This is a small, self-selected sample. I have not completed the manual evidence review, so disagreement alone cannot show which heuristic is more accurate. The two repositories reviewed so far are initial spot checks and are not enough to evaluate the overall reliability of the detection method. The current results do not establish precision, recall, or false-positive and false-negative rates.

#### Next steps

I will continue reviewing the remaining repositories in the selected 33-repository sample, starting with the cases where the file-based and commit-based signals disagree. I will also examine the selected control repositories, where the signals agree or where neither signal was detected. For each repository, I will record the public evidence behind the classification and note cases where the evidence remains unclear.

For RQ3, I will look for credible public evidence of coding-agent use in repositories where the pipeline did not identify the corresponding signals. Candidate sources will include explicit maintainer statements, issue or pull request discussions, commit-level attributions, and author or tool identities that are not covered by the current `authors.csv` patterns. I will record the exact public source and the relevant commit or pull request for each candidate rather than treating a keyword match as sufficient evidence.

After the manual review, I plan to run controlled tests on isolated repository copies or test fixtures, removing or changing selected trace markers to see how the detection results respond. These experiments will help assess how missing or modified traces affect the pipeline and identify situations where coding-agent use may not be detected.

For everybody who is reading this and reviewing this, thank you for your time!

**Paper:** [Agentic Much? Adoption of Coding Agents on GitHub](https://dl.acm.org/doi/10.1145/3822180)  
**Original code:** [labri-progress/agent-impact](https://github.com/labri-progress/agent-impact)  
**Published dataset:** [Zenodo](https://zenodo.org/records/19256968)
