#!/usr/bin/env python3
"""Tests for spark-gates.py's verdict: each run.log below is shaped like the runner's real output (the SG lines, and the
gates.sh, gate-names.sh and lean.sh lines it prefixes), and each must judge as stated. Text only, nothing compiles."""
import importlib.util, os, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = next(p for p in (os.path.join(os.path.dirname(HERE), "spark-gates.py"), os.path.join(HERE, "spark-gates.py"))
            if os.path.isfile(p))
spec = importlib.util.spec_from_file_location("spark_gates", TOOL)
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)

RUN = "sg-20261115-180000"
N1 = ("cli_config_test.test.serve --config: expand reads the file, passes other commands through and names what it "
      "cannot read")
N2 = "listener.test.accepted IPv4 and IPv6 TCP streams disable Nagle for incremental responses"
PIN_TREE = "4be51cc6beefee860f611b5bb928dd06a4f3c72c"
IDS = {"base": PIN_TREE, "series": "e02b8a89c2ccbb7fe67e42fb4bf300bec1a5f2c3",
       "stack": "27a87244e7dca097007c8b086b7c49a76a8e69d2"}
NPATCHES = {"base": 0, "series": 32, "stack": 35}
STANDALONE = ["compile-cuda-tests rc=0 | Build Summary: 10/10 steps succeeded",
              "test-glm-ring-host rc=0 | Build Summary: 4/4 steps succeeded; 3/3 tests passed",
              "test-glm-logprobs-host rc=0 | Build Summary: 4/4 steps succeeded; 10/10 tests passed"]


def gates_lines(n, names=(N1, N2), test_rc=1):
    """gates.sh's output for one tree, without the runner's prefix."""
    out = ["check-native-cuda-host rc=0 | Build Summary: 7/7 steps succeeded"]
    if test_rc == 0:
        out.append("test-cuda-host rc=0 | Build Summary: 412/412 steps succeeded; 6800/6800 tests passed")
    else:
        out.append(f"test-cuda-host rc={test_rc} | Build Summary: 410/412 steps succeeded (1 failed)")
        out += [f"error: '{x}' failed:" for x in names]
    out += STANDALONE
    out.append("test-glm-onepass-order-host: not a step of this tree" if n == "base"
               else "test-glm-onepass-order-host rc=0 | Build Summary: 3/3 steps succeeded")
    out += ["test-rows-host rc=0 | Build Summary: 3/3 steps succeeded", "fmt rc=0 "]
    return out


def gates(n, lines=None, done=True, rc=1):
    lines = gates_lines(n) if lines is None else lines
    return [f"[{n} gates] {x}" for x in lines + ([f"GATES-DONE {RUN}-{n} bad=1"] if done else [])] + \
        [f"SG gates {n} rc={rc}"]


def names(n, count=2, new=(), build_failed=False):
    out = [f"{RUN}-base: 2 failing names | 3836/3852 tests passed (14 skipped, 2 failed)",
           f"{RUN}-{n}: {count} failing names | 6761/6796 tests passed (33 skipped, 2 failed)",
           f"only {RUN}-{n} fails: {new[0] if new else 'none'}", *new[1:], f"only {RUN}-base fails: none"]
    if build_failed:
        out.append(f"{RUN}-{n}: BUILD FAILED, 3 compile error lines in its log (no test ran, its failing names are "
                   f"not a result)")
    return [f"[{n} names] {x}" for x in out] + [f"SG names {n} rc={1 if new or build_failed else 0}"]


def lean(n, new=0, head="6500 files, 341 problems", details=()):
    out = [f"base /home/adam/spark-gates/{RUN}/trees/base: 6454 files, 341 problems",
           f"head /home/adam/spark-gates/{RUN}/trees/{n}: {head}", *details,
           f"lean: {341 + new} problems, 341 on the base, {new} new"]
    return [f"[{n} lean] {x}" for x in out] + [f"SG lean {n} rc={1 if new else 0}"]


def head(n, **kw):
    return gates(n, **kw.get("gates", {})) + names(n, **kw.get("names", {})) + lean(n, **kw.get("lean", {}))


def run_log(trees=("base", "series", "stack"), over=None, ids=None, expect=None, built=None, finished=True):
    """A run.log of the trees; over[name] replaces that tree's output after its build line."""
    over, ids = over or {}, ids or IDS
    expect = expect or ids
    out = [f"SG run {RUN}", f"SG pin v1.2.9 commit=6b9de695104b6b8b30c20458da87ac06c9480289 tree={PIN_TREE} zig=0.17.0",
           "SG dir d0 patches/engine files=32"]
    out += [f"SG tree {t} patches={NPATCHES[t]} dirs={'-' if t == 'base' else 'd0'}" for t in trees]
    out += [f"SG expect {t} {expect[t]} from=x" for t in trees]
    out += [f"SG id {t} {ids[t]} applied={NPATCHES[t]}" for t in (built or trees)]
    for t in trees:
        out += over[t] if t in over else (gates(t) if t == "base" else head(t))
    if finished:
        out += ["SG verdict rc=0", "SPARK-GATES-DONE x verdict=PASS"]
    return "\n".join(out) + "\n"


class Verdict(unittest.TestCase):
    def judge(self, text, ok, needle):
        lines, got = sg.judge(sg.parse_log(text))
        out = "\n".join(lines)
        self.assertEqual(got, ok, out)
        self.assertIn(needle, out)
        return out

    def test_green_run_passes_with_base_names_listed(self):
        out = self.judge(run_log(), True, "VERDICT PASS: series, stack pass against base")
        self.assertIn("1: 2 failing, 0 new", out)
        self.assertIn(N2, out)

    def test_a_head_that_fixes_base_failures_passes(self):
        over = {"series": head("series", gates={"lines": gates_lines("series", test_rc=0), "rc": 0},
                               names={"count": 0})}
        self.judge(run_log(over=over), True, "VERDICT PASS")

    def test_patch_that_does_not_apply(self):
        over = {"series": ["PATCH FAILED series d0/0032-glm-keep-seqs.patch",
                           "SG patch-failed series d0/0032-glm-keep-seqs.patch applied=31", "SG skip series not built"]}
        out = self.judge(run_log(over=over, built=("base", "stack")), False, "series PATCH FAILED")
        self.assertIn("patches/engine/0032-glm-keep-seqs.patch does not apply (after 31 of 32)", out)

    def test_compile_break_is_build_failed(self):
        broken = gates_lines("series")
        broken[0:1] = ["check-native-cuda-host rc=1 | Build Summary: 6/7 steps succeeded; 1 failed",
                       "zig/src/server/main.zig:56:11: error: unused local constant"]
        out = self.judge(run_log(over={"series": head("series", gates={"lines": broken})}), False,
                         "series BUILD FAILED")
        self.assertIn("check-native-cuda-host rc=1: zig/src/server/main.zig:56:11: error: unused local constant", out)

    def test_broken_build_zig_lists_no_steps_and_fails(self):
        nosteps = [f"{s}: not a step of this tree" for s in ("check-native-cuda-host", "test-cuda-host",
                   "compile-cuda-tests", "test-glm-ring-host", "test-glm-logprobs-host",
                   "test-glm-onepass-order-host", "test-rows-host")] + ["fmt rc=0 "]
        over = {"series": head("series", gates={"lines": nosteps, "rc": 0}, names={"count": 0})}
        self.judge(run_log(over=over), False, "check-native-cuda-host did not run")

    def test_a_new_failing_name(self):
        over = {"series": head("series", gates={"lines": gates_lines("series", names=(N1, N2, "kv.test.new"))},
                               names={"count": 3, "new": ("kv.test.new",)})}
        out = self.judge(run_log(over=over), False, "base does not: kv.test.new")
        self.assertIn("NEW kv.test.new", out)

    def test_a_new_lean_problem(self):
        over = {"stack": head("stack", lean={"new": 1, "details": ("zig/src/native/cuda.zig: over 600 lines (1 new)",)})}
        self.judge(run_log(over=over), False, "lean: 1 new problem(s): zig/src/native/cuda.zig: over 600 lines")

    def test_timed_out_tests_with_no_names_fail(self):
        lines = gates_lines("series")
        lines[1:4] = ["test-cuda-host: TIMED OUT after 40 minutes", "test-cuda-host rc=124 | "]
        over = {"series": head("series", gates={"lines": lines}, names={"count": 0})}
        self.judge(run_log(over=over), False, "test-cuda-host rc=124 (timed out)")

    def test_rc1_that_no_failing_name_explains(self):
        over = {"series": head("series", gates={"lines": gates_lines("series", names=())}, names={"count": 0})}
        self.judge(run_log(over=over), False, "no failing test name explains it")

    def test_tree_id_mismatch(self):
        self.judge(run_log(expect={**IDS, "series": "0" * 40}), False, "is not the expected 0000")

    def test_lean_check_that_crashed_on_one_side(self):
        over = {"series": head("series", lean={"head": "SyntaxError: invalid syntax"})}
        self.judge(run_log(over=over), False, "did not report on both sides")

    def test_runner_killed_mid_gates(self):
        over = {"stack": gates("stack", done=False)[:2]}
        text = run_log(over=over, finished=False)
        self.judge(text.replace("SG gates stack rc=1\n", ""), False, "gates.sh did not run")

    def test_base_with_compile_errors_in_its_tests(self):
        lines = gates_lines("base")
        lines[1:4] = ["test-cuda-host rc=1 | Build Summary: 3/408 steps succeeded", "zig/src/x.zig:1:1: error: boom"]
        self.judge(run_log(over={"base": gates("base", lines=lines)}), False, "base BROKEN")

    def test_gate_names_build_failed_alone(self):
        over = {"series": head("series", gates={"lines": gates_lines("series", names=())},
                               names={"count": 0, "build_failed": True})}
        self.judge(run_log(over=over), False, "series BUILD FAILED")

    def test_a_step_base_ran_is_missing_on_the_head(self):
        lines = [x for x in gates_lines("series") if not x.startswith("test-rows-host")]
        self.judge(run_log(over={"series": head("series", gates={"lines": lines})}), False,
                   "test-rows-host ran on base but not on this tree")

    def test_gates_sh_that_stopped_early(self):
        over = {"series": ["[series gates] no zig at /home/adam/tools/zig-x86_64-linux-0.17.0/zig",
                           "SG gates series rc=2"] + names("series") + lean("series")}
        self.judge(run_log(over=over), False, "stopped before GATES-DONE")


if __name__ == "__main__":
    unittest.main()
