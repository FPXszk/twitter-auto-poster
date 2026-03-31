from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import unittest

import yaml

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_pipeline import run_tiktok_pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_accounts(root: Path, *, allowlist_path: str | None = None) -> Path:
    """Write a minimal accounts.yaml and return its path."""
    al_path = allowlist_path or str(root / "allowlist.yaml")
    path = root / "accounts.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "defaults": {
                    "dry_run": True,
                    "max_candidates": 1,
                    "single_post_max_length": 280,
                    "score_weights": {
                        "likes": 1, "retweets": 1, "replies": 1,
                        "views": 1, "velocity": 0, "freshness": 0,
                        "image_bonus": 0, "author_virality": 0,
                    },
                    "filters": {
                        "max_age_hours": 720,
                        "required_terms": [],
                        "exclude_keywords": [],
                    },
                },
                "accounts": {
                    "tiktok": {
                        "dry_run": True,
                        "state_file": "state/tiktok-posted.txt",
                        "allowlist_path": al_path,
                    },
                },
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


def _write_allowlist(
    root: Path,
    *,
    consent_type: str = "owner",
    enabled: bool = True,
    expires_at: str = "2099-01-01T00:00:00Z",
    platform_user_id: str = "owner-id",
    username: str = "exampleowner",
) -> None:
    """Write an allowlist.yaml with a single creator."""
    (root / "allowlist.yaml").write_text(
        yaml.safe_dump(
            {
                "creators": [
                    {
                        "platform_user_id": platform_user_id,
                        "tiktok_username": username,
                        "enabled": enabled,
                        "consent_type": consent_type,
                        "consent_reference": "owned",
                        "expires_at": expires_at,
                        "max_results": 10,
                    },
                ],
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def _make_video(
    *,
    video_id: str = "video-1",
    title: str = "Great TikTok clip",
    description: str = "caption text",
    likes: int = 500,
    views: int = 10000,
    retweets: int = 50,
    replies: int = 30,
) -> dict:
    return {
        "id": video_id,
        "video_id": video_id,
        "title": title,
        "description": description,
        "text": title,
        "created_at": "2026-03-31T00:00:00+00:00",
        "create_time": 1743379200,
        "share_url": f"https://www.tiktok.com/@u/video/{video_id}",
        "video_page_url": f"https://www.tiktok.com/@u/video/{video_id}",
        "metrics": {
            "likes": likes,
            "views": views,
            "retweets": retweets,
            "replies": replies,
        },
        "author": {"username": "", "platform_user_id": ""},
    }


FAKE_ENV = {
    "TIKTOK_CLIENT_KEY": "test-key",
    "TIKTOK_CLIENT_SECRET": "test-secret",
    "TIKTOK_REFRESH_TOKEN": "test-token",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TikTokPipelineTest(unittest.TestCase):
    """Integration tests for the TikTok pipeline orchestrator."""

    # 1 — selects the highest-score video from two candidates
    @patch("tiktok_pipeline.post_video_tweet")
    @patch("tiktok_pipeline.download_tiktok_video")
    @patch("tiktok_pipeline.TikTokClient")
    def test_pipeline_selects_best_owner_video(
        self, mock_client_cls, mock_download, mock_post
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts = _write_accounts(root)
            _write_allowlist(root)

            low = _make_video(video_id="low-1", likes=10, views=100, retweets=1, replies=1)
            high = _make_video(video_id="high-1", likes=5000, views=100000, retweets=500, replies=300)
            fake_client = MagicMock()
            fake_client.fetch_user_videos.return_value = [low, high]
            mock_client_cls.from_env.return_value = fake_client

            mock_download.return_value = root / "video.mp4"
            mock_post.return_value = {
                "ok": True,
                "message": "posted",
                "data": {"action": "dry_run_video", "dry_run": True},
            }

            result = run_tiktok_pipeline(
                category="tiktok",
                config_path=accounts,
                output_dir=root,
                dry_run=True,
                env=FAKE_ENV,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["data"]["selected_video_id"], "high-1")
            self.assertEqual(result["data"]["candidates_fetched"], 2)
            self.assertGreaterEqual(result["data"]["candidates_scored"], 1)

    # 2 — explicit consent_type creator rejected in live mode
    @patch("tiktok_pipeline.post_video_tweet")
    @patch("tiktok_pipeline.download_tiktok_video")
    @patch("tiktok_pipeline.TikTokClient")
    def test_pipeline_rejects_non_owner_for_live_run(
        self, mock_client_cls, mock_download, mock_post
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts = _write_accounts(root)
            _write_allowlist(root, consent_type="explicit")

            fake_client = MagicMock()
            fake_client.fetch_user_videos.return_value = [_make_video()]
            mock_client_cls.from_env.return_value = fake_client

            result = run_tiktok_pipeline(
                category="tiktok",
                config_path=accounts,
                output_dir=root,
                dry_run=False,
                env=FAKE_ENV,
            )

            self.assertTrue(result["ok"])
            self.assertIn("no eligible", result["message"])
            mock_post.assert_not_called()

    # 3 — expired creator skipped
    @patch("tiktok_pipeline.post_video_tweet")
    @patch("tiktok_pipeline.download_tiktok_video")
    @patch("tiktok_pipeline.TikTokClient")
    def test_pipeline_skips_expired_allowlist_entries(
        self, mock_client_cls, mock_download, mock_post
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts = _write_accounts(root)
            _write_allowlist(root, expires_at="2020-01-01T00:00:00Z")

            fake_client = MagicMock()
            fake_client.fetch_user_videos.return_value = [_make_video()]
            mock_client_cls.from_env.return_value = fake_client

            result = run_tiktok_pipeline(
                category="tiktok",
                config_path=accounts,
                output_dir=root,
                dry_run=True,
                env=FAKE_ENV,
            )

            self.assertTrue(result["ok"])
            self.assertIn("no eligible", result["message"])
            mock_post.assert_not_called()

    # 4 — already-posted video skipped
    @patch("tiktok_pipeline.post_video_tweet")
    @patch("tiktok_pipeline.download_tiktok_video")
    @patch("tiktok_pipeline.TikTokClient")
    def test_pipeline_skips_already_posted_video_ids(
        self, mock_client_cls, mock_download, mock_post
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts = _write_accounts(root)
            _write_allowlist(root)

            state_dir = root / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "tiktok-posted.txt").write_text(
                "video-1\n", encoding="utf-8"
            )

            fake_client = MagicMock()
            fake_client.fetch_user_videos.return_value = [_make_video()]
            mock_client_cls.from_env.return_value = fake_client

            result = run_tiktok_pipeline(
                category="tiktok",
                config_path=accounts,
                output_dir=root,
                dry_run=True,
                env=FAKE_ENV,
            )

            self.assertTrue(result["ok"])
            self.assertIn("no eligible", result["message"])
            mock_post.assert_not_called()

    # 5 — dry_run does not post or update state
    @patch("tiktok_pipeline.post_video_tweet")
    @patch("tiktok_pipeline.download_tiktok_video")
    @patch("tiktok_pipeline.TikTokClient")
    def test_pipeline_dry_run_does_not_post_or_mark_state(
        self, mock_client_cls, mock_download, mock_post
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts = _write_accounts(root)
            _write_allowlist(root)

            fake_client = MagicMock()
            fake_client.fetch_user_videos.return_value = [_make_video()]
            mock_client_cls.from_env.return_value = fake_client
            mock_download.return_value = root / "video.mp4"
            mock_post.return_value = {
                "ok": True,
                "message": "dry run",
                "data": {"action": "dry_run_video", "dry_run": True},
            }

            result = run_tiktok_pipeline(
                category="tiktok",
                config_path=accounts,
                output_dir=root,
                dry_run=True,
                env=FAKE_ENV,
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["data"]["dry_run"])
            # post_video_tweet is called (for validation) but with dry_run=True
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            self.assertTrue(kwargs["dry_run"])
            # state file must NOT be created
            state_file = root / "state" / "tiktok-posted.txt"
            self.assertFalse(state_file.exists())

    # 6 — download failure returns graceful error
    @patch("tiktok_pipeline.post_video_tweet")
    @patch("tiktok_pipeline.download_tiktok_video")
    @patch("tiktok_pipeline.TikTokClient")
    def test_pipeline_handles_download_failure(
        self, mock_client_cls, mock_download, mock_post
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts = _write_accounts(root)
            _write_allowlist(root)

            fake_client = MagicMock()
            fake_client.fetch_user_videos.return_value = [_make_video()]
            mock_client_cls.from_env.return_value = fake_client
            mock_download.side_effect = RuntimeError("yt-dlp crashed")

            result = run_tiktok_pipeline(
                category="tiktok",
                config_path=accounts,
                output_dir=root,
                dry_run=True,
                env=FAKE_ENV,
            )

            self.assertFalse(result["ok"])
            self.assertIn("Download failed", result["message"])
            mock_post.assert_not_called()

    # 7 — correct args passed to post_video_tweet
    @patch("tiktok_pipeline.post_video_tweet")
    @patch("tiktok_pipeline.download_tiktok_video")
    @patch("tiktok_pipeline.TikTokClient")
    def test_pipeline_passes_mp4_to_post_video(
        self, mock_client_cls, mock_download, mock_post
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts = _write_accounts(root)
            _write_allowlist(root)

            video = _make_video(title="Test clip")
            fake_client = MagicMock()
            fake_client.fetch_user_videos.return_value = [video]
            mock_client_cls.from_env.return_value = fake_client

            mp4_path = root / "downloaded.mp4"
            mock_download.return_value = mp4_path
            mock_post.return_value = {
                "ok": True,
                "message": "posted",
                "data": {"action": "dry_run_video", "dry_run": True},
            }

            run_tiktok_pipeline(
                category="tiktok",
                config_path=accounts,
                output_dir=root,
                dry_run=True,
                env=FAKE_ENV,
            )

            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            self.assertEqual(kwargs["video_path"], mp4_path)
            self.assertIn("Test clip", kwargs["tweet_text"])
            self.assertTrue(kwargs["dry_run"])

    # 8 — fetch failure returns error when all creators fail
    @patch("tiktok_pipeline.post_video_tweet")
    @patch("tiktok_pipeline.download_tiktok_video")
    @patch("tiktok_pipeline.TikTokClient")
    def test_pipeline_returns_error_when_all_creators_fail_to_fetch(
        self, mock_client_cls, mock_download, mock_post
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            accounts = _write_accounts(root)
            _write_allowlist(root)

            mock_client_cls.from_env.side_effect = ValueError("client_key is required")

            result = run_tiktok_pipeline(
                category="tiktok",
                config_path=accounts,
                output_dir=root,
                dry_run=True,
                env={},
            )

            self.assertFalse(result["ok"])
            self.assertIn("failed to fetch", result["message"].lower())


if __name__ == "__main__":
    unittest.main()
