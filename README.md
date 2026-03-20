# twitter-auto-poster

`twitter-cli` を使って、`news` と `invest` の 2 カテゴリを安全に収集・投稿するための最小構成です。

## 方針

- 既定は `dry-run` です
- 収集と投稿判定は `scripts/` に集約します
- 設定は `config/` の YAML に置きます
- GitHub Actions からもローカルからも同じスクリプトを呼びます

## 必要なもの

- `python3`
- `pyyaml`
- `twitter-cli`

ローカル例:

```bash
python3 -m pip install --user pyyaml
uv tool install twitter-cli
twitter whoami
```

`twitter-cli` の認証が通らない場合、各スクリプトは失敗します。まず `twitter whoami` または `twitter status --yaml` が成功する状態にしてください。

## 設定ファイル

### `config/sources.yaml`

収集元の定義です。`type: user` は `twitter user-posts`、`type: search` は `twitter search` を使います。

主な項目:

- `id`: 出力ファイル名にも使う識別子
- `category`: `news` または `invest`
- `type`: `user` / `search`
- `username`: user ソース用
- `query`: search ソース用
- `max_results`: 取得件数
- `exclude_retweets`: RT を除外するか

### `config/accounts.yaml`

カテゴリごとの投稿ポリシーです。

主な項目:

- `dry_run`: 既定の dry-run 挙動
- `post_prefix`: 投稿文の接頭辞
- `max_candidates`: 投稿候補に使う件数

## ローカル実行

ユーザー系ソースだけ取得:

```bash
bash scripts/fetch_user.sh --category news
```

検索系ソースだけ取得:

```bash
bash scripts/fetch_search.sh --category invest
```

投稿候補を作るが実投稿しない:

```bash
bash scripts/fetch_and_post.sh --category news --dry-run true
```

明示的に投稿する:

```bash
bash scripts/fetch_and_post.sh --category invest --post
```

実行結果は `tmp/` 配下に保存されます。

- `tmp/raw/<category>/`: 取得した JSON
- `tmp/runs/`: 投稿候補や投稿結果
- `tmp/state/<category>-posted.txt`: 投稿済み ID の簡易状態

## GitHub Actions

- `.github/workflows/post_news.yml`
- `.github/workflows/post_invest.yml`

どちらも `workflow_dispatch` と `schedule` を持ちます。スケジュール実行は安全のため常に `dry-run` です。手動実行時だけ `dry_run=false` を選べます。

必要な Secrets:

- `TWITTER_AUTH_TOKEN`
- `TWITTER_CT0`

注意:

- `twitter-cli` の write 操作は Cookie ベースのほうが安定します
- GitHub Actions 上では環境変数認証だけだと投稿時に 226 エラーになる場合があります
- そのため、この構成はまず dry-run 検証を優先しています
