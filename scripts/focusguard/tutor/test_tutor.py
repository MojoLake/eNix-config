import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tutor


def assessment(verdict, hint=""):
    return {"verdict": verdict, "feedback": "Specific feedback.", "hint": hint,
            "misconception": "" if verdict == "correct" else "Missed a dependency."}


class FakeEvaluator:
    def __init__(self, results):
        self.results = iter(results)
        self.offline = False
        self.calls = 0

    def assess(self, exercise, recent):
        self.calls += 1
        if self.offline:
            return None
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


class TutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = tutor.Store(Path(self.tmp.name))
        self.curriculum = json.loads((tutor.HERE / "curriculum.json").read_text())
        self.state = self.store.load()
        self.state["active"] = tutor.new_session(self.state, self.curriculum)
        self.store.save(self.state)

    def run_task(self, task, answers, results):
        answers = iter(answers)
        output = []
        evaluator = FakeEvaluator(results)
        tutor.run_task(task, self.state, self.store, evaluator, lambda: next(answers), output.append)
        return output, evaluator

    def test_independent_transfer_advances_and_next_session_probes_previous(self):
        for task in self.state["active"]["tasks"]:
            self.run_task(task, ["A fully reasoned answer"], [assessment("correct")])
        completed, log = tutor.finish(self.state, self.store)
        self.assertTrue(completed["advanced"])
        self.assertTrue(log.exists())
        state = self.store.load()
        self.assertEqual(state["cursor"], 1)
        self.assertIsNone(state["active"])
        next_session = tutor.new_session(state, self.curriculum)
        self.assertEqual(next_session["tasks"][0]["concept"], "reuse")
        self.assertEqual(next_session["lesson"], "shape")

    def test_hint_then_correct_is_not_independent(self):
        task = self.state["active"]["tasks"][-1]
        self.run_task(task, ["wrong", "/hint", "corrected"],
                      [assessment("partial", "Think about causal dependence."), assessment("correct")])
        self.assertTrue(task["done"])
        self.assertTrue(task["assisted"])
        self.assertFalse(task["independent"])

    def test_two_failed_attempts_reveal_and_reflect_with_bounded_calls(self):
        task = self.state["active"]["tasks"][0]
        _, evaluator = self.run_task(task, ["wrong", "still wrong", "I missed causality."],
                                     [assessment("incorrect"), assessment("partial")])
        self.assertEqual(evaluator.calls, 2)
        self.assertTrue(task["done"])
        self.assertEqual(task["reflection"], "I missed causality.")
        self.assertFalse(task["independent"])

    def test_offline_completes_without_advancing_or_inventing_mastery(self):
        for task in self.state["active"]["tasks"]:
            self.run_task(task, ["my attempt", "my comparison"], [None])
        completed, _ = tutor.finish(self.state, self.store)
        self.assertFalse(completed["advanced"])
        self.assertEqual(self.store.load()["cursor"], 0)
        self.assertEqual(self.state["concepts"]["reuse"]["independent"], 0)

    def test_network_failure_preserves_answer_and_continues_offline(self):
        task = self.state["active"]["tasks"][0]
        output, evaluator = self.run_task(task, ["a real attempt", "self reflection"], [ValueError("bad JSON")])
        self.assertTrue(evaluator.offline)
        self.assertTrue(any("unavailable" in line for line in output))
        self.assertEqual(task["attempts"][0]["answer"], "a real attempt")
        self.assertIsNone(task["attempts"][0]["assessment"])

    def test_cancel_during_evaluation_resumes_pending_answer(self):
        task = self.state["active"]["tasks"][0]
        class Interrupted(FakeEvaluator):
            def assess(self, exercise, recent):
                raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            tutor.run_task(task, self.state, self.store, Interrupted([]), lambda: "saved answer", lambda _: None)
        resumed = self.store.load()
        self.assertEqual(resumed["active"]["tasks"][0]["attempts"][0]["assessment"], "pending")
        def no_new_input():
            self.fail("Pending answer should be evaluated without asking again")
        task = resumed["active"]["tasks"][0]
        tutor.run_task(task, resumed, self.store, FakeEvaluator([assessment("correct")]), no_new_input, lambda _: None)
        self.assertTrue(task["independent"])

    def test_resume_after_reveal_does_not_reevaluate(self):
        task = self.state["active"]["tasks"][0]
        task["revealed"] = True
        task["assisted"] = True
        self.store.save(self.state)
        self.run_task(task, ["my reflection"], [])
        self.assertTrue(task["done"])
        self.assertFalse(task["independent"])

    def test_refuses_incomplete_finish_and_preserves_corrupt_state(self):
        with self.assertRaises(ValueError):
            tutor.finish(self.state, self.store)
        self.store.path.write_text("corrupt")
        with self.assertRaises(ValueError):
            self.store.load()
        self.assertEqual(self.store.path.read_text(), "corrupt")

    def test_concurrent_sessions_refused(self):
        with self.store.locked():
            with self.assertRaises(ValueError):
                with tutor.Store(self.store.directory).locked():
                    pass

    def test_invalid_model_output_cannot_grant_credit(self):
        for value in ({}, {"verdict": "correct"}, assessment("pass"), {**assessment("correct"), "extra": "yes"}):
            with self.assertRaises(ValueError):
                tutor.validate_assessment(value)
        self.assertEqual(tutor.clean("hello\x1b[2J\u202eworld"), "hello[2Jworld")

    def test_curriculum_unique_complete_and_numeric_examples(self):
        lessons = self.curriculum["lessons"]
        self.assertEqual(len({item["id"] for item in lessons}), len(lessons))
        for lesson in lessons:
            for field in ("question", "reference", "rubric", "transfer", "transfer_reference", "transfer_rubric", "hints"):
                self.assertTrue(lesson[field])
        per_token = 2 * 32 * 8 * 128 * 2
        self.assertEqual(per_token * 4096 / 2**20, 512)
        self.assertEqual(per_token * (1024 + 2048 + 4096) / 2**20, 896)
        self.assertEqual((4 * 2**30) // (6144 * per_token), 5)
        self.assertEqual((512 * 2**20) / (32 * 2**30) * 1000, 15.625)

    def test_preflight_invalid_site_and_old_install_never_runs_sudo(self):
        policy = Path(self.tmp.name) / "policy.json"
        policy.write_text(json.dumps({"sites": {"youtube": []}, "defaultMinutes": 20, "maxMinutes": 30}))
        with patch.object(tutor, "GUARD", policy), patch.object(tutor, "POLICY", policy), patch.object(tutor.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                tutor.preflight("badsite", None)
            run.assert_not_called()
            with self.assertRaises(ValueError):
                tutor.preflight("youtube", 31)
            run.assert_not_called()
            run.return_value.returncode = 1
            with self.assertRaises(ValueError):
                tutor.preflight("youtube", 20)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args[0][0][-1], "capabilities")

    def test_unlock_requires_completed_study_before_privileged_grant(self):
        with patch.object(tutor.sys, "argv", ["tutor.py", "unlock", "youtube", "5"]), \
             patch.object(tutor.sys.stdin, "isatty", return_value=True), \
             patch.object(tutor.os, "geteuid", return_value=501), \
             patch.object(tutor, "Store", return_value=self.store), \
             patch.object(tutor, "preflight", return_value=5), \
             patch.object(tutor, "study", side_effect=KeyboardInterrupt) as study, \
             patch.object(tutor.subprocess, "run") as run:
            with self.assertRaises(KeyboardInterrupt):
                tutor.main()
            run.assert_not_called()
            study.side_effect = None
            tutor.main()
            run.assert_called_once_with(["/usr/bin/sudo", str(tutor.GUARD), "unlock-tutored", "youtube", "5"], check=True)


if __name__ == "__main__":
    unittest.main()
