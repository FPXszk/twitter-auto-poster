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

### buz 投稿の preview

```bash
bash scripts/fetch_and_post.sh --category buz --dry-run true
```

見る場所:

- `tmp/runs/candidate-buz.*`
- `tmp/raw/buz/`
- `tmp/runs/fetch-search-buz.json`

確認ポイント:

- `selected.text`
- `selected.score`
- `selected.score_breakdown`
- `selected.author_followers`
- `selected.image_urls`
- `post_candidates`
- `diagnostics.author_lookup`
- `diagnostics.summary_attempts`
- `skipped_candidates`
- `warnings`
- `rotation.selected_source`（どのアカウントのソースが選ばれたか）

### buz 投稿の live 実行

```bash
bash scripts/fetch_and_post.sh --category buz --post
```

live 前に必ず確認すること:

- 直前 preview の候補が妥当なバズツイートか
- 要約が 280 文字以内に収まっている
- 不要な転載・誇張になっていない

### news 投稿の preview / live

```bash
bash scripts/fetch_and_post.sh --category news --dry-run true
bash scripts/fetch_and_post.sh --category news --post
```

## 3. GitHub Actions の見方

主に見る workflow:

- `ci.yml`
- `post_buz.yml`
- `auto_follow.yml`
- `auto_like.yml`

`ci.yml` で見るポイント:

- `Run unit tests`
- `Validate shell scripts`
- `Validate Python modules`
- `Validate YAML files`
- PR をマージする前に全ステップが成功していること

`post_buz.yml` で見るポイント:

- Posting window
- Requested mode / Result mode
- collection.search
- Selected source / tweet / author
- Score breakdown
- Summary provider / model
- summary attempts / fallback candidates
- author lookup diagnostics
- skipped candidates count
- rotation（ラウンドロビン状態）

## 4. 不適切候補が出たとき

確認場所:

- `tmp/runs/candidate-<category>.*`
- `tmp/raw/<category>/`
- workflow summary

主な調整先:

- `config/sources.yaml`（クエリの閾値変更）
- `config/accounts.yaml`（exclude_keywords 追加）

## 5. 障害時の復旧

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
5. `post_candidates` と `diagnostics.summary_attempts` を見て fallback がどこで止まったか確認する

## 6. state の扱い

```bash
rm -f tmp/state/buz-posted.txt
rm -f tmp/state/buz-hot-selection.json
rm -f tmp/state/buz-robin.txt
rm -f tmp/state/news-posted.txt
```

## 7. session logs

- `just dev` で起動した Copilot CLI 終了時に `docs/working-memory/session-logs/` へ best-effort で要約を書き出します。
- これらのログは working memory 用であり、Git 追跡対象ではありません。
- 完全強制終了では保存されないことがあります。

## 8. live 投稿前チェックリスト

- 認証が成功している
- 対象 category が正しい
- preview を直前に確認した
- 候補がバズツイートとして妥当
- 要約が 280 文字以内に収まっている
- score と skipped reasons に違和感がない
- state 更新先を把握している
- 手動の 1 回目 live 実行で実際の投稿を確認済み
