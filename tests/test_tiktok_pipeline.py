from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'lib'))

from tiktok_pipeline import run_tiktok_pipeline, write_pipeline_result


class FakeClient:
    def __init__(self, videos):
        self.videos = videos

    def fetch_user_videos(self, max_count):
        return list(self.videos)


class TikTokPipelineTest(unittest.TestCase):
    def write_accounts(self, root: Path) -> Path:
        path = root / 'accounts.yaml'
        path.write_text(
            yaml.safe_dump(
                {
                    'defaults': {'dry_run': True, 'max_candidates': 1, 'single_post_max_length': 280, 'score_weights': {'likes': 1, 'retweets': 1, 'replies': 1, 'views': 1, 'velocity': 0, 'freshness': 0}, 'filters': {'max_age_hours': 168, 'required_terms': [], 'exclude_keywords': []}},
                    'accounts': {'tiktok': {'dry_run': True, 'state_file': 'state/tiktok-posted.txt', 'allowlist_path': str(root / 'allowlist.yaml'), 'download_dir': 'downloads'}}
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding='utf-8',
        )
        return path

    def write_allowlist(self, root: Path, consent_type: str = 'owner', enabled: bool = True) -> None:
        (root / 'allowlist.yaml').write_text(
            yaml.safe_dump(
                {'creators': [{'platform_user_id': 'owner-id', 'tiktok_username': 'exampleowner', 'enabled': enabled, 'consent_type': consent_type, 'consent_reference': 'owned', 'expires_at': '2099-01-01T00:00:00Z', 'max_results': 10}]},
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding='utf-8',
        )

    def sample_video(self):
        return {'id': 'video-1', 'title': 'owner video', 'description': 'caption', 'created_at': '2026-03-31T00:00:00Z', 'video_page_url': 'https://www.tiktok.com/@u/video/1', 'metrics': {'likes': 10, 'retweets': 2, 'replies': 3, 'views': 100}}

    def test_pipeline_selects_best_owner_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            accounts = self.write_accounts(root)
            self.write_allowlist(root)
            calls = []
            def fake_post_video(tweet_text, video_path, dry_run):
                calls.append((tweet_text, str(video_path), dry_run))
                return {'ok': True, 'message': 'posted', 'data': {'action': 'dry_run_video', 'dry_run': dry_run}}
            payload = run_tiktok_pipeline(
                category='tiktok',
                config_path=accounts,
                output_dir=root,
                dry_run=True,
                client=FakeClient([self.sample_video()]),
                downloader=lambda url, output_dir: root / 'download.mp4',
                post_video=fake_post_video,
            )
            self.assertTrue(payload['ok'])
            self.assertEqual(payload['data']['candidate_id'], 'video-1')
            self.assertEqual(len(calls), 1)

    def test_pipeline_rejects_non_owner_allowlist_entries_for_live_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            accounts = self.write_accounts(root)
            self.write_allowlist(root, consent_type='explicit')
            payload = run_tiktok_pipeline(
                category='tiktok',
                config_path=accounts,
                output_dir=root,
                dry_run=False,
                client=FakeClient([self.sample_video()]),
                downloader=lambda url, output_dir: root / 'download.mp4',
                post_video=lambda **kwargs: {'ok': True, 'message': 'posted', 'data': {'dry_run': False}},
            )
            self.assertEqual(payload['data']['candidate_count'], 0)

    def test_pipeline_skips_already_posted_video_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            accounts = self.write_accounts(root)
            self.write_allowlist(root)
            state_dir = root / 'state'
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / 'tiktok-posted.txt').write_text('video-1\n', encoding='utf-8')
            payload = run_tiktok_pipeline(
                category='tiktok',
                config_path=accounts,
                output_dir=root,
                dry_run=False,
                client=FakeClient([self.sample_video()]),
                downloader=lambda url, output_dir: root / 'download.mp4',
                post_video=lambda **kwargs: {'ok': True, 'message': 'posted', 'data': {'dry_run': False}},
            )
            self.assertEqual(payload['data']['candidate_count'], 0)

    def test_pipeline_dry_run_does_not_mark_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            accounts = self.write_accounts(root)
            self.write_allowlist(root)
            payload = run_tiktok_pipeline(
                category='tiktok',
                config_path=accounts,
                output_dir=root,
                dry_run=True,
                client=FakeClient([self.sample_video()]),
                downloader=lambda url, output_dir: root / 'download.mp4',
                post_video=lambda **kwargs: {'ok': True, 'message': 'posted', 'data': {'dry_run': True}},
            )
            self.assertTrue(payload['ok'])
            self.assertFalse((root / 'state' / 'tiktok-posted.txt').exists())

    def test_write_pipeline_result_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'result.json'
            write_pipeline_result(path, {'ok': True, 'data': {'x': 1}, 'message': 'ok'})
            payload = json.loads(path.read_text(encoding='utf-8'))
            self.assertTrue(payload['ok'])

    def test_pipeline_rejects_multiple_enabled_creators(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            accounts = self.write_accounts(root)
            (root / 'allowlist.yaml').write_text(
                yaml.safe_dump(
                    {
                        'creators': [
                            {'platform_user_id': 'owner-id-1', 'tiktok_username': 'ownerone', 'enabled': True, 'consent_type': 'owner', 'consent_reference': 'owned', 'expires_at': '2099-01-01T00:00:00Z', 'max_results': 10},
                            {'platform_user_id': 'owner-id-2', 'tiktok_username': 'ownertwo', 'enabled': True, 'consent_type': 'owner', 'consent_reference': 'owned', 'expires_at': '2099-01-01T00:00:00Z', 'max_results': 10},
                        ]
                    },
                    sort_keys=False,
                    allow_unicode=True,
                ),
                encoding='utf-8',
            )
            with self.assertRaisesRegex(RuntimeError, 'exactly one enabled TikTok allowlist creator'):
                run_tiktok_pipeline(
                    category='tiktok',
                    config_path=accounts,
                    output_dir=root,
                    dry_run=False,
                    client=FakeClient([self.sample_video()]),
                    downloader=lambda url, output_dir: root / 'download.mp4',
                    post_video=lambda **kwargs: {'ok': True, 'message': 'posted', 'data': {'dry_run': False}},
                )


if __name__ == '__main__':
    unittest.main()
