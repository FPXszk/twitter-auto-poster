from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
CONVERSATION_TERMS = ("？", "?", "注目", "ポイント", "理由", "まとめ", "シナリオ", "見方")
NEGATIVE_TERMS = ("悲報", "最悪", "クソ", "暴落", "絶望", "死ね")


def current_jst_datetime() -> datetime:
    return datetime.now(JST)


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).astimezone(JST)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).astimezone(JST)
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _normalize_score(value: float, maximum: float) -> float:
    return round(_clamp(value, 0.0, maximum), 1)


def _hashtags_in_text(text: str) -> int:
    return len(re.findall(r"#[^\s#]+", text))


def _contains_number_hook(text: str) -> bool:
    return bool(re.search(r"[0-9０-９%％¥￥]", text))


def _has_external_link(text: str, urls: Sequence[object]) -> bool:
    if urls:
        return True
    return "http://" in text or "https://" in text


def analyze_account_score(
    user: Mapping[str, object],
    recent_posts: Sequence[Mapping[str, object]],
    *,
    assume_premium: bool,
    now: datetime | None = None,
) -> dict[str, object]:
    now_jst = (now or current_jst_datetime()).astimezone(JST)

    followers = _safe_int(user.get("followers"))
    following = _safe_int(user.get("following"))
    account_created_at = _parse_datetime(user.get("createdAt"))
    account_age_days = max((now_jst - account_created_at).days, 0) if account_created_at is not None else 0

    age_score = 15.0 * min(account_age_days / 30.0, 1.0)

    ratio = followers / max(following, 1)
    ratio_score = min(ratio / 1.0, 1.0) * 10.0
    follower_scale = min(math.log10(max(followers, 1) + 1) / 3.0, 1.0) * 10.0
    network_score = ratio_score + follower_scale

    post_analyses: list[dict[str, object]] = []
    posts_last_24h = 0
    posts_last_7d = 0
    link_posts = 0
    hashtag_spam_posts = 0
    negative_posts = 0
    views_per_follower: list[float] = []
    interaction_rates: list[float] = []

    seven_days_ago = now_jst - timedelta(days=7)
    one_day_ago = now_jst - timedelta(days=1)

    for post in recent_posts:
        text = str(post.get("text") or "")
        metrics = post.get("metrics") if isinstance(post.get("metrics"), Mapping) else {}
        urls = post.get("urls") if isinstance(post.get("urls"), Sequence) and not isinstance(post.get("urls"), (str, bytes)) else []
        media = post.get("media") if isinstance(post.get("media"), Sequence) and not isinstance(post.get("media"), (str, bytes)) else []
        created_at = _parse_datetime(post.get("createdAtISO") or post.get("createdAt") or post.get("time"))
        if created_at is not None and created_at >= seven_days_ago:
            posts_last_7d += 1
        if created_at is not None and created_at >= one_day_ago:
            posts_last_24h += 1

        hashtags = _hashtags_in_text(text)
        has_link = _has_external_link(text, urls)
        has_negative_term = any(term in text for term in NEGATIVE_TERMS)
        hook_with_numbers = _contains_number_hook(text)
        has_structure = "\n" in text or 40 <= len(text) <= 280
        has_conversation_hook = any(term in text for term in CONVERSATION_TERMS)
        clean_hashtags = hashtags < 3
        media_bonus = bool(media)

        views = _safe_float(metrics.get("views"))
        interactions = (
            _safe_float(metrics.get("likes"))
            + _safe_float(metrics.get("retweets"))
            + _safe_float(metrics.get("replies"))
            + _safe_float(metrics.get("quotes"))
            + _safe_float(metrics.get("bookmarks"))
        )
        views_per_follower.append(views / max(followers, 1))
        interaction_rates.append(interactions / max(views, 1.0))

        if has_link:
            link_posts += 1
        if not clean_hashtags:
            hashtag_spam_posts += 1
        if has_negative_term:
            negative_posts += 1

        post_score = 0.0
        if hook_with_numbers:
            post_score += 5.0
        if has_structure:
            post_score += 5.0
        if not has_link:
            post_score += 5.0
        if clean_hashtags:
            post_score += 5.0
        if has_conversation_hook:
            post_score += 5.0
        if media_bonus:
            post_score += 1.5

        post_analyses.append(
            {
                "id": str(post.get("id") or ""),
                "text": text,
                "created_at": created_at.isoformat() if created_at is not None else "",
                "views": views,
                "interactions": interactions,
                "score": round(min(post_score, 25.0), 1),
                "has_number_hook": hook_with_numbers,
                "has_structure": has_structure,
                "has_link": has_link,
                "clean_hashtags": clean_hashtags,
                "has_conversation_hook": has_conversation_hook,
                "has_negative_term": has_negative_term,
            }
        )

    posts_per_day = posts_last_7d / 7.0
    if posts_last_7d == 0:
        cadence_score = 2.0
    elif posts_per_day < 0.3:
        cadence_score = 6.0
    elif posts_per_day < 1.0:
        cadence_score = 10.0
    elif posts_per_day <= 5.0:
        cadence_score = 12.0
    elif posts_per_day <= 10.0:
        cadence_score = 6.0
    else:
        cadence_score = 0.0
    if posts_last_24h > 0:
        cadence_score += 3.0

    content_score = _mean([_safe_float(item["score"]) for item in post_analyses])
    average_view_ratio = _mean(views_per_follower)
    average_interaction_rate = _mean(interaction_rates)
    engagement_score = min(average_view_ratio / 3.0, 1.0) * 10.0 + min(average_interaction_rate / 0.02, 1.0) * 5.0
    premium_score = 10.0 if assume_premium else 0.0

    penalties = 0.0
    warnings: list[str] = []
    suggestions: list[str] = []

    if following > 500 and (following / max(followers, 1)) > 0.6:
        penalties += 10.0
        warnings.append("フォロー数が多くフォロー/フォロワー比も高いため、TweepCred 低下リスクがあります。")
        suggestions.append("フォロー数とフォロー/フォロワー比を見直してください。")

    link_rate = link_posts / max(len(post_analyses), 1)
    if link_rate >= 0.3:
        penalties += 8.0
        warnings.append("最近の投稿でリンク比率が高く、本文リンクのリーチ減ペナルティが想定されます。")
        suggestions.append("リンクは本文ではなく返信側に回してください。")

    hashtag_spam_rate = hashtag_spam_posts / max(len(post_analyses), 1)
    if hashtag_spam_rate >= 0.3:
        penalties += 8.0
        warnings.append("ハッシュタグ過多の投稿が多く、表示抑制リスクがあります。")
        suggestions.append("ハッシュタグは原則使わない運用に寄せてください。")

    if posts_per_day > 10.0:
        penalties += 10.0
        warnings.append("投稿頻度が高すぎるため、低エンゲージメント連投ペナルティの懸念があります。")
        suggestions.append("1日の投稿数を抑えて反応の良い投稿に集中してください。")

    negative_rate = negative_posts / max(len(post_analyses), 1)
    if negative_rate >= 0.3:
        penalties += 6.0
        warnings.append("ネガティブ寄りの文面が一定割合あり、センチメント面で不利です。")
        suggestions.append("ポジティブか建設的な言い回しへ寄せてください。")

    if account_age_days < 30:
        suggestions.append("アカウント年齢がまだ若いため、日次継続と返信運用で信頼シグナルを積み上げてください。")
    if content_score < 15.0:
        suggestions.append("冒頭140字に数字・結論・問いかけを入れ、続きを読みたくなるフックを強めてください。")
    if engagement_score < 7.5:
        suggestions.append("返信・引用されやすい論点を増やし、投稿後1時間の返信反応を強化してください。")

    raw_total = age_score + network_score + cadence_score + content_score + engagement_score + premium_score - penalties
    total_score = _normalize_score(raw_total, 100.0)

    if total_score >= 80.0:
        distribution = "strong"
    elif total_score >= 65.0:
        distribution = "healthy"
    elif total_score >= 45.0:
        distribution = "limited"
    else:
        distribution = "fragile"

    return {
        "score": total_score,
        "distribution": distribution,
        "components": {
            "account_age": round(age_score, 1),
            "network": round(network_score, 1),
            "cadence": round(cadence_score, 1),
            "content": round(content_score, 1),
            "engagement": round(engagement_score, 1),
            "premium_assumption": round(premium_score, 1),
            "penalties": round(penalties, 1),
        },
        "metrics": {
            "followers": followers,
            "following": following,
            "account_age_days": account_age_days,
            "recent_post_count": len(post_analyses),
            "posts_last_24h": posts_last_24h,
            "posts_last_7d": posts_last_7d,
            "posts_per_day_7d": round(posts_per_day, 2),
            "average_view_per_follower": round(average_view_ratio, 2),
            "average_interaction_rate": round(average_interaction_rate, 4),
            "link_rate": round(link_rate, 2),
            "hashtag_spam_rate": round(hashtag_spam_rate, 2),
            "negative_rate": round(negative_rate, 2),
        },
        "warnings": warnings,
        "suggestions": suggestions[:5],
        "post_analyses": post_analyses,
    }
