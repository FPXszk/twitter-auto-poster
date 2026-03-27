# RUNBOOK

## この文書の役割

- この文書は `twitter-auto-poster` の運用手順書です。
- 設定キーの意味は `docs/SCHEMA.md`、戦略判断は `docs/design-docs/STRATEGY.md` を参照してください。

## 1. 事前準備

### ローカル認証

最低限確認すること:

1. `twitter status --yaml`
2. `twitter whoami`
3. `copilot --version`
4. `gh auth status`

### GitHub Secrets

GitHub Actions で必要な Secrets:

- `TWITTER_AUTH_TOKEN`
- `TWITTER_CT0`
- `COPILOT_GITHUB_TOKEN`

## 2. 日常運用フロー

### invest 投稿の preview

```bash
bash scripts/fetch_and_post.sh --category invest --dry-run true
```

見る場所:

- `tmp/runs/candidate-invest.*`
- `tmp/raw/invest/`
- `tmp/runs/fetch-search-invest.json`

確認ポイント:

- `selected.text`
- `selected.score`
- `selected.score_breakdown`
- `selected.author_followers`
- `selected.author_verified`
- `selected.image_urls`
- `skipped_candidates`
- `warnings`

### invest 投稿の live 実行

```bash
bash scripts/fetch_and_post.sh --category invest --post
```

live 前に必ず確認すること:

- 直前 preview の候補が投資テーマとして妥当
- 要約が 280 文字以内に収まっている
- 画像付き候補なら添付画像が妥当
- 不要な転載・誇張になっていない

### news 投稿の preview / live

```bash
bash scripts/fetch_and_post.sh --category news --dry-run true
bash scripts/fetch_and_post.sh --category news --post
```

## 3. 日本株サマリー運用

### 手動確認

```bash
python3 -m venv python/.venv
python/.venv/bin/pip install --upgrade pip
python/.venv/bin/pip install pandas yfinance twitter-cli xlrd pyyaml googletrans==4.0.0rc1
python/.venv/bin/python python/update_tickers_jp.py
python/.venv/bin/python python/update_tickers.py --summary-output tmp/stock_cache_summary.json
python/.venv/bin/python python/morning_summary.py --dry-run --cache-path tmp/stock_cache.json --summary-output tmp/morning_summary.json
python/.venv/bin/python python/evening_summary.py --dry-run --cache-path tmp/stock_cache.json --summary-output tmp/evening_summary.json
```

### 確認ポイント

- `tmp/stock_cache_summary.json`
- `tmp/morning_summary.json`
- `tmp/evening_summary.json`
- 文字数上限
- 採用された variant
- stale cache や skipped reasons

## 4. GitHub Actions の見方

主に見る workflow:

- `post_invest.yml`
- `morning_post.yml`
- `evening_post.yml`
- `update_tickers_jp.yml`

`post_invest.yml` で見るポイント:

- Posting window
- Requested mode / Result mode
- collection.user / collection.search
- Selected source / tweet / author
- Score breakdown
- Summary provider / model
- skipped candidates count

## 5. 不適切候補が出たとき

確認場所:

- `tmp/runs/candidate-<category>.*`
- `tmp/raw/<category>/`
- workflow summary

主な調整先:

- `config/sources.yaml`
- `config/accounts.yaml`

## 6. 障害時の復旧

### X 認証エラー

1. X に再ログイン
2. `auth_token` と `ct0` を再取得
3. GitHub Secrets 更新
4. preview 実行で復旧確認

### Copilot 要約失敗

1. `COPILOT_GITHUB_TOKEN` を確認
2. `copilot --version` と認証状態を確認
3. preview 実行で再確認
4. 必要なら summary provider を一時的に切り替える

### JPX XLS 変更

1. `tmp/tickers_jp_update_summary.json` を確認
2. 列名変更を特定
3. `config/tickers_jp_rules.yaml` とスクリプトを更新

## 7. state の扱い

```bash
rm -f tmp/state/invest-posted.txt
rm -f tmp/state/invest-hot-selection.json
rm -f tmp/state/news-posted.txt
```

## 8. session logs

- `just dev` で起動した Copilot CLI 終了時に `docs/working-memory/session-logs/` へ best-effort で要約を書き出します。
- これらのログは working memory 用であり、Git 追跡対象ではありません。
- 完全強制終了では保存されないことがあります。

## 9. live 投稿前チェックリスト

- 認証が成功している
- 対象 category が正しい
- preview を直前に確認した
- 候補が投資/ニュースとして妥当
- 要約がそのまま転載になっていない
- score と skipped reasons に違和感がない
- state 更新先を把握している
- 手動の 1 回目 live 実行で実際の投稿を確認済み
