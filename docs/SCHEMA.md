# CONFIG SCHEMA

このリポジトリでは `config/sources.yaml` と `config/accounts.yaml` を使います。
実行時には `scripts/lib/common.sh` の validation で基本 schema を検証します。

## `config/sources.yaml`

トップレベル:

- `defaults`: mapping
- `sources`: list

### `defaults`

- `max_results`: integer, `> 0`
- `timeline`: `top | latest | photos | videos`
- `exclude_retweets`: boolean

### `sources[]`

必須:

- `id`: string
- `category`: string
- `type`: `user | search`

任意:

- `enabled`: boolean
- `max_results`: integer, `> 0`
- `exclude_retweets`: boolean
- `score_boost`: number
- `media_mode`: `any | image | text`
- `filters`: mapping

`type: user` のとき必須:

- `username`: string

`type: search` のとき必須:

- `query`: string

`type: search` のとき任意:

- `timeline`: `top | latest | photos | videos`

### 例

```yaml
defaults:
  max_results: 5
  timeline: latest
  exclude_retweets: true

sources:
  - id: invest-mu-top-search
    category: invest
    type: search
    enabled: true
    query: "$MU lang:en"
    timeline: latest
    media_mode: image
    score_boost: 8
```

## `config/accounts.yaml`

トップレベル:

- `defaults`: mapping
- `accounts`: mapping

### 共通キー

- `dry_run`: boolean
- `post_prefix`: string
- `max_candidates`: integer, `> 0`
- `summary_prefix`: string
- `summary_language`: `ja | raw`
- `summary_max_length`: integer, `1..280`
- `state_file`: string
- `media_state_file`: string
- `selection_mode`: `score | round_robin`
- `rotation_state_file`: string

### `score_weights`

mapping:

- `likes`: number
- `retweets`: number
- `replies`: number
- `views`: number
- `velocity`: number
- `freshness`: number
- `image_bonus`: number

### `filters`

mapping:

- `max_age_hours`: number, `> 0`
- `required_terms`: list of string
- `exclude_keywords`: list of string

### 例

```yaml
defaults:
  dry_run: true
  summary_prefix: "Xで反応上位: "
  summary_language: "ja"
  summary_max_length: 280
  score_weights:
    likes: 1
    retweets: 1
    views: 1
    freshness: 0

  accounts:
  invest:
    dry_run: false
    selection_mode: "score"
    state_file: "state/invest-posted.txt"
    media_state_file: "state/invest-hot-selection.json"
    score_weights:
      retweets: 4
      replies: 5
      views: 0.02
      velocity: 2
      freshness: 6
      image_bonus: 12
    filters:
      max_age_hours: 6
      required_terms:
        - "$MU"
        - "Micron"
```
