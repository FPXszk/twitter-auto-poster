# TikTok Pipeline Phase E-G 実装計画

## 概要
TikTok動画パイプラインの Phase E-G を実装する。パイプラインオーケストレーター、テスト、GitHub Actions ワークフローの作成。

## 変更ファイル一覧

### 変更
- `config/accounts.yaml` — tiktok アカウントブロックを更新（summary_provider 追加、score_weights/filters 変更）

### 削除 → 再作成
- `scripts/lib/tiktok_pipeline.py` — env ベースの新 API で書き直し（~260行）
- `tests/test_tiktok_pipeline.py` — patch ベースの統合テスト7件（~280行）
- `.github/workflows/post_tiktok.yml` — post_buz.yml パターンに合わせて拡充（~200行）

### 変更しないファイル
- `scripts/lib/tiktok_allowlist.py`
- `scripts/lib/tiktok_state.py`
- `scripts/lib/tiktok_client.py`
- `scripts/lib/tiktok_filters.py`
- `scripts/lib/tiktok_scoring.py`
- `scripts/lib/tiktok_downloader.py`
- 既存テスト6ファイル（66テスト）

## 実装ステップ

- [ ] 1. `config/accounts.yaml` の tiktok ブロックを新仕様に置換
- [ ] 2. `scripts/lib/tiktok_pipeline.py` を削除 → 新 API（env パラメータ、詳細 payload）で再作成
- [ ] 3. `tests/test_tiktok_pipeline.py` を削除 → 7テストケースで再作成
- [ ] 4. `.github/workflows/post_tiktok.yml` を削除 → post_buz.yml パターンで再作成
- [ ] 5. パイプラインテスト実行 → 全パス確認
- [ ] 6. 全 TikTok テスト（7モジュール）実行 → 既存66件 + 新規7件 = 73件以上パス確認

## テスト戦略（RED → GREEN → REFACTOR）
1. RED: test_tiktok_pipeline.py の7テスト作成 → 実装前なので全失敗
2. GREEN: tiktok_pipeline.py 実装 → テスト全パス
3. REFACTOR: 全テスト通過を維持しつつコード改善

## テストケース
1. `test_pipeline_selects_best_owner_video` — 2動画のスコア比較
2. `test_pipeline_rejects_non_owner_for_live_run` — explicit consent 拒否
3. `test_pipeline_skips_expired_allowlist_entries` — 期限切れ creator スキップ
4. `test_pipeline_skips_already_posted_video_ids` — 投稿済み動画スキップ
5. `test_pipeline_dry_run_does_not_post_or_mark_state` — dry_run で投稿・state 不変
6. `test_pipeline_handles_download_failure` — ダウンロード失敗のエラーハンドリング
7. `test_pipeline_passes_mp4_to_post_video` — post_video_tweet への正しい引数検証

## リスク
- post_video.py の import 依存（summary_common, twikit_compat）: pipeline 内で直接 import するため影響なし
- 既存テスト66件との互換: 変更対象外モジュールは一切触らないため安全

## 検証コマンド
```bash
python -m unittest tests.test_tiktok_pipeline -v
python -m unittest tests.test_tiktok_allowlist tests.test_tiktok_state tests.test_tiktok_client tests.test_tiktok_filters tests.test_tiktok_scoring tests.test_tiktok_downloader tests.test_tiktok_pipeline -v
```
