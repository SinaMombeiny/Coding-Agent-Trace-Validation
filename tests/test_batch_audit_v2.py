import csv
import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "batch_audit_v2.py"
spec = importlib.util.spec_from_file_location("batch_audit_v2", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class StrictAttributionTests(unittest.TestCase):
    def test_human_name_with_claude_is_not_direct_evidence(self):
        self.assertIsNone(mod.exact_trailer_tool("Stanislas Daniel Claude Dolcini <stanislas@example.com>"))

    def test_jean_claude_is_not_a_claude_agent_identity(self):
        self.assertIsNone(mod.exact_trailer_tool("Jean-Claude <jjoanna@example.com>"))

    def test_exact_claude_trailer_is_detected(self):
        found = mod.explicit_message_evidence(
            "Fix a bug\n\nCo-authored-by: Claude Opus 4.7 <noreply@anthropic.com>"
        )
        self.assertTrue(any(x[0] == "Claude Code" and x[1] == "exact_agent_coauthor_trailer" for x in found))

    def test_exact_codex_trailer_is_detected(self):
        found = mod.explicit_message_evidence(
            "Change docs\n\nCo-authored-by: Codex <noreply@openai.com>"
        )
        self.assertTrue(any(x[0] == "Codex" and x[1] == "exact_agent_coauthor_trailer" for x in found))

    def test_exact_cursor_trailer_is_detected(self):
        found = mod.explicit_message_evidence(
            "Update plugin list\n\nCo-authored-by: Cursor <cursoragent@cursor.com>"
        )
        self.assertTrue(any(x[0] == "Cursor" for x in found))

    def test_generated_with_claude_code_is_detected(self):
        found = mod.explicit_message_evidence("🤖 Generated with Claude Code")
        self.assertTrue(any(x[0] == "Claude Code" for x in found))

    def test_anthropic_domain_alone_is_not_enough(self):
        self.assertIsNone(mod.exact_trailer_tool("Octavian Guzu <oct@anthropic.com>"))

    def test_generic_issue_reference_is_not_a_pr_link(self):
        mapping = mod.build_commit_to_pr_map([{"sha": "abc123", "pr_number": "45"}])
        self.assertNotIn("123", mapping)
        self.assertEqual(mapping["abc123"], {"45"})

    def test_weak_branch_and_label_clues_are_not_direct(self):
        pr = {"branch_name": "codex/update-docs", "labels": '[{"name":"codex"}]'}
        self.assertTrue(mod.weak_pr_clues(pr))
        self.assertEqual(mod.explicit_message_evidence("Branch: codex/update-docs"), [])

    def _write_csv(self, path, fields, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_full_run_is_read_only_and_uses_exact_sha_pr_link(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "code/org/sample-repo"
            (repo / "pull_requests").mkdir(parents=True)
            self._write_csv(root / "audit/manual_audit_candidates.csv",
                ["github_url", "selection_group", "tool_use", "commit_use", "ignored_tools", "audit_status"],
                [{"github_url": "https://github.com/org/sample-repo", "selection_group": "commit_only", "tool_use": "False", "commit_use": "True", "ignored_tools": "False", "audit_status": "pending"}])
            self._write_csv(root / "temp/sina-starred-59/analysis_report_56.csv",
                ["github_url", "path"],
                [{"github_url": "https://github.com/org/sample-repo", "path": "org/sample-repo"}])
            self._write_csv(repo / "commit_stats_main.csv",
                ["sha", "auth_type", "tool", "author", "message"],
                [{"sha": "abc123", "auth_type": "AI", "tool": "Claude_Code", "author": "Stanislas Daniel Claude Dolcini", "message": "Fix docs\n\nCo-authored-by: Claude Opus <noreply@anthropic.com>"}])
            self._write_csv(repo / "pull_requests/pr_list.csv",
                ["number", "merge_commit_sha", "bodyText", "branch_name", "labels", "merged_at"],
                [{"number": "12", "merge_commit_sha": "", "bodyText": "Generated with Claude Code", "branch_name": "codex/update-docs", "labels": "[]", "merged_at": "2026-11-01T00:00:00Z"}])
            self._write_csv(repo / "pull_requests/pr_commits.csv",
                ["sha", "author", "co_authors", "message", "date", "pr_number"],
                [{"sha": "abc123", "pr_number": "12", "message": "Fix docs"}])
            self._write_csv(root / "audit/evidence_inventory.csv",
                ["github_url", "file_markers", "gitignore_matches"],
                [{"github_url": "https://github.com/org/sample-repo", "file_markers": "[]", "gitignore_matches": "[]"}])

            candidates = root / "audit/manual_audit_candidates.csv"
            before = hashlib.sha256(candidates.read_bytes()).hexdigest()
            rc = mod.main(["--root", str(root)])
            after = hashlib.sha256(candidates.read_bytes()).hexdigest()
            self.assertEqual(rc, 0)
            self.assertEqual(before, after)
            out = root / "audit/v2_outputs"
            with (out / "batch_audit_v2_summary.csv").open(encoding="utf-8-sig", newline="") as h:
                summary = list(csv.DictReader(h))[0]
            self.assertEqual(summary["repo_level_evidence_recommendation"], "supported_candidate")
            self.assertEqual(summary["direct_attribution_ai_labeled_shas"], "1")
            self.assertEqual(summary["linked_prs_with_explicit_disclosure"], "1")

    def test_missing_commit_stats_scans_raw_commit_list_without_assuming_human(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "code/org/raw-only"
            (repo / "pull_requests").mkdir(parents=True)
            self._write_csv(root / "audit/manual_audit_candidates.csv",
                ["github_url", "selection_group", "audit_status"],
                [{"github_url": "https://github.com/org/raw-only", "selection_group": "both_false_control", "audit_status": "pending"}])
            self._write_csv(root / "temp/sina-starred-59/analysis_report_56.csv",
                ["github_url", "path"],
                [{"github_url": "https://github.com/org/raw-only", "path": "org/raw-only"}])
            self._write_csv(repo / "commit_list.csv",
                ["sha", "author", "co_authors", "message", "date"],
                [{"sha": "raw123", "author": "{human}", "co_authors": "[]", "message": "Fix docs\n\nCo-authored-by: Codex <noreply@openai.com>", "date": "2026-02-01"}])
            self._write_csv(repo / "pull_requests/pr_list.csv",
                ["number", "merge_commit_sha", "bodyText", "branch_name", "labels"], [])
            self._write_csv(repo / "pull_requests/pr_commits.csv",
                ["sha", "pr_number"], [])
            before = hashlib.sha256((root / "audit/manual_audit_candidates.csv").read_bytes()).hexdigest()
            rc = mod.main(["--root", str(root)])
            self.assertEqual(rc, 0)
            after = hashlib.sha256((root / "audit/manual_audit_candidates.csv").read_bytes()).hexdigest()
            self.assertEqual(before, after)
            with (root / "audit/v2_outputs/batch_audit_v2_summary.csv").open(encoding="utf-8-sig", newline="") as h:
                summary = list(csv.DictReader(h))[0]
            self.assertEqual(summary["classification_availability"], "not_available")
            self.assertEqual(summary["raw_commit_list_rows"], "1")
            self.assertEqual(summary["direct_attribution_commit_shas"], "1")
            self.assertEqual(summary["direct_attribution_unclassified_shas"], "1")
            self.assertEqual(summary["direct_attribution_human_or_bot_labeled_shas"], "0")
            self.assertEqual(summary["repo_level_evidence_recommendation"], "supported_candidate")


    def test_pr_disclosure_with_exact_sha_link_is_kept_when_stats_are_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "code/org/pr-only"
            (repo / "pull_requests").mkdir(parents=True)
            self._write_csv(root / "audit/manual_audit_candidates.csv", ["github_url", "audit_status"],
                [{"github_url": "https://github.com/org/pr-only", "audit_status": "pending"}])
            self._write_csv(root / "temp/sina-starred-59/analysis_report_56.csv", ["github_url", "path"],
                [{"github_url": "https://github.com/org/pr-only", "path": "org/pr-only"}])
            self._write_csv(repo / "commit_list.csv", ["sha", "message"], [])
            self._write_csv(repo / "pull_requests/pr_list.csv",
                ["number", "bodyText", "merge_commit_sha", "merged_at"],
                [{"number": "33", "bodyText": "Generated with Cursor", "merge_commit_sha": "", "merged_at": ""}])
            self._write_csv(repo / "pull_requests/pr_commits.csv", ["sha", "pr_number", "message"],
                [{"sha": "prsha33", "pr_number": "33", "message": "Add component"}])
            rc = mod.main(["--root", str(root)])
            self.assertEqual(rc, 0)
            with (root / "audit/v2_outputs/batch_audit_v2_summary.csv").open(encoding="utf-8-sig", newline="") as h:
                summary = list(csv.DictReader(h))[0]
            self.assertEqual(summary["classification_availability"], "not_available")
            self.assertEqual(summary["linked_prs_with_explicit_disclosure"], "1")
            self.assertEqual(summary["linked_pr_disclosure_prs_with_unclassified_commit"], "1")
            self.assertEqual(summary["repo_level_evidence_recommendation"], "supported_candidate")

    def test_direct_trace_in_pr_commit_file_is_scanned_when_other_commit_files_are_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "code/org/pr-commit-only"
            (repo / "pull_requests").mkdir(parents=True)
            self._write_csv(root / "audit/manual_audit_candidates.csv", ["github_url", "audit_status"],
                [{"github_url": "https://github.com/org/pr-commit-only", "audit_status": "pending"}])
            self._write_csv(root / "temp/sina-starred-59/analysis_report_56.csv", ["github_url", "path"],
                [{"github_url": "https://github.com/org/pr-commit-only", "path": "org/pr-commit-only"}])
            self._write_csv(repo / "pull_requests/pr_list.csv", ["number", "bodyText"], [])
            self._write_csv(repo / "pull_requests/pr_commits.csv",
                ["sha", "pr_number", "message"],
                [{"sha": "prsha88", "pr_number": "88", "message": "Fix\n\nCo-authored-by: Codex <noreply@openai.com>"}])
            rc = mod.main(["--root", str(root)])
            self.assertEqual(rc, 0)
            with (root / "audit/v2_outputs/batch_audit_v2_summary.csv").open(encoding="utf-8-sig", newline="") as h:
                summary = list(csv.DictReader(h))[0]
            self.assertEqual(summary["direct_attribution_commit_shas"], "1")
            self.assertEqual(summary["direct_attribution_unclassified_shas"], "1")
            self.assertEqual(summary["repo_level_evidence_recommendation"], "supported_candidate")

    def test_pr_disclosure_without_exact_commit_link_is_not_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "code/org/unlinked"
            (repo / "pull_requests").mkdir(parents=True)
            self._write_csv(root / "audit/manual_audit_candidates.csv", ["github_url", "audit_status"],
                [{"github_url": "https://github.com/org/unlinked", "audit_status": "pending"}])
            self._write_csv(root / "temp/sina-starred-59/analysis_report_56.csv", ["github_url", "path"],
                [{"github_url": "https://github.com/org/unlinked", "path": "org/unlinked"}])
            self._write_csv(repo / "commit_stats_main.csv", ["sha", "auth_type", "message"], [])
            self._write_csv(repo / "pull_requests/pr_list.csv", ["number", "bodyText", "branch_name", "labels"],
                [{"number": "7", "bodyText": "Generated with Claude Code", "branch_name": "feature/docs", "labels": "[]"}])
            self._write_csv(repo / "pull_requests/pr_commits.csv", ["sha", "pr_number"], [])
            rc = mod.main(["--root", str(root)])
            self.assertEqual(rc, 0)
            with (root / "audit/v2_outputs/batch_audit_v2_summary.csv").open(encoding="utf-8-sig", newline="") as h:
                summary = list(csv.DictReader(h))[0]
            self.assertEqual(summary["linked_prs_with_explicit_disclosure"], "0")
            self.assertEqual(summary["repo_level_evidence_recommendation"], "manual_review")


if __name__ == "__main__":
    unittest.main(verbosity=2)
