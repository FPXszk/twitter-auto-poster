# post_buz trap cleanup 修正計画

## 概要

live run `23679009193` で、`buz` 投稿自体と `Save post state` は成功した一方、job 全体は `Fetch candidates and process mode` の終了コード 1 で failure になった。`scripts/lib/post_publish.sh` の `trap cleanup_publish_temp RETURN` が関数終了後も残り、後続 return に影響している可能性が高いため、trap の解除を中心に最小修正する。

## 変更・作成・確認対象

- 変更ファイル: `scripts/lib/post_publish.sh`
- 変更候補: `tests/test_post_publish.py`
- 確認対象: `.github/workflows/post_buz.yml` の live 実行結果への影響、`fetch_and_post.sh` 成功終了
- 計画書: `docs/exec-plans/active/post-buz-trap-cleanup-fix_20260328_0611.md`

## 実装方針

- `publish_selected_post()` の cleanup trap が関数外へ漏れないように、終了時に trap を解除する
- 解除方法は bash の `trap - RETURN` など既存 shell 挙動に沿った最小変更に留める
- 可能ならテストで trap 後の成功終了を回帰防止する
- 変更後は対象テストと既存検証を再実行し、必要なら live run を再実行して workflow 成功まで確認する

## 実装ステップ

- [x] 1. `publish_selected_post()` の trap 生命周期を修正する
- [x] 2. `tests/test_post_publish.py` に trap 残留の回帰テストを追加する
- [x] 3. `python -m unittest tests.test_post_publish` と `python -m unittest discover -s tests` を通す
- [x] 4. `bash -n scripts/fetch_and_post.sh scripts/lib/common.sh scripts/lib/post_publish.sh`、`py_compile`、`git diff --check` を通す
- [ ] 5. `post_buz.yml` の再 live 実行は、fix を push した main が必要。未 push 状態で起動した run `23679171017` は旧 commit `3536f58` ベースだったため cancel 済み

## 注意点

- 画像添付・引用なし・state 保存の既存修正は壊さない
- `Save post state` はすでに `always()` 化済みなので今回は戻さない
- 変更は trap 周辺に限定し、不要なリファクタはしない
