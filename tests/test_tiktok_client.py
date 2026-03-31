from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_client import TikTokAPIError, TikTokClient, TikTokRateLimitError


def _mock_response(data: dict, status: int = 200) -> MagicMock:
    body = json.dumps(data).encode("utf-8")
    mock = MagicMock()
    mock.read.return_value = body
    mock.status = status
    mock.headers = {}
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _raw_video(
    *,
    video_id: str = "v001",
    title: str = "Test Video",
    video_description: str = "A test",
    create_time: int = 1711900000,
    share_url: str = "https://www.tiktok.com/@user/video/v001",
    like_count: int = 100,
    view_count: int = 5000,
    share_count: int = 20,
    comment_count: int = 10,
) -> dict:
    return {
        "id": video_id,
        "title": title,
        "video_description": video_description,
        "create_time": create_time,
        "share_url": share_url,
        "like_count": like_count,
        "view_count": view_count,
        "share_count": share_count,
        "comment_count": comment_count,
    }


class RefreshAccessTokenTest(TestCase):
    @patch("tiktok_client.urlopen")
    def test_builds_correct_request_body(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"data": {"access_token": "new_token"}}
        )
        client = TikTokClient(
            client_key="test_key",
            client_secret="test_secret",
            refresh_token="test_refresh",
        )
        client.refresh_access_token()

        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        body = request.data.decode("utf-8")
        self.assertIn("grant_type=refresh_token", body)
        self.assertIn("refresh_token=test_refresh", body)
        self.assertIn("client_key=test_key", body)
        self.assertIn("client_secret=test_secret", body)

    @patch("tiktok_client.urlopen")
    def test_returns_access_token(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"data": {"access_token": "fresh_token"}}
        )
        client = TikTokClient(
            client_key="ck", client_secret="cs", refresh_token="rt"
        )
        token = client.refresh_access_token()
        self.assertEqual(token, "fresh_token")

    @patch("tiktok_client.urlopen")
    def test_raises_on_401(self, mock_urlopen: MagicMock) -> None:
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="https://open.tiktokapis.com/v2/oauth/token/",
            code=401,
            msg="Unauthorized",
            hdrs={},  # type: ignore[arg-type]
            fp=io.BytesIO(b"{}"),
        )
        client = TikTokClient(
            client_key="ck", client_secret="cs", refresh_token="rt"
        )
        with self.assertRaises(TikTokAPIError) as ctx:
            client.refresh_access_token()
        self.assertIn("401", str(ctx.exception))


class FetchUserVideosTest(TestCase):
    @patch("tiktok_client.urlopen")
    def test_builds_correct_request_with_auth_header(self, mock_urlopen: MagicMock) -> None:
        response_data = {"data": {"videos": [_raw_video()]}, "error": {"code": "ok"}}
        mock_urlopen.return_value = _mock_response(response_data)

        client = TikTokClient(
            client_key="ck", client_secret="cs", refresh_token="rt"
        )
        client._access_token = "my_token"
        client.fetch_user_videos(max_count=5)

        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        self.assertEqual(request.get_header("Authorization"), "Bearer my_token")

    @patch("tiktok_client.urlopen")
    def test_normalizes_video_list(self, mock_urlopen: MagicMock) -> None:
        raw = _raw_video(video_id="v123", title="Cool Video")
        response_data = {"data": {"videos": [raw]}, "error": {"code": "ok"}}
        mock_urlopen.return_value = _mock_response(response_data)

        client = TikTokClient(
            client_key="ck", client_secret="cs", refresh_token="rt"
        )
        client._access_token = "token"
        videos = client.fetch_user_videos()

        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0]["video_id"], "v123")
        self.assertEqual(videos[0]["title"], "Cool Video")
        self.assertIn("metrics", videos[0])
        self.assertIn("likes", videos[0]["metrics"])

    @patch("tiktok_client.urlopen")
    def test_handles_empty_video_list(self, mock_urlopen: MagicMock) -> None:
        response_data = {"data": {"videos": []}, "error": {"code": "ok"}}
        mock_urlopen.return_value = _mock_response(response_data)

        client = TikTokClient(
            client_key="ck", client_secret="cs", refresh_token="rt"
        )
        client._access_token = "token"
        videos = client.fetch_user_videos()
        self.assertEqual(videos, [])

    @patch("tiktok_client.urlopen")
    def test_raises_on_429(self, mock_urlopen: MagicMock) -> None:
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="https://open.tiktokapis.com/v2/video/list/",
            code=429,
            msg="Too Many Requests",
            hdrs={},  # type: ignore[arg-type]
            fp=io.BytesIO(b"{}"),
        )
        client = TikTokClient(
            client_key="ck", client_secret="cs", refresh_token="rt"
        )
        client._access_token = "token"
        with self.assertRaises(TikTokRateLimitError):
            client.fetch_user_videos()

    @patch("tiktok_client.urlopen")
    def test_raises_on_malformed_json(self, mock_urlopen: MagicMock) -> None:
        mock = MagicMock()
        mock.read.return_value = b"not json at all"
        mock.status = 200
        mock.__enter__ = lambda s: s
        mock.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock

        client = TikTokClient(
            client_key="ck", client_secret="cs", refresh_token="rt"
        )
        client._access_token = "token"
        with self.assertRaises(TikTokAPIError):
            client.fetch_user_videos()


class NormalizeVideoTest(TestCase):
    def test_maps_tiktok_fields_correctly(self) -> None:
        raw = _raw_video(
            video_id="v999",
            title="Mapped",
            video_description="desc",
            create_time=1711900000,
            share_url="https://www.tiktok.com/@u/video/v999",
            like_count=50,
            view_count=1000,
            share_count=5,
            comment_count=3,
        )
        client = TikTokClient(
            client_key="ck", client_secret="cs", refresh_token="rt"
        )
        normalized = client._normalize_video(raw)

        self.assertEqual(normalized["video_id"], "v999")
        self.assertEqual(normalized["title"], "Mapped")
        self.assertEqual(normalized["description"], "desc")
        self.assertEqual(normalized["create_time"], 1711900000)
        self.assertIn("created_at", normalized)
        self.assertEqual(normalized["share_url"], "https://www.tiktok.com/@u/video/v999")
        self.assertEqual(normalized["metrics"]["likes"], 50)
        self.assertEqual(normalized["metrics"]["views"], 1000)
        self.assertEqual(normalized["metrics"]["retweets"], 5)
        self.assertEqual(normalized["metrics"]["replies"], 3)


if __name__ == "__main__":
    main()
