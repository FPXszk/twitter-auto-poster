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

朝夕の投稿文面は `docs/POSTING_STRATEGY.md` を主基準とし、X Premium 前提で全文を組み立てつつ、タイムラインで見える冒頭140字のフックを重視します。

## ディレクトリ構成

```text
.
├── .agents/
│   └── skills/twitter-cli/SKILL.md
├── config/
│   ├── accounts.yaml
│   ├── sources.yaml
│   ├── tickers_jp_rules.yaml
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
│       ├── post_news.yml
│       └── update_tickers_jp.yml
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
- `scripts/lib/post_publish.sh`
  - 実投稿と投稿済み state 更新
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
   - クエリ、ユーザー名、取得件数、optional な source 単位 `filters`
- `config/accounts.yaml`
   - カテゴリ別の投稿ポリシーと workflow 実行モードの設定元
  - `dry_run`
  - `post_prefix`
  - `max_candidates`
- `config/tickers_jp_rules.yaml`
  - JPX XLS から `tickers_jp.csv` を作るときの市場ラベルと除外キーワード
- `config/stock_fetcher.yaml`
  - 異常騰落率フィルタの閾値と summary 詳細件数
- `config/jpx_calendar.json`
  - JPX の追加休場日 / 追加営業日を例外設定する

### `.github/workflows/`

- `post_news.yml`
  - `news` 用の定期実行 / 手動実行
- `post_invest.yml`
  - `invest` 用の定期実行 / 手動実行
- `morning_post.yml`
  - 日本株の朝まとめ投稿
- `evening_post.yml`
  - 日本株の夜総括投稿
- `twitter_diagnostic.yml`
  - アカウント診断と日次スコア予測
- `update_tickers.yml`
  - 日本株サマリー用の `stock-cache` 更新
- `update_tickers_jp.yml`
  - JPX XLS ベースの月次銘柄更新

各 workflow は state をキャッシュし、`tmp/` を artifact として保存します。
日本株系 workflow は JPX 非営業日（土日・祝日・年始年末休場）を自動でスキップします。

### `docs/`

- `docs/POSTING_STRATEGY.md`
  - 投稿文・要約文の主基準（single source of truth）
- `docs/RUNBOOK.md`
  - 運用手順と復旧手順

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

シェルスクリプトは既定で `python/.venv/bin/python3` を優先し、必要なら `PYTHON_BIN` で override できます。

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
python/.venv/bin/pip install pandas yfinance twitter-cli xlrd pyyaml
python/.venv/bin/python python/update_tickers_jp.py
python/.venv/bin/python python/update_tickers.py --summary-output tmp/stock_cache_summary.json
python/.venv/bin/python python/morning_summary.py --dry-run --cache-path tmp/stock_cache.json --summary-output tmp/morning_summary.json
python/.venv/bin/python python/evening_summary.py --dry-run --cache-path tmp/stock_cache.json --summary-output tmp/evening_summary.json
```

### 日本株サマリーを実投稿する

```bash
python/.venv/bin/python python/update_tickers_jp.py
python/.venv/bin/python python/update_tickers.py --summary-output tmp/stock_cache_summary.json
python/.venv/bin/python python/morning_summary.py --cache-path tmp/stock_cache.json --summary-output tmp/morning_summary.json
python/.venv/bin/python python/evening_summary.py --cache-path tmp/stock_cache.json --summary-output tmp/evening_summary.json
```

`python/update_tickers.py`、`python/morning_summary.py`、`python/evening_summary.py` は JPX 非営業日だと `0` で終了して処理をスキップします。`update_tickers_jp.yml` は毎月の初営業日だけ実行されるように制御しています。

`tmp/stock_cache.json` は metadata 付きで保存され、`trade_date`、生成時刻、異常値 skip 件数を持ちます。朝夕 summary はこの metadata と `summary-output` JSON を使って stale cache や文字数・採用パターンを確認できます。

朝サマリーは `docs/POSTING_STRATEGY.md` の朝テンプレートに合わせて `52週高値更新中` の上位銘柄を並べ、夜サマリーは `🗾 日経平均` 行と `値上がり率TOP3` / `値下がり率TOP3` を出力します。GitHub Actions の summary では全文に加えて先頭140文字の preview も確認できます。

## 保守・確認コマンド

普段よく使うものをまとめると以下です。

```bash
just dev
just logs
just stop
twitter status --yaml
git --no-pager status --short
python/.venv/bin/python -m py_compile python/stock_fetcher.py python/stock_cache.py python/update_tickers.py python/update_tickers_jp.py python/morning_summary.py python/evening_summary.py
python/.venv/bin/python -m unittest discover -s tests
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
  - `fetch-user-*.json` / `fetch-search-*.json` に収集成否サマリーも保存される
- `tmp/state/<category>-posted.txt`
  - 投稿済み ID の簡易 state
- `tmp/posted_ids.txt`
  - `post_invest.yml` と日本株 summary workflow が使う投稿済み ID / 実行済みマーカーの簡易 state
- `tmp/*_summary.json`
  - stock cache / morning / evening の実行結果サマリー

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
- `.github/workflows/update_tickers_jp.yml`

### 挙動

- `workflow_dispatch` 対応
- `schedule` 対応
- `workflow_dispatch` では手動実行できます
- `post_news.yml` / `post_invest.yml` は `config/accounts.yaml` の `dry_run` を読んで preview/live-post を切り替えます
- `post_invest.yml` は毎時間の候補収集とプレビューを行います（現状は GitHub Actions から実投稿しません）
- `morning_post.yml` は平日 08:00 JST 向けに日本株の朝まとめを投稿します
- `evening_post.yml` は平日 18:00 JST 向けに日本株の夜総括を投稿します
- `twitter_diagnostic.yml` は毎朝 04:00 JST に `twitter whoami` / recent posts を使ってアカウント診断を行い、`docs/POSTING_STRATEGY.md` ベースの推定スコアを記録します
- `update_tickers.yml` は 00:00 JST 毎日と 17:00 JST 平日に銘柄キャッシュを更新します
- `update_tickers_jp.yml` は毎月 1 日 06:00 JST に JPX XLS から `config/tickers_jp.csv` を更新して artifact 保存します
- `update_tickers_jp.yml` は `tmp/tickers_jp_update_summary.json` と `GITHUB_STEP_SUMMARY` に件数・差分要約も出力します
- `morning_post.yml` / `evening_post.yml` / `update_tickers.yml` も `GITHUB_STEP_SUMMARY` に文字数、採用パターン、skip 理由、異常値 skip 要約を出力します
- `twitter_diagnostic.yml` は `tmp/diagnostics/account-score-history.jsonl` を Actions cache + artifact に保存し、summary へ当日の内訳と改善提案を表示します
- 主要 workflow は依存インストール後に runtime diagnostics を実行し、使用 Python と import 可否を artifact / summary 用 JSON に残します
- Python 3.11 をセットアップ
- `pyyaml` / `pandas` / `yfinance` / `twitter-cli` をインストール
- state を cache restore/save
- 日本株 summary workflow は `update_tickers.yml` が保存した `stock-cache` artifact を復元して使います
- 初回デプロイ時は先に `update_tickers.yml` を手動実行してください。`stock-cache` artifact を取得できない場合、朝夕 summary workflow は fail-fast します
- `tmp/` を artifact 保存
- `post_news.yml` / `post_invest.yml` は `Job summary` に選ばれた候補、score 内訳、要約文を出力します

### 投稿系 workflow に必要な Secrets

- `TWITTER_AUTH_TOKEN`
- `TWITTER_CT0`

`update_tickers_jp.yml` ではこれらの Secrets は不要です。

### JPX 銘柄更新ルール

- `config/tickers_jp_rules.yaml` に対象市場ラベルと除外キーワードを定義します
- 現状は東証プライム系ラベルのみを対象にし、`ETF` / `REIT` / `投資法人` / `優先株` を除外します
- `python/update_tickers_jp.py` 実行後は `tmp/tickers_jp_update_summary.json` に件数と差分要約が出力されます

### 使い方

現状の `config/accounts.yaml` では `post_news.yml` / `post_invest.yml` は **dry-run** です。将来 live-post を再開する場合も workflow ではなく config 側を変更します。

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
- `filters`

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

`post_news.yml` / `post_invest.yml` はこの `dry_run` を読んで実行モードを決めます。

## 運用上の注意

- 既定は `dry-run` です
- ローカルの `scripts/fetch_and_post.sh` では `--post` または `--dry-run false` を明示したときだけ投稿します
- GitHub Actions の `post_news.yml` / `post_invest.yml` は `config/accounts.yaml` の `dry_run` を参照します
- GitHub Actions 上では環境変数認証のみだと 226 エラーが出る可能性があります
- `twitter-cli` の write 系は Cookie ベース認証のほうが安定します
- state は重複投稿防止のために使います

## 今の前提

この README は **現在の実装状態** に合わせて書いています。

今後の投稿文・要約文の作成方針は `docs/POSTING_STRATEGY.md` を基準にしてください。
将来的に候補選定ロジック、投稿文整形、state 永続化の方式、workflow の運用方針を変えた場合は README も一緒に更新してください。
