# post_buz 通常ポスト化・リンク削除 実装計画

## 概要

ユーザー要望に合わせて `post_buz` の投稿形式を `通常ポスト1件 / 引用なし / 引用先リンクなし` に戻す。
現在の `buz` アカウントは `source_reference_mode: "url"` になっており、単独投稿でも末尾に元ポスト URL が付くため、この挙動を止める必要がある。

## 要求の整理

- 引用投稿は使わない
- 投稿自体は止めない
- 投稿形式は単独の通常ポスト1件
- 元ポストへのリンクは本文に含めない

## 変更・作成・確認対象ファイル

- `config/accounts.yaml`
  - `buz` の参照モードをリンクなし通常ポストに変更する
- `scripts/lib/common.sh`
  - `source_reference_mode` の許容値を拡張する場合は設定検証を更新する
- `scripts/lib/post_summary.py`
  - 単独投稿・スレッド生成時にリンクを付けないモードを表現できるようにする
- `scripts/lib/post_publish.sh`
  - publish action 名や thread plan が新モードでも自然に動くよう確認する
- `scripts/fetch_and_post.sh`
  - candidate payload / publish 呼び出しで新モードを流し、`source_url` は診断用に保持しても publish の thread plan には渡さない
- `tests/test_post_summary.py`
  - 単独投稿・スレッドでリンクなしモードを RED/GREEN で固定する
- `tests/test_post_publish.py`
  - 通常ポスト publish が quote に寄らずリンクなしで流れることを確認する
- `docs/exec-plans/active/post-buz-noquote-nolink_20260328_1429.md`
  - 本計画書

## 実装方針

- `source_reference_mode` に `none` のような明示値を追加し、引用でも URL でもない通常ポストを設定で表現する
- `buz` はそのモードに固定し、`source_url` を持っていても本文へ付けない
- 実装は `post_publish.sh` 側で `source_reference_mode=none` のとき `thread_plan_source_url=""` として扱い、diagnostics 用 `source_url` と投稿本文向けリンク付与を分離する
- 既存の `quote` / `url` 挙動は壊さず、`buz` のみ設定で切り替える
- 先にテストを追加して RED を作り、最小変更で GREEN にする

## 実装ステップ

- [x] 1. `tests/test_post_summary.py` と `tests/test_post_publish.py` に、リンクなし通常ポストの期待挙動を RED で追加する
- [x] 2. `config/accounts.yaml` の `buz` 設定をリンクなし通常ポストへ切り替える
- [x] 3. `scripts/lib/common.sh` / `scripts/lib/post_summary.py` / `scripts/lib/post_publish.sh` で新モードを通し、`source_url` は summary diagnostics には残しつつ publish の thread plan には渡さず、引用も URL 付与もしないよう実装する
- [x] 4. 既存の `quote` / `url` モードに回帰がないか対象テストで確認する
- [x] 5. `bash -n`、`py_compile`、対象テスト、`python -m unittest discover -s tests`、workflow YAML 検証、`git diff --check` で確認する

## 注意点

- `post_quote.py` など quote 用コード自体は削除しない
- `news` や他カテゴリの既存設定は変えない
- run summary の診断情報は維持しつつ、本文中のリンク付与だけ止める
