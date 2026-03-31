# 実装計画: post_pic の no_candidate 解消と実投稿確認

## 概要

`post_pic` の live run は workflow 自体は成功するものの、artifact の `candidate-pic.*` が `result_mode: "no_candidate"` になり、`post_result_file: null` のままで実投稿に到達していない。

確認済みの事実:

- run `23781032934` (`workflow_dispatch`, `dry_run=false`) は `success`
- しかし `tmp/post-pic-23781032934/runs/candidate-pic.23Fcz1` は `requested_mode=live`, `result_mode=no_candidate`, `selected_source=null`
- raw payload は各 source で 10〜20 件取得できている
- sample raw item の `createdAtISO` は `2026-02-07T05:25:56+00:00` で、現行 `config/accounts.yaml` の `pic.filters.max_age_hours: 72` に確実に抵触する

方針としては、**`pic` の鮮度条件を緩めて古めの画像投稿も許可する**。そのうえで、必要なら skip reason の可視化と補助テストを追加し、修正後に `post_pic` を再度 live 実行して tweet ID / URL まで確認する。

`docs/exec-plans/active/` に競合する計画はないことを確認済み。

## 変更対象ファイル

- `config/accounts.yaml`
  - `pic.filters.max_age_hours` を実態に合う値へ緩和
  - 必要なら `pic.filters.min_author_followers` の扱いも見直し
- `tests/test_sources_config_pic.py`
  - `pic` 設定の期待値変更を追加/更新
- `tests/test_post_filters.py`
  - pic 向けに古め投稿を通す条件、または follower 条件の扱いに関する回帰テストを追加
- `tests/test_post_author.py`
  - author metrics 補完の失敗時でも pic の方針に矛盾しないことを確認するテストを追加する可能性あり
- `scripts/lib/workflow_summary.py`
  - 必要なら `no_candidate` 時の skip reason / diagnostics を見やすくする改善
- `README.md`
  - `post_pic` 運用説明を変更する必要が出た場合のみ更新

## 実装内容と影響範囲

### 1. 原因の切り分け

- `candidate-pic.*` と `raw/pic/*.json` の差分から、候補取得ではなく選抜前フィルタで全落ちしていることを前提に検証する
- 最優先で `max_age_hours` が主因かをテストで固定する
- 併せて `min_author_followers` / `author follower count unavailable` が副次要因かを確認する

### 2. 最小修正方針

- 第一候補は `config/accounts.yaml` の `pic.filters.max_age_hours` を緩める設定変更
- `pic` は「最新ニュース」ではなく「画像アカウントの良質画像投稿」を拾う用途なので、`buz/news` と違って古め候補を許容する
- もし age 緩和だけで不十分なら、`min_author_followers` も `pic` 用に緩める
- selection / workflow 本体にはバグの証拠が出ない限り手を入れない

### 3. 可視化改善

- `no_candidate` の再発時に原因が追いやすいよう、必要なら summary 側に skip reason の件数や代表例を出す
- ただし本筋は実投稿到達なので、可視化改善は設定修正の後で最小限に留める

### 4. 実投稿確認

- 修正後に `gh workflow run post_pic.yml -f dry_run=false` を実行
- `candidate-pic.*` の `requested_mode=live`, `result_mode=posted`, `post_result_file` 非 null を確認
- run summary の `Posted tweet` 行と tweet URL/ID を確認
- `Save post state` 成功と artifact 保存も確認

## RED -> GREEN -> REFACTOR 方針

### RED

- `tests/test_sources_config_pic.py`
  - `pic.filters.max_age_hours` の期待値を新方針へ更新し、現状 failing にする
- `tests/test_post_filters.py`
  - `pic` 想定の古め候補が `max_age_hours` によって reject される現状を再現し、緩和後は通ることをテストで固定する
- 必要なら `tests/test_post_author.py`
  - author lookup 失敗時の follower 判定が pic 方針と噛み合うことを固定する

### GREEN

- `config/accounts.yaml` の `pic` filters を最小限変更してテストを通す
- 必要なら summary 側に最小限の診断表示を追加

### REFACTOR

- テスト名・fixture を pic 用途に合わせて整理
- `post_pic` にだけ必要な条件変更であることが分かるように設定コメント/期待値を整理

## 検証コマンド

```bash
python/.venv/bin/python -m unittest tests.test_sources_config_pic tests.test_post_filters tests.test_post_author
python/.venv/bin/python -m unittest discover -s tests
python3 - <<'PY'
from pathlib import Path
import yaml
for path in [Path('config/accounts.yaml'), Path('.github/workflows/post_pic.yml')]:
    yaml.safe_load(path.read_text(encoding='utf-8'))
print('OK')
PY
gh workflow run post_pic.yml -f dry_run=false
gh run list --workflow=post_pic.yml --limit 3
gh run watch <RUN_ID>
gh run view <RUN_ID>
```

## 実装ステップ

- [ ] 失敗 run artifact の `skipped_candidates` / `diagnostics.author_lookup` を確認し、age 条件が主因か最終確認する
- [ ] RED: `tests/test_sources_config_pic.py` に pic filters の期待値変更テストを追加/更新する
- [ ] RED: `tests/test_post_filters.py` に pic 用の古め候補回帰テストを追加する
- [ ] 必要なら RED: `tests/test_post_author.py` に author lookup 失敗系の補助テストを追加する
- [ ] GREEN: `config/accounts.yaml` の `pic.filters.max_age_hours` を緩和する
- [ ] 必要なら GREEN: `pic.filters.min_author_followers` も緩和する
- [ ] 必要なら GREEN: `scripts/lib/workflow_summary.py` に no_candidate 診断の補助表示を追加する
- [ ] REFACTOR: テスト/設定の説明を整理する
- [ ] 既存テストと targeted test を実行する
- [ ] `post_pic` を `dry_run=false` で再実行する
- [ ] artifact / summary / tweet URL/ID を確認する
- [ ] 実投稿失敗なら、結果を保存して別計画へ切り分ける

## リスク

- `max_age_hours` を緩めると古い投稿を再掲する可能性がある
- `min_author_followers` まで緩める場合、候補品質が落ちる可能性がある
- live run の再実行で不適切な投稿が出る可能性があるため、投稿後の確認と必要なら削除が必要
- summary 改善まで広げすぎると本筋の設定修正より変更範囲が膨らむ

## Out of Scope

- `post_pic` の workflow 新設や全面再設計
- `post_buz` / `news` / `auto_follow` のロジック変更
- 画像ダウンロード/投稿パイプライン自体の大規模変更
- 今回の修正に直接不要な scoring ロジック全体の見直し
