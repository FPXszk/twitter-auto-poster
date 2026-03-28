# post_buz ライブ再実行計画

## 概要

画像添付と state 保存修正を含む `main@3536f58` を前提に、`post_buz.yml` を `workflow_dispatch` でライブ実行する。`dry_run=false` で起動し、run の進行・結果・確認ポイントを整理してユーザーに引き渡す。

## 変更・作成・確認対象

- 変更ファイル: なし
- 実行対象: `.github/workflows/post_buz.yml`
- 確認対象: workflow run / jobs / summary / artifacts / state save の成否
- 計画書: `docs/exec-plans/active/post-buz-live-run_20260328_1445.md`

## 実装方針

- `gh` CLI で `post_buz.yml` を `workflow_dispatch`、`dry_run=false` で起動する
- 実行コマンドは `gh workflow run post_buz.yml --repo FPXszk/twitter-auto-poster -f dry_run=false` を使う
- 起動した run id を特定し、job 状態と失敗有無を追跡する
- ログでは少なくとも以下を確認する
  - 画像取得が成功しているか
  - `post_publish.sh` の cleanup trap で failure していないか
  - `Save post state` が実行されているか
- 完了後、ユーザーが X 上で確認しやすいように run URL と要点を返す

## 実装ステップ

- [ ] 1. `gh workflow run post_buz.yml --repo FPXszk/twitter-auto-poster -f dry_run=false` でライブ起動する
- [ ] 2. 起動した run を特定して jobs / logs / summary を確認し、`Result mode`・`Post result file`・エラー有無を確認する
- [ ] 3. 画像取得・cleanup・`Save post state` の成否をログから確認する
- [ ] 4. ユーザー確認用に run URL と結果を整理する

## 注意点

- 実行はライブ投稿になるため `dry_run=false` で起動する
- コード変更や設定変更は行わない
- 実行失敗時は原因を添えて報告する
- 実際の X 投稿の最終確認はユーザーの目視確認を前提にする
- 画像添付の有無は workflow ログで兆候を確認しつつ、最終的には X 上の見た目をユーザーに確認してもらう
