"""Regression tests for the skill scripts. Stdlib only.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parent.parent


def load(rel: str):
    path = REPO / rel
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trace = load("skills/claim-trace/scripts/trace_claims.py")
prose = load("skills/prose-guard/scripts/prose_lint.py")
audit = load("skills/llm-pipeline/scripts/audit_llm_app.py")
scout = load("skills/repo-scout/scripts/repo_scout.py")
stale = load("skills/docs-sync/scripts/stale_docs.py")
thresholds = load("skills/llm-evals/scripts/check_thresholds.py")
readme = load("skills/readme-brand/scripts/check_readme.py")
contract = load("skills/agent-contract/scripts/verify_claude_md.py")
zips = load("scripts/build_zips.py")

EM = "—"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout


class TempRepo:
    """A throwaway git repo with an initial commit on main."""

    def __init__(self, files: dict[str, str]):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        self.write(files)
        self.commit("init")

    def write(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))  # LF as written, on every OS

    def commit(self, message: str) -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def close(self) -> None:
        self._tmp.cleanup()


class InDir:
    def __init__(self, path: Path):
        self.path, self.old = path, None

    def __enter__(self):
        self.old = os.getcwd()
        os.chdir(self.path)

    def __exit__(self, *exc):
        os.chdir(self.old)


# --------------------------------------------------------------------------
# claim-trace
# --------------------------------------------------------------------------

class ClaimTraceTests(unittest.TestCase):
    def index(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "m.csv").write_text(text, encoding="utf-8")
            return trace.artifact_values(Path(tmp))

    def test_positive_value_counted_once(self):
        _, counts, _ = self.index("acc\n0.8473\n")
        self.assertEqual(counts["0.847"], 1)

    def test_negative_value_matches_both_signs_once(self):
        _, counts, _ = self.index("delta\n-0.25\n")
        self.assertEqual(counts["-0.25"], 1)
        self.assertEqual(counts["0.25"], 1)

    def test_percent_matches_fraction(self):
        self.assertIn("0.847", trace.normalize("84.7", percent=True))
        self.assertIn("84.7", trace.normalize("84.7", percent=True))

    def test_percent_precision_counts_toward_min_decimals(self):
        self.assertTrue(trace.is_claim("84.7", True, 2, False))
        self.assertFalse(trace.is_claim("84.7", False, 2, False))

    def test_exponent_precision(self):
        self.assertEqual(trace.decimal_places("1.5e-3"), 4)
        self.assertEqual(trace.decimal_places("0.847"), 3)
        self.assertEqual(trace.decimal_places("12"), 0)

    def test_end_to_end_percent_is_traced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "results").mkdir()
            (root / "results" / "m.csv").write_text("acc\n0.8473\n", encoding="utf-8")
            (root / "paper.md").write_text("Accuracy reached 84.73% overall.\n", encoding="utf-8")
            out = subprocess.run(
                [sys.executable, "-B", str(REPO / "skills/claim-trace/scripts/trace_claims.py"),
                 "paper.md", "--results", "results", "--json"],
                cwd=root, capture_output=True, text=True,
            )
            claims = json.loads(out.stdout)["claims"]
            self.assertEqual([c["status"] for c in claims], ["traced"])
            self.assertEqual(out.returncode, 0)


# --------------------------------------------------------------------------
# prose-guard
# --------------------------------------------------------------------------

class ProseLintTests(unittest.TestCase):
    def rules(self, text: str) -> list[str]:
        return [f.rule for f in prose.check_file(Path("x.md"), text)]

    def test_mentioning_directive_does_not_disable_linting(self):
        text = "Add `<!-- prose-lint: off -->` at the top.\n\nWe delve into it.\n"
        self.assertIn("delve", self.rules(text))

    def test_directive_on_its_own_line_disables(self):
        text = "<!-- prose-lint: off -->\nWe delve into it.\n"
        self.assertNotIn("delve", self.rules(text))

    def test_directive_back_on(self):
        text = "<!-- prose-lint: off -->\nWe delve.\n<!-- prose-lint: on -->\nWe delve.\n"
        self.assertEqual(self.rules(text).count("delve"), 1)

    def test_fix_pair_becomes_commas(self):
        new, n = prose.fix_em_dashes(f"The tool {EM} once tuned {EM} runs fast.\n")
        self.assertEqual(new, "The tool, once tuned, runs fast.\n")
        self.assertEqual(n, 2)

    def test_fix_pair_before_punctuation(self):
        new, _ = prose.fix_em_dashes(f"It works {EM} mostly {EM}.\n")
        self.assertEqual(new, "It works, mostly.\n")

    def test_fix_definition_becomes_colon(self):
        new, n = prose.fix_em_dashes(f"- **Mock lane** {EM} no key needed.\n")
        self.assertEqual(new, "- **Mock lane**: no key needed.\n")
        self.assertEqual(n, 1)

    def test_fix_leaves_code_and_ambiguous_dashes(self):
        text = f"Run `a {EM} b` now.\nIt failed {EM} we rewrote it.\n```\nx {EM} y\n```\n"
        new, n = prose.fix_em_dashes(text)
        self.assertEqual(new, text)
        self.assertEqual(n, 0)

    def test_fix_leaves_lint_off_region(self):
        text = f"<!-- prose-lint: off -->\nThe tool {EM} once tuned {EM} runs.\n"
        self.assertEqual(prose.fix_em_dashes(text)[0], text)


# --------------------------------------------------------------------------
# llm-pipeline audit
# --------------------------------------------------------------------------

class AuditTests(unittest.TestCase):
    def run_audit(self, files: dict[str, str]) -> dict:
        repo = TempRepo(files)
        try:
            return audit.audit(repo.root, None)
        finally:
            repo.close()

    def test_twilio_messages_create_is_not_llm(self):
        result = self.run_audit({"sms.js": "client.messages.create({ body: 'hi', to: n })\n"})
        self.assertEqual(result["llm_files"], [])

    def test_sdk_call_without_import_is_llm(self):
        result = self.run_audit({"ask.py": "r = client.messages.create(model=M, max_tokens=10)\n"})
        self.assertEqual(result["llm_files"], ["ask.py"])

    def test_mentioning_sdk_name_is_not_llm(self):
        result = self.run_audit({"deps.py": 'FRAMEWORKS = {"@anthropic-ai/sdk": "Anthropic SDK"}\n'})
        self.assertEqual(result["llm_files"], [])

    def test_require_and_subpath_imports_count(self):
        result = self.run_audit({
            "a.js": "const A = require('@anthropic-ai/sdk')\n",
            "b.ts": "import { zodOutputFormat } from '@anthropic-ai/sdk/helpers/zod'\n",
        })
        self.assertEqual(result["llm_files"], ["a.js", "b.ts"])

    def test_next_route_without_max_duration_is_flagged(self):
        src = "import Anthropic from '@anthropic-ai/sdk'\nexport async function POST() {}\n"
        result = self.run_audit({"app/api/chat/route.ts": src})
        self.assertIn("no-timeout", [f.rule for f in result["findings"]])

    def test_express_api_dir_is_not_flagged(self):
        src = "import Anthropic from '@anthropic-ai/sdk'\n"
        result = self.run_audit({"server/api/chat.ts": src})
        self.assertNotIn("no-timeout", [f.rule for f in result["findings"]])

    def test_vercel_json_max_duration_counts(self):
        src = "import Anthropic from '@anthropic-ai/sdk'\n"
        result = self.run_audit({"app/api/chat/route.ts": src,
                                 "vercel.json": '{"functions": {"x": {"maxDuration": 60}}}'})
        self.assertNotIn("no-timeout", [f.rule for f in result["findings"]])

    def test_scope_is_not_a_string_prefix(self):
        repo = TempRepo({"apps/server/a.py": "import anthropic\n",
                         "apps/server2/b.py": "import anthropic\n"})
        try:
            result = audit.audit(repo.root, "apps/server")
            self.assertEqual(result["llm_files"], ["apps/server/a.py"])
        finally:
            repo.close()


# --------------------------------------------------------------------------
# Running from a subdirectory
# --------------------------------------------------------------------------

class SubdirectoryTests(unittest.TestCase):
    def setUp(self):
        self.repo = TempRepo({"README.md": "# Demo\n", "src/main.py": "print(1)\n",
                              "src/lib/util.py": "x = 1\n",
                              "CLAUDE.md": "See `src/main.py` and `README.md`.\n"})

    def tearDown(self):
        self.repo.close()

    def test_repo_scout_lists_whole_repo(self):
        with InDir(self.repo.root / "src" / "lib"):
            files = scout.list_files(self.repo.root, None)
        names = sorted(p.relative_to(self.repo.root).as_posix() for p in files)
        self.assertIn("README.md", names)
        self.assertIn("src/main.py", names)

    def test_verify_claude_md_sees_root_paths(self):
        with InDir(self.repo.root / "src"):
            result = contract.audit(self.repo.root / "CLAUDE.md", self.repo.root, 200)
        self.assertEqual(result["dead_paths"], [])
        self.assertEqual(result["shorthand_paths"], [])

    def test_check_readme_all_from_subdir(self):
        with InDir(self.repo.root / "src"):
            out = subprocess.run(
                [sys.executable, "-B", str(REPO / "skills/readme-brand/scripts/check_readme.py"),
                 "--all", "--json"], capture_output=True, text=True)
        files = [Path(r["file"]).name for r in json.loads(out.stdout)]
        self.assertIn("README.md", files)


# --------------------------------------------------------------------------
# docs-sync
# --------------------------------------------------------------------------

class StaleDocsTests(unittest.TestCase):
    def test_base_ignores_changes_made_on_base(self):
        repo = TempRepo({"a.py": "1\n", "b.py": "1\n"})
        try:
            git(repo.root, "switch", "-q", "-c", "feature")
            repo.write({"a.py": "2\n"})
            repo.commit("feature change")
            git(repo.root, "switch", "-q", "main")
            repo.write({"b.py": "2\n"})
            repo.commit("main change")
            git(repo.root, "switch", "-q", "feature")
            changed = stale.changed_files(repo.root, "main", staged=False)
            self.assertEqual(changed, ["a.py"])
        finally:
            repo.close()

    def test_glob(self):
        regex = stale.glob_to_regex("app/api/**")
        self.assertTrue(regex.match("app/api/x/route.ts"))
        self.assertFalse(regex.match("app/web/page.tsx"))


# --------------------------------------------------------------------------
# llm-evals
# --------------------------------------------------------------------------

class ThresholdTests(unittest.TestCase):
    def test_missing_warn_only_metric_warns(self):
        rows = thresholds.evaluate({"accuracy": 0.9},
                                   {"accuracy": {"min": 0.8},
                                    "refusal_rate": {"max": 0.02, "warn_only": True}}, None)
        status = {r["metric"]: r["status"] for r in rows}
        self.assertEqual(status["refusal_rate"], "warn")

    def test_missing_gated_metric_fails(self):
        rows = thresholds.evaluate({}, {"accuracy": {"min": 0.8}}, None)
        self.assertEqual(rows[0]["status"], "missing")

    def test_nested_ungated_metrics_are_listed(self):
        rows = thresholds.evaluate({"quality": {"accuracy": 0.9, "f1": 0.8}},
                                   {"quality.accuracy": {"min": 0.8}}, None)
        ungated = [r["metric"] for r in rows if r["status"] == "ungated"]
        self.assertEqual(ungated, ["quality.f1"])

    def test_baseline_drop(self):
        rows = thresholds.evaluate({"acc": 0.80}, {"acc": {"min": 0.5, "max_drop": 0.03}},
                                   {"acc": 0.85})
        self.assertEqual(rows[0]["status"], "fail")


# --------------------------------------------------------------------------
# readme-brand
# --------------------------------------------------------------------------

class SlugTests(unittest.TestCase):
    def test_github_slug_rules(self):
        self.assertEqual(readme.slugify("Usage & Notes"), "usage--notes")
        self.assertEqual(readme.slugify("`install.py` flags"), "installpy-flags")


# --------------------------------------------------------------------------
# build_zips
# --------------------------------------------------------------------------

class ZipTests(unittest.TestCase):
    def build(self, newline: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "demo"
            skill.mkdir()
            text = "---\nname: demo\n---\nbody\n".replace("\n", newline)
            (skill / "SKILL.md").write_bytes(text.encode())
            return zips.build_bytes(skill)

    def test_line_endings_do_not_change_archive(self):
        self.assertEqual(self.build("\n"), self.build("\r\n"))

    def test_archive_root_is_skill_folder(self):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as fh:
            fh.write(self.build("\n"))
        try:
            with zipfile.ZipFile(fh.name) as archive:
                self.assertEqual(archive.namelist(), ["demo/SKILL.md"])
        finally:
            os.unlink(fh.name)

    def test_committed_zips_are_current(self):
        out = subprocess.run([sys.executable, "-B", str(REPO / "scripts/build_zips.py"), "--check"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
