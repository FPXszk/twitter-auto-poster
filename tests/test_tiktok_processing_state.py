from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_processing_state import (
    begin_attempt,
    create_initial_state,
    current_attempt,
    load_processing_state,
    processing_lock,
    record_failure,
    save_processing_state,
    should_skip_as_exported,
    transition_state,
)


class TikTokProcessingStateTest(unittest.TestCase):
    def test_transitions_and_failure_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            payload = create_initial_state(
                video_id="123",
                input_url="https://www.tiktok.com/@u/video/123",
                canonical_url="https://www.tiktok.com/@u/video/123",
            )
            begin_attempt(payload, force=False)
            transition_state(payload, "DOWNLOADED", artifacts={"normalized_path": "/tmp/n.mp4"})
            record_failure(
                payload,
                phase="DOWNLOADED",
                category="RuntimeError",
                message="boom",
                retryable=False,
            )
            save_processing_state(state_path, payload)

            loaded = load_processing_state(state_path)
            self.assertEqual(loaded["current_state"], "FAILED")
            self.assertEqual(loaded["failure"]["message"], "boom")
            self.assertEqual(current_attempt(loaded)["final_state"], "FAILED")

    def test_should_skip_exported_without_force(self) -> None:
        payload = create_initial_state(
            video_id="123",
            input_url="https://www.tiktok.com/@u/video/123",
            canonical_url="https://www.tiktok.com/@u/video/123",
        )
        begin_attempt(payload, force=False)
        payload["export"] = {"ready_to_post_path": "/tmp/ready_to_post.mp4"}
        transition_state(payload, "EXPORTED")
        self.assertTrue(should_skip_as_exported(payload, force=False))
        self.assertFalse(should_skip_as_exported(payload, force=True))

    def test_processing_lock_blocks_second_holder(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "video.lock"
            with processing_lock(lock_path):
                with self.assertRaises(RuntimeError):
                    with processing_lock(lock_path):
                        self.fail("nested lock should not succeed")


if __name__ == "__main__":
    unittest.main()
