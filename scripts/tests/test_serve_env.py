#!/usr/bin/env python3
"""test_serve_env.py: serve.sh's environment, built from scripts/env/prod.env and dev.env, against what the last pre-split launcher built.

The oracle is the launcher text of commit 4c02515 (`git show`): its fixed block, its DEFS string, its XENV rules and its TF_GLM_ROCE_MULTI rule are parsed
here, in Python, and replayed for each configuration; serve.sh then runs in its DRYRUN mode (it prints the docker command and exits) under WSL bash and the
`-e NAME=value` words of that command are compared as lists. The intended differences are named in REMOVED, so a new difference fails the test.

Run from the top-level Windows shell: python scripts/tests/test_serve_env.py
"""
import itertools
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OLD_REV = "4c02515"
# Dropped on purpose: two names nothing in zig/src reads at the v1.2.9 pin or at main (the inventory of the move to main checked both), and the switch main's
# unconditional item plan retired (upstream 4e6cdeed9 and 51a6fe02a).
REMOVED = {"TF_GLM_COPY_MAX", "TF_GLM_COPY_REPLY_MATCH", "TF_GLM_OVN_EXL3_ITEMS"}


def wsl(path):
    p = pathlib.Path(path).resolve()
    return f"/mnt/{p.drive[0].lower()}{p.as_posix()[2:]}"


def old_text():
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{OLD_REV}:scripts/serve.sh"], capture_output=True, text=True, check=True).stdout


def old_environment(text, knobs, p, world, comm, xenv, caller, fatbin):
    """The `-e` pairs the pre-split launcher passes, in its order."""
    res = {"1": "12.5", "2": "14.5", "4": "13.0"}.get(str(p), "6.5")
    head = text[text.index("ENV=(") : text.index("[[ -n \"${COMM_ID:-}\" ]]")]
    fixed = re.findall(r"-e (\w+)=(\S+?)(?=\s|\))", head)
    out = []
    for n, v in fixed:
        out.append((n, {"$RES": res, "$RANK": "0", "$WORLD": str(world)}.get(v, v)))
    if comm:
        out.append(("NCCL_COMM_ID", comm))
    block = text[text.index("# The proven production/ai-engine NCCL shape") : text.index("# NCCL_DEBUG is deliberately NOT set")]
    for n, v in re.findall(r"-e (\w+)=(\S+?)(?=\s|\))", block):
        m = re.match(r'"\$\{(\w+):-([^}]*)\}"$|\$\{(\w+):-([^}]*)\}$', v)
        if m:
            var, default = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            v = caller.get(var, default)
        out.append((n, v))
    xe = xenv
    if knobs in ("measured", "all"):
        defs = re.search(r'DEFS="(.*?)"\n', text, re.S).group(1).split()
        for kv in defs:
            if f" -e {kv.split('=')[0]}=" not in f" {xe} ":
                xe = f"{xe} -e {kv}"
    if knobs != "off" and world > 1 and p <= 4 and " -e TF_GLM_ROCE_MULTI=" not in f" {xe} " and fatbin:
        xe = f"{xe} -e TF_GLM_ROCE_MULTI=1 -e TF_TP_MASTER={comm.split(':')[0]} -e TF_TP_KERNEL_IMAGE=/root/.cache/huggingface/tp_mailbox.fatbin"
    out += re.findall(r"-e (\w+)=(\S+)", xe)
    return out


def env_words(name, section=None):
    """prod.env or dev.env parsed here: the NAME=value lines of one section (runtime, recipe, candidates) or of all."""
    sec = "runtime"
    out = []
    for line in (ROOT / "scripts/env" / f"{name}.env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        m = re.match(r"# --- (runtime|recipe|candidates)(\s|$)", line)
        if m:
            sec = m.group(1)
            continue
        if not line or line.startswith("#"):
            continue
        if section in (None, sec):
            n, v = line.split(" #")[0].strip().split("=", 1)
            out.append((n, v))
    return out


def new_environment(knobs, p, world, comm, xenv, caller, fatbin):
    home = tempfile.mkdtemp(prefix="serveenv-", dir=ROOT / "work")
    try:
        if fatbin:
            d = pathlib.Path(home) / ".cache/huggingface"
            d.mkdir(parents=True)
            (d / "tp_mailbox.fatbin").write_bytes(b"x")
        pre = " ".join(f"{k}={shlex.quote(v)}" for k, v in caller.items())
        cmd = (f"cd {wsl(ROOT)} && {pre} DRYRUN=1 KNOBS={knobs} WORLD={world} XENV={shlex.quote(xenv)} HOME={wsl(home)}"
               + (f" COMM_ID={comm}" if comm else "") + f" bash scripts/serve.sh 0 {p}")
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        lines = [l for l in r.stdout.splitlines() if l.startswith("[serve] exec docker run")]
        if r.returncode or len(lines) != 1:
            raise AssertionError(f"serve.sh failed rc={r.returncode}: {r.stderr[-400:]} {r.stdout[-200:]}")
        return re.findall(r"-e (\w+)=(\S+)", lines[0].split(" ".join(["--ulimit", "stack=67108864"]), 1)[1])
    finally:
        for f in pathlib.Path(home).rglob("*"):
            if f.is_file():
                f.unlink()
        for d in sorted((x for x in pathlib.Path(home).rglob("*") if x.is_dir()), reverse=True):
            d.rmdir()
        os.rmdir(home)


class ServeEnv(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "work").mkdir(exist_ok=True)
        cls.old = old_text()

    def same(self, knobs, p, world, xenv="", caller=None, fatbin=False):
        comm = "192.0.2.1:29561" if world > 1 else ""
        want = [(n, v) for n, v in old_environment(self.old, knobs, p, world, comm, xenv, caller or {}, fatbin) if n not in REMOVED]
        got = new_environment(knobs, p, world, comm, xenv, caller or {}, fatbin)
        why = f"KNOBS={knobs} P={p} WORLD={world} XENV={xenv!r} caller={caller} fatbin={fatbin}"
        # docker takes the last `-e` of a name, so the effective environment is the comparison; the old launcher passed a name twice when XENV
        # re-set a fixed one, the new one passes it once, and a name twice in the new command would be a defect
        self.assertEqual(len(got), len({n for n, _ in got}), "a name is passed twice: " + why)
        self.assertEqual(dict(want), dict(got), why)
        return got

    def test_every_mode_matches_the_old_launcher(self):
        for knobs, p, world, fatbin in itertools.product(("off", "measured", "all"), (1, 2, 4, 8), (1, 3), (False, True)):
            self.same(knobs, p, world, fatbin=fatbin)

    def test_xenv_wins_over_a_file_line(self):
        got = dict(self.same("measured", 4, 3, xenv="-e TF_GLM_OVN_DRAFT_EDGE=0.9 -e TF_GLM_OVN_KEEP_SEQS=0 -e TF_GLM_HEAD_BITS=4"))
        self.assertEqual("0.9", got["TF_GLM_OVN_DRAFT_EDGE"])
        self.assertEqual("0", got["TF_GLM_OVN_KEEP_SEQS"])
        self.assertEqual("4", got["TF_GLM_HEAD_BITS"])

    def test_caller_environment_wins_for_the_two_nccl_names(self):
        got = dict(self.same("measured", 4, 3, caller={"NCCL_IB_HCA": "mlx5_0", "NCCL_SOCKET_IFNAME": "eth9"}))
        self.assertEqual("mlx5_0", got["NCCL_IB_HCA"])
        self.assertEqual("eth9", got["NCCL_SOCKET_IFNAME"])

    def test_off_carries_the_runtime_section_and_no_recipe_line(self):
        got = dict(new_environment("off", 4, 3, "192.0.2.1:29561", "", {}, False))
        for n, v in env_words("prod", "runtime"):
            self.assertEqual(v, got[n], n)
        for n, _ in env_words("prod", "recipe"):
            self.assertNotIn(n, got, n)

    def test_dev_is_prod_plus_its_candidates_and_nothing_else_differs(self):
        prod = dict(new_environment("measured", 4, 3, "192.0.2.1:29561", "", {}, False))
        dev = dict(new_environment("dev", 4, 3, "192.0.2.1:29561", "", {}, False))
        self.assertEqual(dict(env_words("dev")), {k: v for k, v in dev.items() if k in dict(env_words("dev"))})
        for k, v in prod.items():
            self.assertEqual(v, dev.get(k), f"dev lost or changed {k}")
        extra = {k for k in dev if k not in prod}
        self.assertEqual({n for n, _ in env_words("dev")} - {n for n, _ in env_words("prod")}, extra)
        self.assertTrue(extra, "dev.env adds no candidate")

    def test_the_check_launcher_takes_its_runtime_settings_from_prod_env(self):
        text = (ROOT / "scripts/gpu-check-tp3.sh").read_text(encoding="utf-8")
        self.assertIn('env/words.sh" prod runtime', text)
        runtime = {n for n, _ in env_words("prod", "runtime")}
        carried = sorted(n for n in runtime if re.search(rf"-e {n}=", text))
        self.assertEqual([], carried, "gpu-check-tp3.sh carries its own copy of a runtime setting")

    def test_a_bad_mode_is_refused(self):
        r = subprocess.run(["bash", "-c", f"cd {wsl(ROOT)} && DRYRUN=1 KNOBS=nope COMM_ID=x:1 bash scripts/serve.sh 0 4"], capture_output=True, text=True)
        self.assertEqual(2, r.returncode)
        self.assertIn("KNOBS must be", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
