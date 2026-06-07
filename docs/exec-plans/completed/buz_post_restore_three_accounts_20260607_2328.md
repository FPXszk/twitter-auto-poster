# Buz Post Restore Three Accounts 20260607_2328

## 変更対象ファイル

- `.github/workflows/post_buz.yml`
- `scripts/lib/posting_window.py`
- `config/accounts.yaml`
- `config/sources.yaml`
- `tests/test_posting_window.py`
- `tests/test_sources_config.py`
- 必要なら関連テストを最小限追加・更新

## 実装内容

- `post_buz` の定期実行を日本時間 `08:00` `12:30` `21:00` の1日3回に変更する
- `buz` の対象ソースを `@ql_7mxa` `@yaruki_nash2` `@rmiqx_` のみに限定する
- `buz` の本文生成を AI 要約なしの raw 投稿へ切り替える
- `buz` の Copilot 依存返信も無効化し、投稿確認用のシンプルなワークフローに戻す
- 設定変更に合わせて時刻判定テストとソース設定テストを更新する

## 影響範囲

- 影響対象は `buz` カテゴリの自動投稿のみ
- `pic` `news` `tiktok` 系の設定やワークフローは変更しない
- 候補選定ロジックそのものは変更せず、投稿本文の生成方式のみ raw に切り替える

## テスト方針

- RED: 先に `tests/test_posting_window.py` と `tests/test_sources_config.py` を新仕様に合わせて更新し、失敗を確認する
- GREEN: 設定とワークフロー実装を変更して対象テストを通す
- REFACTOR: 追加差分が不要に広がっていないか見直す
- 実行コマンド:
  - `python3 -m unittest tests.test_posting_window tests.test_sources_config tests.test_post_summary`

## リスク

- `workflow_dispatch` の手動確認をしやすくするため、手動実行時だけ投稿時刻判定をバイパスする可能性がある
- raw 投稿に切り替えることで 280 文字超過時は既存の truncate ロジックに依存する

## 実装ステップ

- [x] `post_buz` のスケジュールと時刻判定仕様を新時刻へ更新する
- [x] `buz` 設定を raw 投稿・返信無効へ更新する
- [x] `buz` ソースを3アカウントのみに限定する
- [x] 関連ユニットテストを RED -> GREEN で更新する
- [x] 対象テストを実行して結果を確認する
