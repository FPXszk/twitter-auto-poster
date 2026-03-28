# post_buz ワークフロー障害調査・対策計画

## 概要

`post_buz.yml` は GitHub Actions 上では `active` だが、直近の scheduled run `#1`（run id `23676655893`）は失敗している。
一次障害は `scripts/lib/post_author.py` の `twitter` 実行が PATH 依存で `FileNotFoundError: 'twitter'` になっている点で、二次障害として `Write run summary` が空または不正な candidate JSON を読み込んで `JSONDecodeError` で連鎖失敗している。

## 調査結果サマリー

- Workflow 定義ファイル: `.github/workflows/post_buz.yml`
- Workflow 状態: `active`
- 直近実行: run `23676655893` / `schedule` / `completed: failure`
- 失敗開始ステップ: `Fetch candidates and process mode`
- 一次原因: `scripts/lib/post_author.py` が `subprocess.run(["twitter", ...])` を直接呼び、ワークフロー内 venv の実体 `python/.venv/bin/twitter` を使えていない
- 二次原因: candidate 生成失敗後も `Write run summary` が壊れた candidate ファイルを `json.loads()` して落ちる

## 変更・作成・確認対象ファイル

- `scripts/lib/post_author.py`
  - `twitter` 実行パス解決を common.sh の期待値と揃える
  - `TWITTER_BIN` / repo ルート基準の venv / PATH の順で安全に解決する
- `scripts/fetch_and_post.sh`
  - candidate 出力を一時ファイル経由にして、生成成功時のみ本ファイルへ反映する
- `.github/workflows/post_buz.yml`
  - `Write run summary` が candidate JSON の不正時でも診断情報を書いて完走できるようにする
- `tests/test_post_author.py`（新規）
  - `post_author` の実行パス解決と subprocess エラーハンドリング
- `tests/` 配下の関連テスト
  - candidate JSON 不正時の summary 側の扱い
- `docs/exec-plans/active/post-buz-workflow-investigation_20260328_1323.md`
  - 本計画書

## 実装方針

- `post_author.py` に twitter CLI 解決ヘルパーを追加し、GitHub Actions でもローカルでも同じ規約で実行する
- `TWITTER_BIN` は任意 override とし、未設定時でも repo ルート基準の `python/.venv/bin/twitter` を解決できる前提で進める
- candidate 出力は `scripts/fetch_and_post.sh` 側で一時ファイル経由にし、失敗時に空ファイルを本番ファイルとして残さない
- `.github/workflows/post_buz.yml` の `Write run summary` では JSON パース失敗を明示的に扱い、一次障害を隠さず summary 自体は書き切る
- 回帰テストを先に追加して RED を作り、その後最小修正で GREEN にする
- 既存の検証手順に沿って py_compile / unittest / workflow YAML チェックを実行する

## 実装ステップ

- [x] 1. `tests/test_post_author.py` を新規追加し、twitter CLI の解決順序・見つからない場合の失敗・lookup 失敗時の RuntimeError 変換を RED で固定する
- [x] 2. `post_author.py` の twitter CLI 解決戦略を実装し、PATH 非依存で user lookup が動くようにして GREEN にする
- [x] 3. `scripts/fetch_and_post.sh` で candidate 出力を一時ファイル経由に変更し、壊れた candidate を残さないようにする
- [x] 4. `.github/workflows/post_buz.yml` の `Write run summary` を耐障害化し、JSONDecodeError を連鎖させない
- [x] 5. 追加した回帰テストと既存関連テストを通し、必要なら summary まわりのテストも補強する
- [x] 6. `python -m py_compile scripts/lib/post_author.py scripts/lib/workflow_summary.py tests/test_post_author.py tests/test_workflow_summary.py`、`bash -n scripts/fetch_and_post.sh scripts/lib/common.sh scripts/lib/post_publish.sh`、`python -m unittest tests.test_post_author tests.test_workflow_summary`、`python -m unittest discover -s tests`、workflow YAML の構文検証、`git diff --check` を実行する
- [x] 7. 追加で見つかった副作用がないか確認し、対策と残課題を整理する

## 想定される対策案

- 対策A: `post_author.py` 側で `TWITTER_BIN` と repo ルート基準の `python/.venv/bin/twitter` を解決して使う（workflow 側に新規 env を必須追加しない）
- 対策B: `scripts/fetch_and_post.sh` で candidate JSON を一時ファイルに出力し、成功時のみ本ファイルへ反映する
- 対策C: `Write run summary` では JSONDecodeError を握り潰さず、壊れた candidate を明示して summary 自体は書き切る

## 注意点

- 既存の投稿ロジックやスコアリング条件は今回の主眼ではないため、不必要な仕様変更はしない
- 既存の `common.sh` の bin 解決規約と齟齬が出ないようにする
- `Write run summary` の改善は、一次障害の隠蔽ではなく診断性向上を目的にする
