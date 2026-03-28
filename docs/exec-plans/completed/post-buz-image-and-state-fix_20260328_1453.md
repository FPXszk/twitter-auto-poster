# post_buz 画像添付・状態保存 修正計画

## 概要

live run `23678725070` では、引用なし投稿そのものは通ったが、元ツイート画像の取得で `HTTP Error 403` が発生し、その後 `post_publish.sh` の cleanup trap が `media_paths_json: unbound variable` で落ちた。
このため画像なし投稿になり、さらに workflow が failure 扱いとなって `Save post state` が走らず、次回 run で同じツイートが再選択された。

## 調査結果

- 画像添付ロジック
  - `post_media.py` は payload から `image_urls` を抽出している
  - `post_publish.sh` の `prepare_image_attachments()` が `urllib.request.urlopen()` で画像を直接ダウンロードする
  - live run ではここが `HTTP Error 403: Forbidden` で失敗し、warning のみ出して text only にフォールバックした
- 同一ツイート再選択
  - `publish_selected_post()` 自体は投稿後に `buz-posted.txt` / `buz-source-posted.txt` を更新している
  - しかし直後に `cleanup_publish_temp()` が `media_paths_json: unbound variable` で落ち、job 全体が failure になった
  - `.github/workflows/post_buz.yml` の `Save post state` は成功 run 前提の条件なのでスキップされ、更新 state が cache 保存されなかった
  - `selection_mode: round_robin` はランダムではなく source 順ローテーション。rotation state も保存されなかったため再選択が起きうる

## 要求整理

- 引用は使わないままにする
- 元ツイート画像は添付したい
- 同じツイートの再投稿は避けたい
- round_robin の状態は live run 後も持ち越したい

## 変更・確認対象ファイル

- `scripts/lib/post_publish.sh`
  - 画像ダウンロードの 403 回避策
  - cleanup trap の unbound variable 解消
- `tests/test_post_publish.py`
  - 画像取得失敗/成功・cleanup・state 更新まわりの回帰テスト追加
- `.github/workflows/post_buz.yml`
  - run failure 時でも保存すべき state の扱いを見直す必要があるか確認
- `scripts/fetch_and_post.sh`
  - posted / rotation / media state 更新順と failure 伝播を確認
- `docs/exec-plans/active/post-buz-image-and-state-fix_20260328_1453.md`
  - 本計画書

## 実装方針

- まず `post_publish.sh` の cleanup trap を安定化し、`prepare_image_attachments()` 失敗時でも `media_paths_json` が unbound にならないようにする
- 画像取得は current URL 直叩き前提を見直し、403 回避できる取得経路やヘッダ付き取得へ改善する
- state 保存は workflow failure 後でも次回選定に反映される必要があるため、workflow 側の保存条件補強を必須で検討する
- 先にテストを追加して RED を作り、最小修正で GREEN にする

## 実装ステップ

- [x] 1. `tests/test_post_publish.py` と `tests/test_post_media.py` に、画像取得と cleanup 後処理に関する RED テストを追加する
- [x] 2. `scripts/lib/post_publish.sh` で cleanup trap の unbound variable を解消し、`prepare_image_attachments()` 失敗時でも投稿成功後に failure へ転ばないようにする
- [x] 3. `scripts/lib/post_media.py` / `scripts/lib/post_publish.sh` で画像取得を改善し、引用なしでも画像添付できるようにする
- [x] 4. `.github/workflows/post_buz.yml` の state 保存条件を `always()` ベースに見直し、run failure でも保存すべき posted / rotation / media state が失われないようにする
- [x] 5. 対象テスト、`bash -n`、`py_compile`、`unittest discover -s tests`、workflow YAML 検証、`git diff --check` で確認する

## 注意点

- `round_robin` はランダムではなく決め打ちローテーションであることを維持する
- 引用なし・リンクなしの現行挙動は壊さない
- 画像取得失敗時の fallback は残しつつ、今回の 403 で text only へ落ちる頻度を下げる
