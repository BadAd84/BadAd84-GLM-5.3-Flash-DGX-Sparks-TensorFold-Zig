#!/usr/bin/env python3
"""test_check_env_coverage.py: scripts/env/check-env-coverage.py, one defect class a test, on a fixture table and env files.

The gate holds the D1 model: every row of the table's scopes is set in both env files, one verdict a row, a value the row's
own parser accepts, and a candidate only as an upgrade of a row prod keeps at its engine default. Run from the top-level
shell: python scripts/tests/test_check_env_coverage.py
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/env/check-env-coverage.py"

TABLE = """\
pub const rules = [_]Rule{
    .{ .name = "TF_A", .scope = .glm, .kind = .flag, .forms = "0 or 1" },
    .{ .name = "TF_B", .scope = .glm, .kind = .u32, .min = 4, .forms = "a whole number, 4 or more" },
    .{ .name = "TF_C", .scope = .glm, .kind = .flag, .blank_default = false, .forms = "0 or 1" },
    .{ .name = "TF_MEASURED", .scope = .glm, .kind = .word, .words = &.{ "main", "other" }, .forms = "main or other" },
    .{ .name = "TF_OUT", .scope = .metal, .kind = .flag, .forms = "0 or 1" },
};
"""

PROD = """\
# --- runtime
# --- recipe
TF_MEASURED=main
# --- completeness
TF_A=0
TF_B=4
TF_C=1
"""

DEV = PROD + """\
# --- candidates
TF_A=1
"""

REG = """\
# --- table rows
# measured TF_MEASURED=main: its cells; evidence docs/KNOBS.md
# debt TF_A=0: the default; evidence docs/ENV-REGISTER.md
# debt TF_B=4: the default; evidence docs/ENV-REGISTER.md
# debt TF_C=1: the default; evidence docs/ENV-REGISTER.md
# --- candidates
# candidate TF_A=1: measured; evidence docs/KNOBS.md
"""


class Fixture:
    def __init__(self, prod=PROD, dev=DEV, reg=REG):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="coverage-", dir=ROOT / "work"))
        (self.dir / "environment.zig").write_text(TABLE, encoding="utf-8")
        (self.dir / "prod.env").write_text(prod, encoding="utf-8")
        (self.dir / "dev.env").write_text(dev, encoding="utf-8")
        (self.dir / "register.env").write_text(reg, encoding="utf-8")

    def run(self):
        r = subprocess.run([sys.executable, str(GATE), "--table", str(self.dir / "environment.zig"),
                            "--prod", str(self.dir / "prod.env"), "--dev", str(self.dir / "dev.env"),
                            "--register", str(self.dir / "register.env"), "--scopes", "glm,cuda,common"],
                           capture_output=True, text=True)
        return r.returncode, r.stdout

    def close(self):
        for f in self.dir.iterdir():
            f.unlink()
        self.dir.rmdir()


class Coverage(unittest.TestCase):
    def check(self, **kw):
        f = Fixture(**kw)
        try:
            return f.run()
        finally:
            f.close()

    def test_a_complete_pair_is_clean(self):
        rc, out = self.check()
        self.assertEqual(0, rc, out)
        self.assertIn("4 rows in scope, set 4, measured 1, inert 0, debt 3, raw 0, candidates 1, unset 0", out)

    def test_an_inert_verdict_is_clean_and_counted(self):
        rc, out = self.check(reg=REG.replace("# debt TF_C=1: the default; evidence docs/ENV-REGISTER.md",
                                             "# inert TF_C=1: a log switch; evidence docs/ENV-REGISTER.md"))
        self.assertEqual(0, rc, out)
        self.assertIn("inert 1, debt 2", out)

    def test_an_inert_verdict_without_a_citation_is_a_finding(self):
        rc, out = self.check(reg=REG.replace("# debt TF_C=1: the default; evidence docs/ENV-REGISTER.md",
                                             "# inert TF_C=1: a log switch, no path named"))
        self.assertEqual(1, rc)
        self.assertIn("cites no evidence path", out)

    def test_a_row_missing_from_prod_is_unset(self):
        rc, out = self.check(prod=PROD.replace("TF_B=4\n", ""))
        self.assertEqual(1, rc)
        self.assertIn("UNSET TF_B", out)

    def test_a_verdict_value_that_differs_is_a_finding(self):
        rc, out = self.check(reg=REG.replace("# debt TF_B=4:", "# debt TF_B=5:"))
        self.assertEqual(1, rc)
        self.assertIn("VALUE TF_B", out)

    def test_the_retired_default_ok_word_is_a_finding(self):
        rc, out = self.check(reg=REG.replace("# debt TF_B=4:", "# default-ok TF_B=4:"))
        self.assertEqual(1, rc)
        self.assertIn("retired verdict default-ok", out)
        self.assertIn("UNRECORDED TF_B", out)

    def test_a_value_the_rows_parser_refuses_is_a_finding(self):
        for prod in (PROD.replace("TF_A=0", "TF_A=2"), PROD.replace("TF_B=4", "TF_B=3"),
                     PROD.replace("TF_MEASURED=main", "TF_MEASURED=mian")):
            rc, out = self.check(prod=prod)
            self.assertEqual(1, rc, prod)
            self.assertIn("REFUSED", out)

    def test_a_blank_on_a_row_that_refuses_blank_is_a_finding(self):
        rc, out = self.check(prod=PROD.replace("TF_C=1", "TF_C="), dev=DEV.replace("TF_C=1", "TF_C="))
        self.assertEqual(1, rc)
        self.assertIn("BLANK TF_C", out)

    def test_a_candidate_repeating_prods_value_is_a_finding(self):
        rc, out = self.check(dev=DEV.replace("TF_A=1", "TF_A=0"), reg=REG.replace("# candidate TF_A=1:", "# candidate TF_A=0:"))
        self.assertEqual(1, rc)
        self.assertIn("CANDIDATE TF_A: repeats prod.env's value", out)

    def test_a_candidate_over_a_measured_line_is_a_finding(self):
        dev = DEV.replace("# --- candidates\nTF_A=1", "# --- candidates\nTF_MEASURED=other")
        reg = REG.replace("# candidate TF_A=1: measured; evidence docs/KNOBS.md",
                          "# candidate TF_MEASURED=other: measured; evidence docs/KNOBS.md")
        rc, out = self.check(dev=dev, reg=reg)
        self.assertEqual(1, rc)
        self.assertIn("CANDIDATE TF_MEASURED: overrides a measured recipe line", out)

    def test_a_name_with_no_table_row_needs_a_raw_line(self):
        rc, out = self.check(prod=PROD + "TF_RAW=1\n", dev=DEV + "TF_RAW=1\n")
        self.assertEqual(1, rc)
        self.assertIn("UNREAD TF_RAW", out)
        rc, out = self.check(prod=PROD + "TF_RAW=1\n", dev=DEV + "TF_RAW=1\n",
                             reg=REG + "# raw TF_RAW=1: raw getenv; evidence docs/ENV-REGISTER.md\n")
        self.assertEqual(1, rc)  # dev.env's candidates line has no candidate record
        self.assertIn("UNRECORDED candidate TF_RAW", out)

    def test_a_stale_verdict_is_a_finding(self):
        rc, out = self.check(reg=REG + "# debt TF_GONE=0: x; evidence docs/KNOBS.md\n")
        self.assertEqual(1, rc)
        self.assertIn("STALE TF_GONE", out)

    def test_a_launcher_row_stays_blank_and_is_clean(self):
        # launcher: serve.sh computes the value per boot, so the env line is blank by rule
        rc, out = self.check(prod=PROD.replace("TF_B=4\n", "TF_B=\n"),
                             dev=DEV.replace("TF_B=4\n", "TF_B=\n"),
                             reg=REG.replace("# debt TF_B=4:", "# launcher TF_B=:"))
        self.assertEqual(0, rc, out)

    def test_a_launcher_row_with_a_value_is_a_finding(self):
        # a value here would override the launcher, which is how a rank gets the wrong identity
        rc, out = self.check(prod=PROD.replace("TF_B=4\n", "TF_B=9\n"),
                             reg=REG.replace("# debt TF_B=4:", "# launcher TF_B=:"))
        self.assertEqual(1, rc)
        self.assertIn("VALUE TF_B: launcher", out)

    def test_an_absent_row_stays_blank_and_is_clean(self):
        # absent: no value is the decision, so a blank line is the correct record
        rc, out = self.check(prod=PROD.replace("TF_B=4\n", "TF_B=\n"),
                             dev=DEV.replace("TF_B=4\n", "TF_B=\n"),
                             reg=REG.replace("# debt TF_B=4:", "# absent TF_B=:"))
        self.assertEqual(0, rc, out)

    def test_an_absent_row_with_a_value_is_a_finding(self):
        # setting a value here would switch on a feature the record says is deliberately off
        rc, out = self.check(prod=PROD.replace("TF_B=4\n", "TF_B=9\n"),
                             reg=REG.replace("# debt TF_B=4:", "# absent TF_B=:"))
        self.assertEqual(1, rc)
        self.assertIn("VALUE TF_B: absent", out)

if __name__ == "__main__":
    unittest.main(verbosity=2)
