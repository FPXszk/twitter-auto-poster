# SCHEMA

## この文書の役割

- この文書は、`twitter-auto-poster` の主要設定ファイルのスキーマ説明です。
- 設定値の実装上の正本は `scripts/lib/common.sh` の validation と、各処理スクリプトの読み出しロジックです。
- 実運用手順は `docs/RUNBOOK.md` を参照してください。

## 対象ファイル

- `config/sources.yaml`
- `config/accounts.yaml`

## `config/sources.yaml`

### トップレベル

- `defaults`: mapping
- `sources`: list

### `defaults`

- `max_results`: integer, `> 0`
- `timeline`: `top | latest | photos | videos`
- `exclude_retweets`: boolean

### `sources[]` 共通キー

- `id`: string, 必須
- `category`: string, 必須
- `type`: `user | search`, 必須
- `enabled`: boolean, 任意
- `max_results`: integer, `> 0`, 任意
- `exclude_retweets`: boolean, 任意
- `score_boost`: number, 任意
- `media_mode`: `any | image | text`, 任意
- `filters`: mapping, 任意

### `sources[].filters`

- `max_age_hours`: number, `> 0`
- `required_terms`: list of non-empty string
- `exclude_keywords`: list of non-empty string
- `min_author_followers`: integer, `>= 0`
- `max_author_followers`: integer, `>= 0`

### `type: user` のとき

必須:

- `username`: string

### `type: search` のとき

必須:

- `query`: string

任意:

- `timeline`: `top | latest | photos | videos`

### `sources.yaml` の意味

- `sources` は「どこから候補を取るか」を定義します。
- `score_boost` はソース単位の優先度補正です。
- `media_mode` は画像候補とテキスト候補の交互運用に使われます。
- `filters` はソース単位での上書き条件です。

## `config/accounts.yaml`

### トップレベル

- `defaults`: mapping
- `accounts`: mapping

### `defaults` / `accounts.<name>` 共通キー

- `dry_run`: boolean
- `post_prefix`: string
- `max_candidates`: integer, `> 0`
- `summary_prefix`: string
- `summary_language`: `ja | raw`
- `summary_provider`: `legacy_google_translate | copilot_cli`
- `summary_model`: string
- `summary_prompt_path`: string
- `summary_max_length`: integer, `1..280`
- `single_post_max_length`: integer, `1..280`
- `state_file`: string
- `media_state_file`: string
- `selection_mode`: `score | round_robin`
- `source_reference_mode`: `url | quote`
- `rotation_state_file`: string
- `score_weights`: mapping
- `filters`: mapping

### `score_weights`

- `likes`: number
- `retweets`: number
- `replies`: number
- `views`: number
- `velocity`: number
- `freshness`: number
- `image_bonus`: number
- `author_virality`: number

### `filters`

- `max_age_hours`: number, `> 0`
- `required_terms`: list of non-empty string
- `exclude_keywords`: list of non-empty string
- `min_author_followers`: integer, `>= 0`
- `max_author_followers`: integer, `>= 0`

### `accounts.yaml` の意味

- `accounts` はカテゴリごとの投稿ポリシーです。
- `summary_*` は要約文生成の制御です。
- `score_weights` は候補選定スコアの重みです。
- `filters` は候補の除外条件です。
- `author_virality` は「フォロワー規模に対してどれだけ伸びたか」を加点するための重みです。

## 更新トリガー

次の変更が入ったらこの文書も更新します。

- `scripts/lib/common.sh` の validation 変更
- `config/*.yaml` の新規キー追加
- 候補選定や投稿生成に関わる設定項目の意味変更
