import threading
import time
import unittest

from dual_lobe import (
    DualLobeCoordinator,
    PROFILE_SCREEN_AWARE,
    ScreenObservation,
    handoff_matches,
    predict_boundary,
)


class DualLobeCoreTests(unittest.TestCase):
    def test_handoff_requires_visual_change_for_visual_batch(self):
        response = {"actions": [{"action": "click", "params": {"x": 10, "y": 10}}]}
        boundary = predict_boundary(response, "a-1")
        before = ScreenObservation(1.0, "same")
        after = ScreenObservation(2.0, "same")
        self.assertFalse(handoff_matches(boundary, before, after))
        self.assertTrue(
            handoff_matches(boundary, before, ScreenObservation(2.0, "changed"))
        )

    def test_b_prediction_overlaps_a_execution_and_commits_after_it(self):
        preview_started = threading.Event()
        execution_started = threading.Event()
        execution_finished = threading.Event()
        commit_after_execution = []

        screen_counter = {"value": 0}

        def capture():
            screen_counter["value"] += 1
            return {
                "captured_at": time.time(),
                "screen_hash": str(screen_counter["value"]),
            }

        def preview(current, boundary, observation):
            self.assertEqual(current.source_lobe, "A")
            preview_started.set()
            return {
                "actions": [{"action": "task_completed", "params": {}}],
                "current_state": {},
            }

        def execute(response):
            execution_started.set()
            self.assertTrue(preview_started.wait(1.0))
            time.sleep(0.02)
            execution_finished.set()

        def commit(batch, observation):
            commit_after_execution.append(execution_finished.is_set())
            return True

        coordinator = DualLobeCoordinator(
            preview_fn=preview,
            commit_fn=commit,
            execute_fn=execute,
            capture_fn=capture,
            fallback_fn=lambda: None,
            profile=PROFILE_SCREEN_AWARE,
            preview_timeout=1.0,
        )
        report = coordinator.run(
            {"actions": [{"action": "click", "params": {"x": 10, "y": 10}}]},
            max_batches=2,
        )

        self.assertTrue(execution_started.is_set())
        self.assertTrue(preview_started.is_set())
        self.assertEqual(commit_after_execution, [True])
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.lookahead_ready, 1)


if __name__ == "__main__":
    unittest.main()
