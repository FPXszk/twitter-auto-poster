# TikTok Video Pipeline — Phase A-D (Core Modules & Tests)

**Created:** 2026-03-31 18:48
**Completed:** 2026-03-31 18:55
**Status:** Complete

## 概要

TikTokリポスト機能の基盤モジュール（allowlist, state, client, filters, scoring, downloader）とそのテストをTDD方式で実装。

## 変更ファイル一覧

### 新規作成 — Config
- [x] `config/tiktok_allowlist.yaml` — 許可リストYAMLテンプレート

### 新規作成 — テスト（64テスト、全パス）
- [x] `tests/test_tiktok_allowlist.py` — 18 tests
- [x] `tests/test_tiktok_state.py` — 8 tests
- [x] `tests/test_tiktok_client.py` — 9 tests
- [x] `tests/test_tiktok_filters.py` — 10 tests
- [x] `tests/test_tiktok_scoring.py` — 6 tests
- [x] `tests/test_tiktok_downloader.py` — 11 tests (2 extra beyond spec)

### 新規作成 — モジュール
- [x] `scripts/lib/tiktok_allowlist.py` — YAML読込、バリデーション、許可判定
- [x] `scripts/lib/tiktok_state.py` — 行ベース状態ファイル管理
- [x] `scripts/lib/tiktok_client.py` — TikTok API v2クライアント（urllib）
- [x] `scripts/lib/tiktok_filters.py` — TikTok固有フィルタリング
- [x] `scripts/lib/tiktok_scoring.py` — post_scoring.calculate_score()再利用
- [x] `scripts/lib/tiktok_downloader.py` — yt-dlp経由ダウンロード＋検証

## 結果

- 全410テストパス（既存テスト含む）
- tiktok_pipeline.py / test_tiktok_pipeline.py との後方互換性維持
