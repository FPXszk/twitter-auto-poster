# 実装計画: post_buz アカウント入替と投稿時間帯・スケジュール変更

## 概要

`post_buz` ワークフローで参照する `buz` ソースの投稿元アカウントを、現行の 9 アカウントから新しい 10 アカウントへ差し替える。
旧アカウント定義は削除せず、`config/sources.yaml` 内でコメントアウトして残す。

あわせて、自動実行スケジュールを毎時 0 分で再開し、投稿対象時間帯を JST 7:00〜翌 1:00 に変更する。
アカウントの切り替えは既存の `round_robin_account` ロジックをそのまま使い、1 時間ごとに次のアカウントへ進む前提で構成を更新する。

`docs/exec-plans/active/` には競合する進行中計画がないことを確認済み。

## 変更対象ファイル

- `config/sources.yaml`
  - 旧 `buz` ソースをコメントアウトして保持
  - 新 10 アカウント分の `buz` ソースを追加
- `.github/workflows/post_buz.yml`
  - `schedule` を毎時実行で再有効化
  - 投稿時間帯判定を JST 7:00〜翌 1:00 に変更
  - 判定ロジックをテスト可能な本番モジュール呼び出しへ切り替え
- `scripts/lib/posting_window.py`
  - 投稿時間帯判定の本番関数を新規追加
- `scripts/lib/workflow_summary.py`
  - 投稿時間帯スキップ文言を新時間帯へ更新
- `tests/test_post_selection.py`
  - 新しい 10 アカウント前提の `round_robin_account` テストを追加
- `tests/test_posting_window.py`
  - 投稿時間帯判定の境界値テストを新規追加
- `tests/test_workflow_summary.py`
  - スキップ文言が新時間帯表示になることを確認するテストを追加
- `tests/test_sources_config.py`
  - `config/sources.yaml` の `buz` 設定が期待どおりになっているか検証するテストを新規追加

## 新アカウント

- `ql_7mxa`
- `yaruki_nash2`
- `rmiqx_`
- `pam99ham`
- `kyomx2_pudding_`
- `aaa_hareharu`
- `suzuka_saga`
- `bibilab158`
- `hatsunetsu_u`
- `175__chan`

## 実装内容と影響範囲

### 1. `config/sources.yaml`

- 既存の `buz` 向け 9 アカウント分の定義をコメントアウトで残す
- コメントアウト区間に「旧アカウント定義」であることを示すヘッダコメントを付ける
- 新 10 アカウントについて、既存と同じ形式で `big` / `small` の 2 エントリずつ追加する
- `rotation_key` は各アカウント名を使い、`round_robin_account` の入力順をそのまま新ローテーション順にする
- `news` 系ソースや他カテゴリは変更しない

### 2. `.github/workflows/post_buz.yml`

- 現在コメントアウトされている `schedule` を復活させ、毎時 0 分実行へ戻す
- `Evaluate posting window` のインライン判定式を、`scripts/lib/posting_window.py` の関数呼び出しへ置き換える
- 判定は JST 기준で `7 <= hour or hour < 1` と等価な実装にし、7:00〜0:59 のみ投稿対象にする
- ワークフローコメントも一時停止中の説明から、現行運用に合う内容へ更新する

### 3. `scripts/lib/posting_window.py`

- ワークフローから import して使える、投稿時間帯判定の本番関数を追加する
- 単純な判定ロジックを 1 か所へ寄せ、テストとワークフローの条件を一致させる

### 4. `scripts/lib/workflow_summary.py`

- 投稿時間帯外でスキップした際の文言を `08:00-24:00` から新しい時間帯表記へ更新する
- 実行結果のサマリがワークフロー実装と食い違わない状態にする

### 5. テスト

- ロジック自体は既存の `round_robin_account` を流用するため、主に設定変更と時間帯判定の整合性を確認する
- 実データに近いアカウント名でローテーション順を確認する
- `config/sources.yaml` の有効 `buz` ソース構成をテストで固定し、設定 typo や並び順崩れを防ぐ

## 実装ステップ

- [ ] 影響箇所の現状テストと設定を確認する
- [ ] RED: `tests/test_posting_window.py` を追加し、JST 0, 1, 6, 7, 23 時台の境界を失敗テストで定義する
- [ ] RED: `tests/test_sources_config.py` を追加し、`buz` の有効ソースが新 10 アカウント × 2 件であることを失敗テストで定義する
- [ ] RED: `tests/test_workflow_summary.py` に投稿時間帯外メッセージの期待値変更テストを追加する
- [ ] RED: `tests/test_post_selection.py` に新 10 アカウント順のラウンドロビン確認テストを追加する
- [ ] GREEN: `scripts/lib/posting_window.py` を追加して投稿時間帯判定を実装する
- [ ] GREEN: `.github/workflows/post_buz.yml` から新しい投稿時間帯判定関数を使うよう変更する
- [ ] GREEN: `.github/workflows/post_buz.yml` の cron を再有効化し、関連コメントを更新する
- [ ] GREEN: `config/sources.yaml` の旧アカウント定義をコメントアウトし、新アカウント定義へ差し替える
- [ ] GREEN: `scripts/lib/workflow_summary.py` の投稿時間帯文言を更新する
- [ ] REFACTOR: コメントの整理、重複表現の解消、テストデータの読みやすさ改善を行う
- [ ] 既存の検証コマンドで回帰確認する

## RED → GREEN → REFACTOR 方針

### RED

- `tests/test_posting_window.py`
  - 本番関数 `should_run_in_posting_window` を直接テストする
  - 7:00 は `true`、0:59 相当の 0 時台は `true`、1:00 は `false`、6:00 台は `false` を確認する
- `tests/test_sources_config.py`
  - `config/sources.yaml` を読み込み、`buz` の有効エントリ数が 20 件であること
  - 有効 `rotation_key` が 10 個で、各アカウントに `big` / `small` が 1 つずつあること
  - 旧 9 アカウントが有効エントリ側に残っていないことを確認する
- `tests/test_workflow_summary.py`
  - 投稿時間帯外スキップ時のサマリ文言が新時間帯になることを確認する
- `tests/test_post_selection.py`
  - 新 10 アカウントの並びを `source_order` に渡したとき、前回アカウントの次から順番に進むことを確認する

### GREEN

- 最小限の本番コード変更で上記テストを通す
- 既存の選定ロジックには手を入れず、設定・時間帯判定・サマリ文言のみ変更する

### REFACTOR

- YAML コメントやテストデータの説明を整理する
- ワークフローと本番モジュールの責務分離を明確にする
- 全テスト再実行で回帰がないことを確認する

## 検証コマンド

```bash
python/.venv/bin/python -m unittest discover -s tests
python/.venv/bin/python -m unittest tests.test_post_selection tests.test_posting_window tests.test_sources_config tests.test_workflow_summary
python/.venv/bin/python -m py_compile scripts/lib/post_selection.py scripts/lib/posting_window.py scripts/lib/workflow_summary.py
bash -n scripts/lib/common.sh scripts/fetch_search.sh scripts/fetch_and_post.sh
python3 - <<'PY'
from pathlib import Path
import yaml
for path in [Path('config/sources.yaml'), Path('.github/workflows/post_buz.yml')]:
    yaml.safe_load(path.read_text(encoding='utf-8'))
print('OK')
PY
```

補足:

- リポジトリ規約にはカバレッジ 80% 確認の記載があるが、現時点で README や CI に既存のカバレッジ計測コマンドは定義されていない
- そのため今回は既存テスト群と対象テストの追加で回帰防止を行い、カバレッジ計測基盤の整備自体はスコープ外とする

## Out of Scope

- `scripts/fetch_and_post.sh` や `scripts/lib/post_selection.py` の選定ロジック変更
- `config/accounts.yaml` の `buz` アカウント設定値変更
- `news` ソースや他ワークフローの設定変更
- 旧アカウント定義の完全削除
- Twitter / GitHub Secrets の更新
- カバレッジ計測基盤の新規導入

## リスクと確認事項

- cron 再有効化により、マージ後は `post_buz` の自動投稿が再開される
- 新アカウントの検索結果量が既存閾値に合わず、候補不足になる可能性がある
- 旧ローテーション状態ファイルに旧アカウント名が残っていても、既存正規化ロジックで先頭から再開される想定だが、実行確認は必要
- `from:` クエリのユーザー名表記は URL 由来で設定するため、表記揺れがないか実装時に再確認する

## 実装時の前提

- `big` / `small` のしきい値、`score_boost`、`max_results` は現行 `buz` と同値を維持する
- 投稿順は `config/sources.yaml` に並べたアカウント順を採用する
- 日本時間 7:00〜翌 1:00 の解釈は、JST の 0 時台を含み 1:00 ちょうどを含まない
