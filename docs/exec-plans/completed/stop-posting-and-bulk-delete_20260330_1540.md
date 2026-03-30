# 投稿自動化の一時停止と既存投稿の全削除

**作成日時:** 2026-03-30 15:40 UTC  
**ステータス:** 承認待ち

---

## 1. 問題 / 背景

ユーザー要望は次の 2 点です。

- 投稿系ワークフローを一旦停止し、ツイート戦略を見直せる状態にする
- 現在アカウント上にある投稿系コンテンツ（通常ポスト・返信・引用・リポスト）を把握し、安全に一括削除できる仕組みを追加する

確認済み前提:

- 停止対象は **「投稿系のみ」** であり、`ci.yml`、`twitter_diagnostic.yml`、`update_tickers.yml`、`update_tickers_jp.yml` は止めない
- 削除対象は **通常ポスト / 返信 / 引用 / リポストを含む投稿系全般** とする

---

## 2. 現状調査結果

### 2.1 停止対象ワークフロー

確認できた投稿系 workflow は以下です。

| ファイル | 現在の状態 | 今回の扱い |
|---|---|---|
| `.github/workflows/post_buz.yml` | `schedule` 有効 | **変更対象** |
| `.github/workflows/morning_post.yml` | `schedule` は既に無効、`workflow_dispatch` のみ | 変更不要 |
| `.github/workflows/evening_post.yml` | `schedule` は既に無効、`workflow_dispatch` のみ | 変更不要 |
| `.github/workflows/post_video.yml` | `workflow_dispatch` のみ | 変更不要 |

補足:

- `.github/workflows/auto_like.yml` と `.github/workflows/auto_follow.yml` は X 操作を行うものの、今回確認したユーザー条件では **「投稿系停止」の対象外** とする
- 実際に GitHub Actions の自動実行を止めるために変更が必要なのは、現時点では **`post_buz.yml` のみ**

### 2.2 Twitter/X 操作の既存実装

既存の `twitter-cli` 利用で、今回必要な主要操作は賄える見込みです。

- 認証確認: `twitter status`, `twitter whoami --json`
- 自アカウント特定: `twitter whoami --json`
- アカウント情報取得: `twitter user <username> --json`
- 投稿一覧取得: `twitter user-posts <username> --json`
- 通常ポスト / 返信 / 引用の削除: `twitter delete <tweet_id>`
- リポスト解除: `twitter unretweet <tweet_id>`

一方で、**この repo には既存の一括削除 CLI は存在しない** ため、新規追加が必要です。

### 2.3 件数確認と安全性評価の前提

実装前の想定は次の通りです。

- 総件数の基準値は `twitter whoami --json` で確定した自アカウントの username を使い、`twitter user <username> --json` の `tweets_count` から取得する
- 実削除に使う候補一覧は `twitter user-posts <username> --json` から取得する
- **`tweets_count` と取得一覧件数が一致しない場合は安全側で扱う**（dry-run で警告または execute を中断する設計を優先）
- 未分類の投稿種別は削除せず、明示的に警告して停止する

### 2.4 既存テスト / 検証基盤

- Python テスト: `python -m unittest discover -s tests`
- 個別テスト: `python -m unittest tests.test_xxx`
- 構文確認: `python -m py_compile ...`
- Workflow/YAML 確認: `python - <<'PY' ... yaml.safe_load(...)`

### 2.5 既存 plan との衝突

- `docs/exec-plans/active/` に他の active plan はなく、衝突なし

---

## 3. 変更対象ファイル

### 3.1 変更するファイル

- `.github/workflows/post_buz.yml`
- `README.md`

### 3.2 新規作成するファイル

- `python/bulk_delete.py`
- `tests/test_bulk_delete.py`

### 3.3 削除するファイル

- なし

---

## 4. 実装方針

### 4.1 投稿系ワークフロー停止

- `post_buz.yml` の `schedule` をコメントアウトして、自動投稿を停止する
- `workflow_dispatch` は維持し、必要時のみ手動実行できる状態を残す
- コメントには停止理由を残し、後で戻しやすくする

### 4.2 一括削除 CLI の基本方針

新規 `python/bulk_delete.py` は、まず **確認専用の dry-run** を安全なデフォルトにし、その後に明示的 `--execute` でのみ削除する。

期待する流れ:

1. `twitter whoami --json` で認証済みの自アカウントを取得
2. `twitter user <username> --json` で `tweets_count` を取得
3. `twitter user-posts <username> --json` で削除候補一覧を取得
4. 投稿を `normal / reply / quote / retweet / unknown` に分類
5. dry-run では以下を表示して終了
   - 総件数
   - 取得できた件数
   - 種別別件数
   - 総件数との差分
   - 削除対象サンプル
6. execute では以下を強制する
   - 削除前バックアップ JSON 作成
   - 確認プロンプト（`--yes` のときのみ省略）
   - `retweet` は `unretweet`、それ以外は `delete`
   - state ファイル保存による再開対応
   - 未分類件数または件数差分がある場合は安全側で停止

### 4.3 誤削除防止の原則

- 対象 username は `whoami` の結果で確定し、任意 username を自由入力させない
- dry-run を通さず execute できる設計にしない
- backup 書き込み前に削除を始めない
- unknown 種別は削除対象に含めない

---

## 5. 実装ステップ（TDD: RED → GREEN → REFACTOR）

### Phase 1: workflow 停止

- [ ] `post_buz.yml` の `schedule` をコメントアウトする
- [ ] 停止理由コメントを追加する
- [ ] YAML と差分を確認して、手動実行が壊れていないことを確認する

### Phase 2: dry-run / 件数確認 CLI

- [ ] **RED** `tests/test_bulk_delete.py` を作成し、以下の失敗テストを書く
- [ ] `test_parse_args_defaults`
- [ ] `test_whoami_username_is_used_for_target`
- [ ] `test_fetch_total_count_from_user_payload`
- [ ] `test_classify_tweets_by_type`
- [ ] `test_unknown_tweet_type_is_skipped`
- [ ] `test_dry_run_reports_count_mismatch`
- [ ] **GREEN** `python/bulk_delete.py` に最小実装を入れる
- [ ] `run_twitter_json()` / `run_twitter_write()` 相当のラッパーを実装する
- [ ] `whoami` → `user` → `user-posts` の取得処理を実装する
- [ ] 分類と dry-run サマリ出力を実装する
- [ ] **REFACTOR** 型・ログ・エラーメッセージを整理する

### Phase 3: 実削除

- [ ] **RED** 以下の失敗テストを追加する
- [ ] `test_backup_written_before_execute`
- [ ] `test_execute_requires_confirmation_without_yes`
- [ ] `test_delete_normal_reply_quote_uses_delete`
- [ ] `test_retweet_uses_unretweet`
- [ ] `test_resume_skips_already_deleted_ids`
- [ ] `test_execute_aborts_when_count_mismatch_exists`
- [ ] `test_execute_aborts_when_unknown_items_exist`
- [ ] **GREEN** 実削除ロジックを追加する
- [ ] backup/state 管理を実装する
- [ ] `--execute` / `--yes` を実装する
- [ ] 進捗表示と安全停止条件を実装する
- [ ] **REFACTOR** 再実行性と例外系を整理する

### Phase 4: ドキュメント / 最終検証

- [ ] `README.md` に bulk delete の使い方と注意点を追記する
- [ ] 対象テスト / 全体テスト / py_compile / YAML 確認を通す
- [ ] 実アカウントに対しては **dry-run だけ** を先に実行し、総件数と取得件数の差を確認する
- [ ] 差分や unknown がなければ、その時点で実削除実行可否を再判断する

---

## 6. テスト戦略

### RED

- 新規 `tests/test_bulk_delete.py` で、CLI 引数解析・件数取得・分類・安全停止条件・削除呼び出しを先に失敗で固定する

### GREEN

- 最小限の `python/bulk_delete.py` を追加し、サブプロセス呼び出しは `subprocess.run` モックで通す

### REFACTOR

- ログ/型/関数分割を整理し、再開用 state と backup の責務を明確にする

---

## 7. 検証コマンド

```bash
python -m unittest tests.test_bulk_delete
python -m unittest discover -s tests
python -m py_compile python/bulk_delete.py
python - <<'PY'
from pathlib import Path
import yaml
for path in [Path('.github/workflows/post_buz.yml')]:
    yaml.safe_load(path.read_text(encoding='utf-8'))
print('yaml ok')
PY
python/.venv/bin/python python/bulk_delete.py --help
python/.venv/bin/python python/bulk_delete.py --dry-run
```

---

## 8. リスク / 注意点

### 8.1 いきなり削除するとまずいか

**はい、まずい可能性があります。** 主な理由は次の通りです。

- 削除は不可逆で、戻せない
- `tweets_count` と実取得件数がズレた状態で走らせると「一部だけ消えた半端な状態」になる
- 返信 / 引用 / リポストの payload が完全に分類できない場合、誤削除または取りこぼしが起こりうる
- 認証切れや API 制限の途中失敗により、中途半端な実行状態になる可能性がある

そのため、**実運用は dry-run → 差分確認 → backup 作成 → execute の順** を必須にする。

### 8.2 API / 認証リスク

- Cookie 期限切れで `whoami` / `user-posts` が失敗する可能性
- 大量削除でレート制限や一時エラーが起こる可能性
- 書き込み系は browser cookie ベース認証のほうが安定しやすい

### 8.3 workflow 停止リスク

- 自動投稿停止により `post_buz` の定期発信は止まる
- ただし `workflow_dispatch` は残すため、必要時には手動確認実行ができる

---

## 9. スコープ外

- `auto_like.yml` / `auto_follow.yml` の停止
- `ci.yml` / `twitter_diagnostic.yml` / `update_tickers*.yml` の変更
- twitter-cli 本体の改修
- DM / likes / bookmarks / follows の一括削除
- 実削除を GitHub Actions 化すること

