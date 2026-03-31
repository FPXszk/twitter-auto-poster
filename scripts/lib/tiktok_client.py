from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, urlopen

logger = logging.getLogger(__name__)

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
VIDEO_LIST_URL = "https://open.tiktokapis.com/v2/video/list/"


class TikTokAPIError(Exception):
    """Base exception for TikTok API errors."""


class TikTokRateLimitError(TikTokAPIError):
    """Raised when the TikTok API rate limit is exceeded (HTTP 429)."""


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    compact = str(value).replace(",", "").strip()
    return int(compact) if compact.isdigit() else 0


class TikTokClient:
    """Client for the TikTok Open API v2."""

    def __init__(
        self,
        client_key: str = "",
        client_secret: str = "",
        refresh_token: str = "",
        *,
        opener: Any = None,
        timeout: int = 60,
    ) -> None:
        self.client_key = str(client_key or "").strip()
        self.client_secret = str(client_secret or "").strip()
        self.refresh_token = str(refresh_token or "").strip()
        self.timeout = timeout
        self._opener = opener
        self._access_token: str = ""

        if not self.client_key:
            raise ValueError("client_key is required")
        if not self.client_secret:
            raise ValueError("client_secret is required")
        if not self.refresh_token:
            raise ValueError("refresh_token is required")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, **kwargs: Any) -> TikTokClient:
        import os
        values = os.environ if env is None else env
        return cls(
            client_key=str(values.get("TIKTOK_CLIENT_KEY") or "").strip(),
            client_secret=str(values.get("TIKTOK_CLIENT_SECRET") or "").strip(),
            refresh_token=str(values.get("TIKTOK_REFRESH_TOKEN") or "").strip(),
            **kwargs,
        )

    def _do_request(self, request: Request) -> dict[str, Any]:
        try:
            if self._opener is not None:
                response = self._opener.open(request, timeout=self.timeout)
            else:
                response = urlopen(request, timeout=self.timeout)
            with response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise TikTokRateLimitError(
                    f"TikTok API rate limit exceeded (HTTP 429)"
                ) from error
            raise TikTokAPIError(
                f"TikTok API request failed with status {error.code}"
            ) from error
        except URLError as error:
            raise TikTokAPIError(
                f"TikTok API request failed: {error.reason}"
            ) from error
        except json.JSONDecodeError as error:
            raise TikTokAPIError(
                "TikTok API returned invalid JSON"
            ) from error

    def refresh_access_token(self) -> str:
        """POST to the TikTok OAuth token endpoint with refresh_token grant."""
        payload = urlencode(
            {
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }
        ).encode("utf-8")
        request = Request(
            TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        response = self._do_request(request)
        access_token = str(((response.get("data") or {}).get("access_token") or "")).strip()
        if not access_token:
            raise TikTokAPIError("TikTok token response did not include access_token")
        self._access_token = access_token
        return access_token

    def fetch_user_videos(
        self, max_count: int = 10, cursor: int | str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch user videos from the TikTok API, returning normalized video dicts."""
        if not self._access_token:
            self.refresh_access_token()

        body = {
            "max_count": int(max_count),
            "fields": [
                "id", "create_time", "title", "video_description",
                "share_url", "cover_image_url", "duration",
                "embed_link", "like_count", "comment_count",
                "share_count", "view_count",
            ],
        }
        if cursor is not None:
            body["cursor"] = int(cursor)

        request = Request(
            VIDEO_LIST_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        response = self._do_request(request)
        data = response.get("data")
        if not isinstance(data, Mapping):
            raise TikTokAPIError("TikTok video list response is missing data")
        videos = data.get("videos")
        if videos is None:
            raise TikTokAPIError("TikTok video list response is missing videos")
        if not isinstance(videos, list):
            raise TikTokAPIError("TikTok video list response videos is not a list")
        return [self._normalize_video(item) for item in videos]

    def _normalize_video(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize a TikTok video payload to the pipeline-standard format."""
        video_id = str(raw.get("id") or "").strip()
        create_time = _coerce_int(raw.get("create_time"))
        try:
            created_at = datetime.fromtimestamp(create_time, tz=timezone.utc).isoformat()
        except (OSError, ValueError, OverflowError):
            created_at = str(raw.get("create_time") or "")

        return {
            "video_id": video_id,
            "id": video_id,
            "title": str(raw.get("title") or "").strip(),
            "description": str(raw.get("video_description") or "").strip(),
            "text": str(raw.get("title") or raw.get("video_description") or "").strip(),
            "create_time": create_time,
            "created_at": created_at,
            "share_url": str(raw.get("share_url") or "").strip(),
            "video_page_url": str(raw.get("share_url") or raw.get("embed_link") or "").strip(),
            "cover_image_url": str(raw.get("cover_image_url") or "").strip(),
            "duration_seconds": _coerce_int(raw.get("duration")),
            "metrics": {
                "likes": _coerce_int(raw.get("like_count")),
                "views": _coerce_int(raw.get("view_count")),
                "retweets": _coerce_int(raw.get("share_count")),
                "replies": _coerce_int(raw.get("comment_count")),
            },
            "author": {
                "username": "",
                "platform_user_id": "",
            },
        }

    # Backward-compatible alias for tiktok_pipeline.py
    normalize_video_item = _normalize_video
