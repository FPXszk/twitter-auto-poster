# RUNBOOK

`twitter-auto-poster` を安全に運用するための手順書です。

## 1. GitHub Secrets の設定

GitHub Actions で必要な Secrets は次の 2 つです。

- `TWITTER_AUTH_TOKEN`
- `TWITTER_CT0`

設定手順:

1. GitHub で対象 repository を開く
2. `Settings` → `Secrets and variables` → `Actions` を開く
3. `New repository secret` を選ぶ
4. `TWITTER_AUTH_TOKEN` を作成して保存
5. 同じ手順で `TWITTER_CT0` を作成して保存

値の取得方法:

1. ブラウザで `x.com` にログインする
2. 開発者ツールを開き、任意の `x.com` リクエストを選ぶ
3. `Cookie` から `auth_token` と `ct0` を抜き出す
4. 認証情報なので、平文で共有しない

## 2. ローカル → 手動実行 → 定期実行の流れ

### JPX 銘柄更新

JPX 銘柄更新 workflow (`update_tickers_jp.yml`) には Secrets は不要です。

ローカル確認:

1. `python/.venv/bin/pip install xlrd pyyaml` を実行する
2. `python/.venv/bin/python python/update_tickers_jp.py` を実行する
3. `config/tickers_jp.csv` と `config/tickers_jp.csv.bak` を確認する
4. `tmp/tickers_jp_update_summary.json` の件数・差分要約を確認する

GitHub Actions の手動実行:

1. Actions で `Update JP tickers` を開く
2. `Run workflow` から実行する
3. `Job summary` の件数・追加/削除/業種変更を確認する
4. artifact `tickers-jp-update` から `config/tickers_jp.csv` と `tmp/tickers_jp_update_summary.json` を確認する

### ローカル確認

1. `python/.venv/bin/twitter status --yaml` で認証確認
2. `bash scripts/fetch_search.sh --category invest` で JSON 取得確認
3. `bash scripts/fetch_and_post.sh --category invest --dry-run true` で候補文確認
4. `tmp/runs/` と `tmp/raw/` を見て、候補と元データが妥当か確認

### GitHub Actions の手動実行

1. Actions で `Post invest` または `Post news` を開く
2. `Run workflow` から `dry_run=true` を選んで実行
3. `Job summary` と artifact の `tmp/` を確認
4. summary の候補文と score 内訳が期待どおりなら次へ進む

### 定期実行へ移る前

1. `workflow_dispatch` で `dry_run=false` を 1 回だけ実行
2. 実際の投稿内容と `tmp/posted_ids.txt` / `tmp/state/*.txt` の更新を確認
3. 問題がなければ schedule に任せる

## 3. 障害時の復旧手順

### JPX XLS の列構成変更

症状:

- `update_tickers_jp.py` が header mismatch で失敗する
- Actions の `Job summary` に missing columns が表示される

対応:

1. artifact の `tmp/tickers_jp_update_summary.json` を開く
2. `error` の missing columns と sheet 名を確認する
3. JPX の XLS 列名変更であれば `config/tickers_jp_rules.yaml` と `python/update_tickers_jp.py` の想定を更新する
4. 既存の `config/tickers_jp.csv` は維持されていることを確認してから再実行する

### 認証エラー

症状:

- `twitter status` 失敗
- GitHub Actions で 401 / 403 / 226 が出る

対応:

1. ブラウザで X に再ログインする
2. `auth_token` と `ct0` を再取得する
3. GitHub Secrets を更新する
4. `workflow_dispatch` を `dry_run=true` で再実行する

### 重複候補・不適切候補の調査

確認場所:

- `tmp/runs/candidate-<category>.*`
- `tmp/raw/<category>/`
- workflow の `Job summary`

見るポイント:

- `selected.id`
- `selected.score`
- `selected.score_breakdown`
- `skipped_candidates`
- `warnings`

必要なら `config/accounts.yaml` の `filters` / `score_weights` を調整する。

### state のリセット

invest:

```bash
rm -f tmp/posted_ids.txt
```

news:

```bash
rm -f tmp/state/news-posted.txt
```

GitHub Actions 上の cache をリセットしたい場合は、新しい run を流して最新 state を上書きする。

## 4. live 投稿前チェックリスト

- `python/.venv/bin/twitter status --yaml` が成功する
- 対象 category が正しい
- 直前に `--dry-run true` または `workflow_dispatch dry_run=true` を確認した
- `Job summary` の score と要約文が妥当
- state ファイルに直近投稿 ID が入っている
- schedule を有効にする前に手動で 1 回だけ本番投稿を確認した
