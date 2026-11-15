import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import buddy


class BuddyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = buddy.Store(self.temp.name)
        self.sent = []

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def notify(self, state, root):
        self.sent.append(state["notification"])

    def proposal(self, **changes):
        response = {"reply": "Let's test that batch-size drop.", "action": "propose",
                    "task": "Measure throughput at three batch sizes", "minutes": 45}
        response.update(changes)
        return response

    def test_due_once_across_restarts_and_sleep(self):
        self.store.start("Measure throughput", 1, now=100)
        self.assertFalse(self.store.notify_due(self.notify, now=159))
        self.store.db.close()
        self.store = buddy.Store(self.temp.name)
        self.assertTrue(self.store.notify_due(self.notify, now=3600))
        self.assertFalse(self.store.notify_due(self.notify, now=7200))
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.store.state()["sent"])

    def test_delivery_failure_is_retried(self):
        self.store.start("Measure throughput", 1, now=0)
        def fail(*args):
            raise OSError("Hammerspoon is not running")
        with self.assertRaises(OSError):
            self.store.notify_due(fail, now=60)
        self.assertFalse(self.store.state()["sent"])
        self.assertTrue(self.store.notify_due(self.notify, now=90))

    def test_snooze_cancels_old_deadline_and_creates_one_new_notification(self):
        self.store.start("Measure throughput", 1, now=0)
        first = self.store.state()["notification"]
        self.store.snooze(2, now=30)
        self.assertNotEqual(first, self.store.state()["notification"])
        self.assertFalse(self.store.notify_due(self.notify, now=60))
        self.assertTrue(self.store.notify_due(self.notify, now=150))
        self.store.snooze(1, now=150)
        self.assertTrue(self.store.notify_due(self.notify, now=210))
        self.assertEqual(len(self.sent), 2)

    def test_finished_session_cannot_send_or_be_snoozed(self):
        self.store.start("Measure throughput", 1, now=0)
        self.store.finish()
        self.assertFalse(self.store.notify_due(self.notify, now=600))
        with self.assertRaises(ValueError):
            self.store.snooze(20)

    def test_proposal_is_saved_without_replacing_active_commitment(self):
        self.store.start("Old task", 1, now=0)
        self.store.reply(self.proposal(), self.store.state()["revision"])
        self.assertEqual(self.store.state()["task"], "Old task")
        self.store.db.close()
        self.store = buddy.Store(self.temp.name)
        self.store.accept()
        self.assertEqual(self.store.state()["task"], self.proposal()["task"])
        self.assertIsNone(self.store.state()["proposal"])

    def test_stale_model_response_cannot_restart_finished_session(self):
        revision = self.store.state()["revision"]
        self.store.finish()
        with self.assertRaises(ValueError):
            self.store.reply(self.proposal(), revision)
        self.assertIsNone(self.store.state()["task"])
        self.assertIsNone(self.store.state()["proposal"])

    def test_two_workers_do_not_deliver_twice(self):
        self.store.start("Measure throughput", 1, now=0)
        second = buddy.Store(self.temp.name)
        try:
            self.store.notify_due(self.notify, now=60)
            self.assertFalse(second.notify_due(self.notify, now=60))
        finally:
            second.db.close()
        self.assertEqual(len(self.sent), 1)

    def test_chat_accepts_proposal_then_records_update_and_finishes(self):
        responses = iter([self.proposal(), {"reply": "Good, you have an answer.",
                                           "action": "finish", "task": "", "minutes": 0}])
        def model(store):
            return next(responses)
        with contextlib.redirect_stdout(io.StringIO()):
            buddy.handle_input(self.store, "Investigate the batch-size drop", model)
            self.assertIsNone(self.store.state()["task"])
            buddy.handle_input(self.store, "", model)
            self.assertIsNotNone(self.store.state()["task"])
            self.assertFalse(buddy.handle_input(self.store, "Found the cause. I'm finished.", model))
        self.assertIsNone(self.store.state()["task"])
        self.assertTrue(any("Found the cause" in m["content"] for m in self.store.history()))

    def test_model_outage_preserves_commitment_and_offline_commands_work(self):
        def fail(store):
            raise ValueError("offline")
        with contextlib.redirect_stdout(io.StringIO()):
            buddy.handle_input(self.store, "/start 45 Measure throughput", fail)
            before = self.store.state()
            with self.assertRaises(ValueError):
                buddy.handle_input(self.store, "I am stuck", fail)
            self.assertEqual(self.store.state(), before)
            buddy.handle_input(self.store, "/snooze 20", fail)
            self.assertFalse(buddy.handle_input(self.store, "done for today", fail))

    def test_invalid_durations_and_model_responses(self):
        for value in (0, -1, 241, True, 2.5, "nan"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.start("Task", value)
        for changes in ({"action": "exec"}, {"minutes": 999}, {"task": ""},
                        {"reply": ""}, {"reply": []}, {"action": "finish", "minutes": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                buddy.validate_response(self.proposal(**changes))

    def test_notification_payload_is_data_even_for_hostile_text(self):
        task = 'Quotes " and $(touch /tmp/nope) and `id` and Å'
        seen = {}
        def run(command, **kwargs):
            files = list(Path(self.temp.name).glob("*.json"))
            seen.update(json.loads(files[0].read_text()))
            self.assertNotIn(task, command[-1])
            return type("Result", (), {"returncode": 0, "stdout": "BUDDY_SENT"})()
        with patch("buddy.subprocess.run", side_effect=run):
            buddy.notify_mac({"notification": "test", "task": task}, Path(self.temp.name))
        self.assertEqual(seen["task"], task)
        self.assertFalse(list(Path(self.temp.name).glob("*.json")))

    def test_terminal_controls_are_removed(self):
        self.assertNotIn("\x1b", buddy.clean("hello\x1b]52;c;bad\x07"))
        self.assertEqual(buddy.clean("Å\u202eevil"), "Åevil")

    def test_ai_checkin_is_saved_shown_and_reused_on_retry(self):
        self.store.start("Measure throughput", 1, now=0)
        calls = []
        question = "What throughput did you measure at each batch size, or where did you get stuck?"
        def model(store, **kwargs):
            calls.append(kwargs)
            return {"reply": question, "action": "say", "task": "", "minutes": 0}
        def fail(*args):
            raise OSError("notification unavailable")
        with self.assertRaises(OSError):
            self.store.notify_due(fail, now=60, model=model)
        self.store.notify_due(self.notify, now=90, model=model)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["event"], "check_in")
        self.assertEqual(self.store.state()["checkin"], question)
        self.assertEqual(sum(m["content"] == question for m in self.store.history()), 1)
        output = io.StringIO()
        display = buddy.CheckinDisplay(self.store)
        with contextlib.redirect_stdout(output):
            self.assertTrue(display.show())
            self.assertFalse(display.show())
        self.assertIn(question, output.getvalue())
        self.store.message("user", "I measured all three sizes.")
        self.assertFalse(buddy.CheckinDisplay(self.store).show())

    def test_no_model_call_before_due_and_fallback_on_model_failure(self):
        self.store.start("Explain the KV-cache layout", 1, now=0)
        calls = []
        def fail(*args, **kwargs):
            calls.append(True)
            raise ValueError("offline")
        self.assertFalse(self.store.notify_due(self.notify, now=59, model=fail))
        self.assertEqual(calls, [])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertTrue(self.store.notify_due(self.notify, now=60, model=fail))
        self.assertIn("Explain the KV-cache layout", self.store.state()["checkin"])
        self.assertIn("?", self.store.state()["checkin"])

    def test_cancellation_during_generation_discards_checkin(self):
        self.store.start("Old task", 1, now=0)
        def model(store, **kwargs):
            store.finish()
            return {"reply": "How did the old task go?", "action": "say", "task": "", "minutes": 0}
        self.assertFalse(self.store.notify_due(self.notify, now=60, model=model))
        self.assertIsNone(self.store.state()["checkin"])
        self.assertEqual(self.sent, [])

    def test_snoozing_resets_the_question_and_answer_state(self):
        self.store.start("Task", 1, now=0)
        self.store.notify_due(self.notify, now=60)
        self.store.message("user", "Still working")
        self.store.snooze(1, now=60)
        self.assertIsNone(self.store.state()["checkin"])
        self.assertFalse(self.store.state()["answered"])
        self.store.notify_due(self.notify, now=120)
        self.assertTrue(self.store.state()["checkin"])

    def test_existing_delivered_reminder_gains_question_without_resending(self):
        self.store.start("Existing task", 1, now=0)
        with self.store.transaction():
            self.store.db.execute("UPDATE state SET sent=1")
        self.assertFalse(self.store.notify_due(self.notify, now=60))
        self.assertTrue(self.store.state()["checkin"])
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
