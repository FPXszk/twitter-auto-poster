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
    timeline: top
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
- `summary_max_length`: integer, `> 0`
- `state_file`: string

### `score_weights`

mapping:

- `likes`: number
- `retweets`: number
- `views`: number

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
  summary_max_length: 140
  score_weights:
    likes: 1
    retweets: 1
    views: 1

accounts:
  invest:
    state_file: "posted_ids.txt"
    filters:
      max_age_hours: 24
      required_terms:
        - "$MU"
        - "Micron"
```
