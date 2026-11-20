#!/usr/bin/env python3
"""test_check_env.py: scripts/check-env.py against fixture environment files and a one-commit git fixture, one finding class a test.

Run from the top-level shell: python scripts/tests/test_check_env.py
"""
import importlib.util
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_env", ROOT / "scripts/check-env.py")
check_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_env)

PROD = """# prod
# --- runtime
HF_HUB_OFFLINE=1
TF_GLM_HEAD_BITS=8
NCCL_P2P_DISABLE=1
# --- recipe
TF_GLM_KDA_PAD=1
TF_GLM_OVN_KEEP_SEQS=1
"""
DEV = """# dev
# --- runtime
HF_HUB_OFFLINE=1
TF_GLM_HEAD_BITS=8
NCCL_P2P_DISABLE=1
# --- recipe
TF_GLM_KDA_PAD=1
TF_GLM_OVN_KEEP_SEQS=1
# --- candidates
TF_GLM_OVN_SOLO_TO_START=1
"""
SRC = 'const names = .{ "TF_GLM_HEAD_BITS", "TF_GLM_KDA_PAD", "TF_GLM_OVN_KEEP_SEQS", "TF_GLM_OVN_SOLO_TO_START" };\n'


class Fixture:
    def __init__(self, prod=PROD, dev=DEV, src=SRC):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="checkenv-", dir=ROOT / "work"))
        (self.dir / "env").mkdir()
        (self.dir / "env/prod.env").write_text(prod, encoding="utf-8")
        (self.dir / "env/dev.env").write_text(dev, encoding="utf-8")
        g = self.dir / "git"
        (g / "zig/src").mkdir(parents=True)
        (g / "zig/src/names.zig").write_text(src, encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", "-C", str(g), *args], check=True, capture_output=True)
        self.tree = f"{g / '.git'}:HEAD"

    def run(self, tree=False):
        return check_env.check(self.dir / "env", self.tree if tree else None)

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class CheckEnv(unittest.TestCase):
    def setUp(self):
        (ROOT / "work").mkdir(exist_ok=True)

    def fx(self, **kw):
        f = Fixture(**kw)
        self.addCleanup(f.close)
        return f

    def test_a_consistent_pair_is_clean_with_and_without_a_tree(self):
        f = self.fx()
        self.assertEqual([], f.run())
        self.assertEqual([], f.run(tree=True))

    def test_the_committed_files_are_clean(self):
        self.assertEqual([], check_env.check(ROOT / "scripts/env"))

    def test_a_malformed_line_is_a_finding(self):
        f = self.fx(prod=PROD.replace("TF_GLM_HEAD_BITS=8", "TF_GLM_HEAD_BITS = 8"))
        self.assertTrue(any("not NAME=value" in x for x in f.run()))

    def test_a_name_twice_in_a_file_is_a_finding(self):
        f = self.fx(dev=DEV.replace("TF_GLM_OVN_SOLO_TO_START=1", "TF_GLM_OVN_SOLO_TO_START=1\nTF_GLM_OVN_SOLO_TO_START=0"))
        self.assertTrue(any("again" in x for x in f.run()))

    def test_a_missing_or_misordered_section_is_a_finding(self):
        f = self.fx(dev=DEV.replace("# --- candidates\n", ""))
        self.assertTrue(any("no '# --- candidates' section" in x for x in f.run()))
        g = self.fx(prod=PROD.replace("# --- runtime", "# --- recipe", 1))
        self.assertTrue(any("out of order" in x for x in g.run()))

    def test_a_candidates_section_in_prod_is_a_finding(self):
        f = self.fx(prod=PROD + "# --- candidates\nTF_GLM_OVN_X=1\n")
        self.assertTrue(any("prod.env:" in x and "section 'candidates' out of order" in x for x in f.run()))

    def test_dev_differing_from_prod_in_a_production_section_is_a_finding(self):
        for dev in (DEV.replace("TF_GLM_OVN_KEEP_SEQS=1\n", ""), DEV.replace("TF_GLM_KDA_PAD=1", "TF_GLM_KDA_PAD=0"),
                    DEV.replace("HF_HUB_OFFLINE=1\nTF_GLM_HEAD_BITS=8", "TF_GLM_HEAD_BITS=8\nHF_HUB_OFFLINE=1")):
            f = self.fx(dev=dev)
            self.assertTrue(any("not prod.env's" in x for x in f.run()), dev)

    def test_a_candidate_that_is_a_production_name_is_a_finding(self):
        f = self.fx(dev=DEV + "TF_GLM_KDA_PAD=2\n")
        self.assertTrue(any("is a setting of prod.env" in x for x in f.run()))

    def test_a_name_the_tree_does_not_read_is_a_finding_but_nccl_and_hf_are_exempt(self):
        f = self.fx(src='const names = .{ "TF_GLM_HEAD_BITS", "TF_GLM_KDA_PAD", "TF_GLM_OVN_SOLO_TO_START" };\n')
        found = f.run(tree=True)
        self.assertEqual(["TF_GLM_OVN_KEEP_SEQS: not read anywhere under zig/src of HEAD"], found)

    def test_a_longer_quoted_name_is_not_a_match(self):
        f = self.fx(src='const a = "TF_GLM_KDA_PAD_X";\nconst b = .{ "TF_GLM_HEAD_BITS", "TF_GLM_OVN_KEEP_SEQS", "TF_GLM_OVN_SOLO_TO_START" };\n')
        self.assertEqual(["TF_GLM_KDA_PAD: not read anywhere under zig/src of HEAD"], f.run(tree=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
