# post_buz ローテーション修正と自動返信 実装計画

## 概要

`post_buz.yml` は複数の収集元アカウントからバズ投稿候補を拾う設計だが、現状の `buz` 設定では同じアカウントが連続採用されやすい。
調査したところ、`round_robin_account` 用の rotation state 解決が実質無効になっており、さらに source 順序にも同一アカウント重複が入り得るため、アカウント単位の順番回しが崩れている可能性が高い。

あわせて、`post_buz` の毎時実行タイミングで「直近の自動投稿に付いた返信」を検出し、Copilot で当たり障りのない短い返答案を作って自動返信する機能を同一 workflow に自然に統合する。

## 要求の整理

- `buz` の収集元アカウントは同一アカウント連投を避け、アカウント単位で順番に回す
- `post_buz` の毎時実行時に、過去の自動投稿へ新着返信が来ていないか確認する
- 未返信の返信があれば Copilot を使って無難な返答文を生成し、自動返信する
- 返信処理は `post_buz.yml` と同じ実行タイミング・認証・依存関係の中で自然に動く構成にする
- 重複返信は避ける

## 変更・作成・確認対象ファイル

- `config/accounts.yaml`
  - `buz` の rotation/reply 関連設定を明示し、必要な state / prompt 設定を追加する
- `config/copilot_reply_prompt_ja.txt`（新規）
  - 返信用 Copilot 指示文を追加する
- `scripts/fetch_and_post.sh`
  - `round_robin_account` でも rotation state を正しく解決・更新できるようにし、source 順序をアカウント単位で重複排除する
- `scripts/lib/post_selection.py`
  - account rotation の順序処理をテストしやすく保ち、必要なら重複順序の扱いを補強する
- `scripts/lib/post_feedback.py`
  - 既存の posted tweet 履歴を reply 対象探索へ再利用しやすい形に拡張する
- `scripts/lib/post_reply.py`（新規想定）
  - posted tweet 履歴から返信候補を集め、未返信判定・Copilot 呼び出し・twitter-cli reply 実行を担当する
- `.github/workflows/post_buz.yml`
  - 既存の投稿処理に加えて reply check / auto reply を組み込む
- `scripts/lib/workflow_summary.py`
  - reply check / reply result を workflow summary に表示する
- `tests/test_post_selection.py`
  - account rotation の重複順序・state 維持の RED/GREEN を追加する
- `tests/test_post_feedback.py`
  - reply 対象の履歴解釈や未返信判定の RED/GREEN を追加する
- `tests/test_post_reply.py`（新規）
  - reply 候補抽出、Copilot 生成結果の整形、重複返信防止を検証する
- `README.md`
  - `post_buz` のローテーション仕様と auto reply 動作を反映する
- `docs/exec-plans/active/post-buz-rotation-and-auto-reply_20260328_2324.md`
  - 本計画書

## 実装方針

- `resolve_rotation_state_file()` は `round_robin_account` でも state file を返すように直す
- `source_order` は source 定義順を保ちつつ account rotation key 単位で重複排除し、同一アカウントの `big/small` source が連続枠を奪わないようにする
- RED では「前回 alpha の次でも source_order の重複 alpha に吸われず beta へ進む」ケースを先に固定する
- 自動返信は新 workflow を増やさず `post_buz.yml` へ統合するが、投稿本体と障害を切り分けるため `fetch_and_post.sh` とは別 workflow step として実行する
- 返信対象は既存の feedback history に保存済みの `posted_tweet_id` を起点に集める。実装前に `twitter tweet <id> --json` の実 payload を確認し、replies の field path と author 情報を fixture 化してからロジックへ落とす
- 返信済み管理は専用 state を持ち、同じ reply ID へ二重返信しない
- bot 自身の投稿/返信は `twitter whoami --json` で取得した username / user id を使って除外する。既存の `auto_follow.py` / `twitter_account_diagnostic.py` の whoami 解釈を再利用候補として見る
- 1 回の実行で見る投稿数と返す返信数には上限を持たせ、`accounts.yaml` で `max_reply_checks_per_run` / `max_replies_per_run` を調整可能にする
- Copilot には「短く無難・攻撃的/断定的にしない・個人情報や勧誘を含めない」返信だけを出させ、投稿前に長さや空文字を検証する
- reply prompt は「元の自動投稿本文」と「受信 reply 本文」の両方を入れられるよう、summary prompt とは別の組み立て処理を `post_reply.py` 側に持たせる
- 返信処理は投稿本体を壊さないよう段階を分け、summary には投稿結果と返信結果の両方を残す
- 返信済み state は `tmp/state/` 配下に置き、既存 cache restore/save の対象へ自然に乗せる

## 実装ステップ

- [ ] 1. `twitter tweet <known_tweet_id> --json` の replies payload を確認し、reply 抽出に必要な field path・author 情報を fixture / テスト前提へ落とす
- [ ] 2. `tests/test_post_selection.py` に `round_robin_account` の state 解決と重複順序を固定する RED を追加する（`source_order` 重複ありケースも含む）
- [ ] 3. `scripts/fetch_and_post.sh` / 必要に応じて `scripts/lib/post_selection.py` を修正し、account rotation を正しく永続化・重複排除して GREEN にする
- [ ] 4. `tests/test_post_feedback.py` と `tests/test_post_reply.py` で、posted tweet 履歴から未返信 reply を拾う・self reply を除外する・返信済み state で重複防止する・1 run の上限を守る RED を追加する
- [ ] 5. `scripts/lib/post_reply.py`、`config/copilot_reply_prompt_ja.txt`、`config/accounts.yaml` を実装し、whoami 解決・Copilot 生成・reply 実行・state 更新を GREEN にする
- [ ] 6. `.github/workflows/post_buz.yml` と `scripts/lib/workflow_summary.py` を更新し、投稿本体とは別 step で reply check / auto reply を統合する
- [ ] 7. `README.md` を更新して、`post_buz` の account rotation と auto reply 挙動を記録する
- [ ] 8. `python -m unittest discover -s tests`、`bash -n`、`python -m py_compile`、workflow / config YAML 検証、`git diff --check` で確認する

## 影響範囲

- `buz` の候補選定順序が変わるため、同一アカウント連投が減り source の巡回性が上がる
- `post_buz.yml` の処理時間は reply check 分だけ少し増える
- Copilot 返信生成や `twitter reply` 失敗時の扱いを summary に残し、原因調査できるようにする必要がある

## 注意点

- 返信対象は bot 自身の既存 reply や自分自身の投稿を除外する
- 返信本文は 1 投稿で完結する短文に制限し、スレッド化しない
- `post_buz` の既存投稿本体が失敗しないことを最優先にしつつ、reply 処理は失敗理由を明示する
- README の `round_robin` / `round_robin_account` 説明は実装後の実態に合わせて更新する
- `max_reply_checks_per_run` / `max_replies_per_run` を越える残件は次回 run へ回す
- 返信済み state は `tmp/state/buz-replied.jsonl` など cache 対象パスに固定する
