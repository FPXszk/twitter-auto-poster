# twitter-auto-poster

`twitter-cli` を使って、`news` / `invest` 系の情報収集投稿と、日本株サマリーの定時投稿を行う自動化プロジェクトです。

現状は **`dry-run` 既定の MVP** として構成してあり、ローカル実行と GitHub Actions の両方で同じスクリプトを使います。

## プロジェクト概要

このリポジトリは次の流れを扱います。

1. `config/sources.yaml` から収集対象を読む
2. `twitter-cli` でユーザー投稿または検索結果を取得する
3. 投稿済み ID を避けながら候補を選ぶ
4. `dry-run` では候補文だけ表示する
5. 明示的に投稿モードにしたときだけ `twitter post` を実行する
6. 日本株サマリーでは `yfinance` で東証プライム銘柄を集計し、朝夕の要約を投稿する

## ディレクトリ構成

```text
.
├── .agents/
│   └── skills/twitter-cli/SKILL.md
├── config/
│   ├── accounts.yaml
│   ├── sources.yaml
│   └── tickers_jp.csv
├── python/
│   ├── stock_fetcher.py
│   ├── morning_summary.py
│   └── evening_summary.py
├── scripts/
│   ├── lib/
│   │   └── common.sh
│   ├── fetch_and_post.sh
│   ├── fetch_search.sh
│   └── fetch_user.sh
├── .github/
│   └── workflows/
│       ├── evening_post.yml
│       ├── morning_post.yml
│       ├── post_invest.yml
│       └── post_news.yml
├── devinit.sh
├── justfile
└── twitter-auto-poster.log
```

## 主要ファイルの役割

### `scripts/`

- `scripts/lib/common.sh`
  - 共通関数
  - 依存コマンド確認
  - 認証確認
  - `tmp/` 出力ディレクトリ管理
  - YAML 読み出し補助
- `scripts/fetch_user.sh`
  - `type: user` の source を読み、`twitter user-posts` を実行
- `scripts/fetch_search.sh`
  - `type: search` の source を読み、`twitter search` を実行
- `scripts/fetch_and_post.sh`
  - 収集 → スコア選定 → 日本語要約 → `dry-run` 表示 or 実投稿 のオーケストレーション

### `config/`

- `config/sources.yaml`
  - 収集対象の一覧
  - `news` / `invest`
  - `user` / `search`
  - クエリ、ユーザー名、取得件数など
- `config/accounts.yaml`
  - カテゴリ別の投稿ポリシー
  - `dry_run`
  - `post_prefix`
  - `max_candidates`

### `.github/workflows/`

- `post_news.yml`
  - `news` 用の定期実行 / 手動実行
- `post_invest.yml`
  - `invest` 用の定期実行 / 手動実行
- `morning_post.yml`
  - 日本株の朝まとめ投稿
- `evening_post.yml`
  - 日本株の夜総括投稿

各 workflow は state をキャッシュし、`tmp/` を artifact として保存します。

## 必要なもの

- `python3`
- `pyyaml`
- `pandas`
- `yfinance`
- `twitter-cli`
- `tmux`
- `lazygit`
- `gh`
- `just`

ローカルの最低限セットアップ例:

```bash
python3 -m pip install --user pyyaml
python3 -m pip install --user pandas yfinance
uv tool install twitter-cli
twitter whoami
```

`twitter-cli` の認証確認:

```bash
twitter status --yaml
twitter whoami
```

これが失敗する場合、各スクリプトも失敗します。

## ローカル起動コマンド

### 開発セッション起動

`just dev` で `devinit.sh` を起動します。

```bash
just dev
```

`devinit.sh` は `tmux` セッション `twitter-auto-poster` を作り、3 ペイン構成で起動します。

- `copilot`
- `logs`
- `git`

内部的には以下を行います。

- `gh auth status` を確認
- 必要なら GitHub ログイン
- Copilot CLI を起動
- `twitter-auto-poster.log` を tail
- `lazygit` を起動

### 開発セッション停止

```bash
just stop
```

### ログ監視

```bash
just logs
```

## 収集・投稿コマンド

### ユーザー系 source を取得

```bash
bash scripts/fetch_user.sh --category news
bash scripts/fetch_user.sh --category invest
```

### 検索系 source を取得

```bash
bash scripts/fetch_search.sh --category news
bash scripts/fetch_search.sh --category invest
```

### 候補生成のみ

```bash
bash scripts/fetch_and_post.sh --category news --dry-run true
bash scripts/fetch_and_post.sh --category invest --dry-run true
```

### 明示的に投稿する

```bash
bash scripts/fetch_and_post.sh --category news --post
bash scripts/fetch_and_post.sh --category invest --post
```

### 日本株サマリーを手動確認する

```bash
python3 -m venv python/.venv
python/.venv/bin/pip install --upgrade pip
python/.venv/bin/pip install pandas yfinance twitter-cli
python/.venv/bin/python python/update_tickers.py
python/.venv/bin/python python/morning_summary.py --dry-run --cache-path tmp/stock_cache.json
python/.venv/bin/python python/evening_summary.py --dry-run --cache-path tmp/stock_cache.json
```

### 日本株サマリーを実投稿する

```bash
python/.venv/bin/python python/update_tickers.py
python/.venv/bin/python python/morning_summary.py --cache-path tmp/stock_cache.json
python/.venv/bin/python python/evening_summary.py --cache-path tmp/stock_cache.json
```

## 保守・確認コマンド

普段よく使うものをまとめると以下です。

```bash
just dev
just logs
just stop
twitter status --yaml
git --no-pager status --short
python/.venv/bin/python -m py_compile python/stock_fetcher.py python/stock_cache.py python/update_tickers.py python/morning_summary.py python/evening_summary.py
```

README や workflow を触ったときの軽い確認例:

```bash
bash -n scripts/lib/common.sh scripts/fetch_user.sh scripts/fetch_search.sh scripts/fetch_and_post.sh
python3 -m py_compile scripts/lib/post_scoring.py scripts/lib/post_summary.py scripts/lib/post_filters.py
python3 - <<'PY'
from pathlib import Path
import yaml
for path in [Path('config/sources.yaml'), Path('config/accounts.yaml'), Path('.github/workflows/post_news.yml'), Path('.github/workflows/post_invest.yml')]:
    yaml.safe_load(path.read_text(encoding='utf-8'))
print('OK')
PY
```

## 実行結果の保存先

実行時には `tmp/` 配下にファイルが作られます。

- `tmp/raw/<category>/`
  - 取得した JSON レスポンス
- `tmp/runs/`
  - 投稿候補や投稿結果の一時ファイル
- `tmp/state/<category>-posted.txt`
  - 投稿済み ID の簡易 state
- `tmp/posted_ids.txt`
  - `post_invest.yml` と日本株 summary workflow が使う投稿済み ID / 実行済みマーカーの簡易 state

## ドキュメント

- `docs/RUNBOOK.md`
  - Secrets 設定、`workflow_dispatch` から schedule への移行、障害復旧の手順
- `docs/SCHEMA.md`
  - `config/sources.yaml` と `config/accounts.yaml` の schema
- `docs/PLAN.md`
  - 日本株サマリー機能の実装要件

## GitHub Actions

### 対象 workflow

- `.github/workflows/post_news.yml`
- `.github/workflows/post_invest.yml`
- `.github/workflows/morning_post.yml`
- `.github/workflows/evening_post.yml`
- `.github/workflows/update_tickers.yml`

### 挙動

- `workflow_dispatch` 対応
- `schedule` 対応
- `dry_run` 入力あり
- `post_invest.yml` は `python/.venv/bin/twitter` を使い、毎時間の自動投稿を行います
- `morning_post.yml` は平日 08:00 JST 向けに日本株の朝まとめを投稿します
- `evening_post.yml` は平日 18:00 JST 向けに日本株の夜総括を投稿します
- `update_tickers.yml` は 00:00 JST 毎日と 17:00 JST 平日に銘柄キャッシュを更新します
- Python 3.11 をセットアップ
- `pyyaml` / `pandas` / `yfinance` / `twitter-cli` をインストール
- state を cache restore/save
- 日本株 summary workflow は `update_tickers.yml` が保存した `stock-cache` artifact を復元して使います
- 初回デプロイ時は先に `update_tickers.yml` を手動実行してください。`stock-cache` artifact を取得できない場合、朝夕 summary workflow は fail-fast します
- `tmp/` を artifact 保存
- `post_news.yml` / `post_invest.yml` は `Job summary` に選ばれた候補、score 内訳、要約文を出力します

### 必要な Secrets

- `TWITTER_AUTH_TOKEN`
- `TWITTER_CT0`

### 使い方

まずは **手動実行 + `dry_run=true`** で試すのがおすすめです。

## 設定ファイルの見方

### `config/sources.yaml`

主なキー:

- `id`
- `category`
- `type`
- `enabled`
- `username`
- `query`
- `timeline`
- `max_results`
- `exclude_retweets`

### `config/accounts.yaml`

主なキー:

- `dry_run`
- `post_prefix`
- `max_candidates`
- `summary_prefix`
- `summary_language`
- `summary_max_length`
- `state_file`
- `score_weights`
- `filters`

## 運用上の注意

- 既定は `dry-run` です
- 投稿を有効にするのは `--post` または `--dry-run false` を明示したときだけです
- GitHub Actions 上では環境変数認証のみだと 226 エラーが出る可能性があります
- `twitter-cli` の write 系は Cookie ベース認証のほうが安定します
- state は重複投稿防止のために使います

## 今の前提

この README は **現在の実装状態** に合わせて書いています。
将来的に候補選定ロジック、投稿文整形、state 永続化の方式、workflow の運用方針を変えた場合は README も一緒に更新してください。
