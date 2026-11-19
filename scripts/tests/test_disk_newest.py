#!/usr/bin/env python3
"""The disk tier harness's notion of a conversation's newest kept state (scripts/disk.py).

Under TF_GLM_REQUEST_STARTS=1 a turn keeps its states at request starts and at its prompt's end, not on the 2,048-row grid, so a
harness that expects the resume at the grid point neither evicts the state the next turn resumes from nor notices a resume short of it
(the first window with the unaligned saves read two failures of that kind with every reply equal to the cold one). The conversation
records in these tests have the shape cmd_turn appends: case_id, tokens, grid, kept, newest (None without an answer from /stats).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import disk  # noqa: E402


class Stub:
    """A client whose /stats lists these RAM store entries."""

    def __init__(self, entries):
        self.entries = entries

    def get_json(self, path, timeout):
        assert path == "/stats"
        return {"prompt_cache": {"entries": self.entries}}


def turn(grid, kept, newest):
    return {"case_id": "M/t", "tokens": grid + 10, "grid": grid, "kept": kept, "newest": newest}


class NewestKept(unittest.TestCase):
    def test_request_starts_resume_at_the_prompts_end_not_the_grid(self):
        conv = {"prompts": [turn(30720, 2, 32035), turn(30720, 1, 32111)]}
        self.assertEqual(disk.newest_kept(conv), 32111)

    def test_a_turn_that_kept_nothing_leaves_the_earlier_state(self):
        conv = {"prompts": [turn(30720, 2, 32035), turn(32768, 0, None)]}
        self.assertEqual(disk.newest_kept(conv), 32035)

    def test_rows_without_a_newest_use_their_grid_point(self):
        conv = {"prompts": [{"case_id": "M/t1", "tokens": 4100, "grid": 4096, "kept": 1}, turn(6144, 1, None)]}
        self.assertEqual(disk.newest_kept(conv), 6144)

    def test_no_turn_is_zero(self):
        self.assertEqual(disk.newest_kept({"prompts": []}), 0)


class RamPositions(unittest.TestCase):
    ENTRIES = [{"at": 30720, "created_at_ms": 1000}, {"at": 32035, "created_at_ms": 2000}, {"at": 2912, "created_at_ms": 2500}]

    def test_since_keeps_the_states_a_turn_created(self):
        self.assertEqual(disk.ram_positions(Stub(self.ENTRIES), since_ms=2000), [32035, 2912])

    def test_before_keeps_the_older_states_for_the_eviction_loop(self):
        self.assertEqual(disk.ram_positions(Stub(self.ENTRIES), before_ms=2000), [30720])

    def test_no_bound_lists_every_state(self):
        self.assertEqual(disk.ram_positions(Stub(self.ENTRIES)), [30720, 32035, 2912])


if __name__ == "__main__":
    unittest.main()
