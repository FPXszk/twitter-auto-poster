# Post invest ロジック改善 + 単独投稿化 実装計画

## 目的

`post_invest` の候補選定が、フォロワー規模の大きい公式/広告寄りアカウントを拾いやすくなっているため、`フォロワー規模に対して異常に伸びた投稿` を優先するよう改善する。

あわせて、現在の引用ベースの投稿経路は使わず、280文字以内の単独ポストへ統一する。画像付き候補では元画像を再利用できるようにし、本文はそのままの転載ではなく日本語で要約・言い換えした内容にする。

## 変更対象ファイル

- `config/accounts.yaml`
- `config/copilot_summary_prompt_ja.txt`
- `scripts/fetch_and_post.sh`
- `scripts/lib/post_media.py`
- `scripts/lib/post_scoring.py`
- `scripts/lib/post_publish.sh`
- `tests/test_post_scoring.py`
- `tests/test_post_publish.py`
- `tests/test_post_media.py`
- 必要に応じて `tests/test_post_summary.py`

## 実装内容

### 1. 候補選定ロジックの改善

- 候補ツイートの author 情報から `followers` / `following` / `verified` / account age 相当の属性を取得できる範囲で拾う
- payload に `followers` が無い場合は author ごとの追加取得と重複排除キャッシュを入れる
- `絶対値が極端なアカウント` を除外または大幅減点する仕組みを追加する
- `フォロワー数に対して反応が大きい投稿` を加点する仕組みを追加する
- `極端にフォロワーが少ないアカウント` も除外できるようにする
- 広告/公式/懸賞/勧誘っぽい本文とプロフィール由来のシグナルが取れる場合は追加フィルタする

### 2. 投稿生成の改善

- Copilot 要約プロンプトを、`事実維持 + 言い換え + 280文字以内 + パクリ感の低減` に寄せる
- 元ポストの URL や引用形式に依存しない単独ポストを生成する
- 単独ポストで 280 文字以内に収まることを既存の長さ判定で担保する

### 3. 画像付き投稿の改善

- 候補のメディア情報から再利用可能な画像 URL を抽出する
- 候補 dict / candidate JSON / publish 関数の引数へ画像情報を伝播させる
- 画像付き候補が選ばれた場合、実投稿時に画像を一時保存して添付できるよう投稿経路を拡張する
- 画像が使えないケースでは明示的にテキスト単独投稿へフォールバックする
- 成功・失敗を問わず一時画像ファイルを確実に削除する

### 4. 引用投稿経路の整理

- `quote` 前提の投稿処理と分岐を整理し、`invest` は単独投稿経路を使うよう統一する
- 既存の引用前提テストを置き換え、単独投稿 + 画像添付の検証へ切り替える

## 影響範囲

- `post_invest` の候補選定順位と除外条件が変わる
- `invest` の live 投稿結果が、引用ではなく単独ポストになる
- 画像付き候補で `twitter-cli` の投稿引数が変わる
- スコア計算・メディア抽出・投稿処理のユニットテスト更新が必要

## 実装ステップ

- [ ] 現行 payload で利用可能な author / media フィールドを確認し、スコア入力仕様を決める
- [ ] author 追加取得が必要な場合のキャッシュ方式と API 呼び出し回数を設計する
- [ ] RED: 大規模アカウント除外、低フォロワー除外、バズ率加点、画像 URL 抽出、単独投稿 + 画像添付の失敗テストを追加する
- [ ] GREEN: `post_scoring.py` と `fetch_and_post.sh` に author 指標ベースの選定ロジックを実装する
- [ ] GREEN: `post_media.py` に画像 URL 抽出を追加する
- [ ] GREEN: Copilot 要約プロンプトを更新し、単独ポスト前提の要約文へ寄せる
- [ ] GREEN: `post_publish.sh` を単独投稿 + 画像添付対応へ更新し、画像ダウンロードとクリーンアップを実装した上で `invest` の引用依存を外す
- [ ] REFACTOR: 使わなくなる引用前提分岐やテストを整理し、ログ/結果 JSON を整える
- [ ] 検証: 既存の Python / shell / unittest 一式を実行して回帰を確認する

## ロジックレビュー所見と追加提案

- `likes/retweets/replies/views` の絶対数だけだと、大規模アカウントが常に有利になりやすい
- 追加候補としては、`engagement per follower`、`views per follower`、`weighted engagement per follower` を使うのが有効
- しきい値を 1 本で固定するより、`min_followers` / `max_followers` / `max_following_to_followers_ratio` / `min_virality_ratio` のように設定値として持たせる方が調整しやすい
- 可能なら `verified` は即除外ではなく減点寄りにし、本文やプロフィールの広告シグナルと合わせて判定した方が安全
- 画像再利用は URL 取得だけで終わらず、一時ファイル保存・投稿・削除までを一連のフローとして扱う

## 想定テスト

- `tests/test_post_scoring.py`
  - フォロワー過大アカウントが落ちる
  - フォロワー過少アカウントが落ちる
  - フォロワー比で異常に伸びた投稿が加点される
- `tests/test_post_media.py`
  - 画像 URL を抽出できる
- `tests/test_post_publish.py`
  - 画像付き単独投稿で media 引数が渡る
  - 画像なし単独投稿が従来通り動く
  - 引用依存がなくても投稿成功する
- `python -m unittest discover -s tests`
- `python -m py_compile` 対象 Python 群
- `bash -n` 対象 shell 群
