# twitter-auto-poster

`twitter-cli` を使って、バズツイートの自動収集・投稿と、自動フォロー・自動いいねを行う自動化プロジェクトです。

カテゴリごとに `dry_run` / live-post を切り替えられる構成で、ローカル実行と GitHub Actions の両方で同じスクリプトを使います。

## プロジェクト概要

このリポジトリは次の流れを扱います。

1. `config/sources.yaml` から収集対象を読む（バズ系アカウントの人気ツイート）
2. `twitter-cli` で検索結果を取得する
3. 投稿済み ID を避けながらスコア順またはラウンドロビンで候補を選ぶ
4. `dry-run` では候補文だけ表示する
5. Copilot CLI が 280 文字以内に整形する
6. 対象 category の設定が live-post のときだけ `twitter post` を実行する（単発投稿）

## ディレクトリ構成

```text
.
├── .agents/
│   └── skills/twitter-cli/SKILL.md
├── config/
│   ├── accounts.yaml
│   ├── sources.yaml
│   └── copilot_summary_prompt_ja.txt
├── python/
│   ├── auto_follow.py
│   ├── auto_unfollow.py
│   └── auto_like.py
├── scripts/
│   ├── lib/
│   │   └── common.sh
│   ├── fetch_and_post.sh
│   ├── fetch_search.sh
│   └── fetch_user.sh
├── .github/
│   └── workflows/
│       ├── post_buz.yml
│       ├── auto_follow.yml
│       └── auto_like.yml
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
  - `buz` / `news`
  - `search` クエリ、取得件数
- `config/accounts.yaml`
  - カテゴリ別の投稿ポリシーと workflow 実行モードの設定元
  - `dry_run`
  - `selection_mode`（`score` / `round_robin` / `round_robin_account`）
  - `fallback_candidates`
  - `rotation_state_file`
  - `summary_provider` / `summary_model` / `summary_prompt_path`
- `config/copilot_summary_prompt_ja.txt`
  - 280 文字以内整形用の Copilot プロンプト
- `config/follow_state.json`
  - auto follow / auto unfollow の履歴 state

### `.github/workflows/`

- `post_buz.yml`
  - `buz` 用の定期実行（JST 08:00〜24:00、毎時）/ 手動実行
- `auto_follow.yml`
  - 日次の auto follow / auto unfollow（`@tkzwgrs` フォロワーから選定）
- `auto_like.yml`
  - 定期の auto like
- `twitter_diagnostic.yml`
  - アカウント診断と日次スコア予測
- `morning_post.yml` / `evening_post.yml` / `update_tickers.yml` / `update_tickers_jp.yml`
  - 投資系ワークフロー（スケジュール停止中・手動実行のみ）

各 workflow は state をキャッシュし、`tmp/` を artifact として保存します。

### `docs/`

- `docs/RUNBOOK.md`
  - 運用手順と復旧手順
- `docs/design-docs/STRATEGY.md`
  - X 成長戦略

## 必要なもの

- `python3`
- `pyyaml`
- `twitter-cli`
- `copilot`
- `tmux`
- `lazygit`
- `gh`
- `just`

ローカルの最低限セットアップ例:

```bash
npm install -g @github/copilot
copilot login
python3 -m pip install --user pyyaml
uv tool install twitter-cli
twitter whoami
```

`twitter-cli` の認証確認:

```bash
twitter status --yaml
twitter whoami
```

これが失敗する場合、各スクリプトも失敗します。

GitHub Actions で Copilot 要約を使う場合は、`COPILOT_GITHUB_TOKEN` secret に Copilot Requests 権限付きトークンを設定してください。

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

### 検索系 source を取得

```bash
bash scripts/fetch_search.sh --category buz
bash scripts/fetch_search.sh --category news
```

### 候補生成のみ

```bash
bash scripts/fetch_and_post.sh --category buz --dry-run true
bash scripts/fetch_and_post.sh --category news --dry-run true
```

### 明示的に投稿する

```bash
bash scripts/fetch_and_post.sh --category buz --post
bash scripts/fetch_and_post.sh --category news --post
```

### auto follow を手動確認する

```bash
python/.venv/bin/python python/auto_follow.py --target-username tkzwgrs
python/.venv/bin/python python/auto_unfollow.py
```

`auto_follow.py` は `@tkzwgrs` のフォロワーを最大 1000 人まで調べ、プロフィールまたは直近投稿に日本語シグナルと株関連キーワードがある候補を follow します。`auto_unfollow.py` は `config/follow_state.json` を見て、7 日以上経過して未フォローバックの相手だけをランダム件数 unfollow します。

### auto like を手動確認する

```bash
python/.venv/bin/python python/auto_like.py --dry-run
python/.venv/bin/python python/auto_like.py
```

`auto_like.py` は for-you タイムラインから直近候補を集め、`300` 以上いいね済みの投稿を除外しつつ、できるだけ「新しく・まだいいね数が少ない」投稿を優先して 1 回ごとに `5〜15` 件の like をします。連続 like の待機は `2〜8秒` です。

## 保守・確認コマンド

普段よく使うものをまとめると以下です。

```bash
just dev
just logs
just stop
twitter status --yaml
git --no-pager status --short
python/.venv/bin/python -m py_compile python/auto_follow.py python/auto_unfollow.py python/auto_like.py
python/.venv/bin/python -m unittest discover -s tests
```

README や workflow を触ったときの軽い確認例:

```bash
bash -n scripts/lib/common.sh scripts/fetch_user.sh scripts/fetch_search.sh scripts/fetch_and_post.sh
python3 -m py_compile scripts/lib/post_scoring.py scripts/lib/post_summary.py scripts/lib/post_filters.py
python3 - <<'PY'
from pathlib import Path
import yaml
for path in [Path('config/sources.yaml'), Path('config/accounts.yaml'), Path('.github/workflows/post_buz.yml')]:
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
  - `fetch-search-*.json` に収集成否サマリーも保存される
- `tmp/state/<category>-posted.txt`
  - 投稿済み ID の簡易 state
- `tmp/state/buz-robin.txt`
  - `post_buz.yml` が前回投稿ソースを保持する round-robin state
- `tmp/state/liked_ids.txt`
  - `auto_like.py` が 7 日分の like 済み tweet ID と日時を保持する state

## ドキュメント

- `docs/RUNBOOK.md`
  - Secrets 設定、障害復旧の手順
- `docs/SCHEMA.md`
  - `config/sources.yaml` と `config/accounts.yaml` の schema
- `docs/design-docs/STRATEGY.md`
  - X 成長戦略

## GitHub Actions

### 対象 workflow（稼働中）

- `.github/workflows/ci.yml` — `push` / `pull_request` で tests・shell 構文・Python compile・YAML 検証
- `.github/workflows/post_buz.yml` — バズツイート投稿（毎時、JST 08:00〜24:00）
- `.github/workflows/auto_follow.yml` — 日次 auto follow / auto unfollow
- `.github/workflows/auto_like.yml` — 定期 auto like

### 対象 workflow（スケジュール停止・手動実行のみ）

- `.github/workflows/morning_post.yml`
- `.github/workflows/evening_post.yml`
- `.github/workflows/update_tickers.yml`
- `.github/workflows/update_tickers_jp.yml`
- `.github/workflows/twitter_diagnostic.yml`

### 挙動

- `ci.yml` は `main` への push と pull request ごとに既存の検証コマンドを自動実行します
- `workflow_dispatch` 対応
- `schedule` 対応
- `post_buz.yml` は `config/accounts.yaml` の `dry_run` を読んで preview/live-post を切り替えます
- `post_buz.yml` は毎時実行ですが、実投稿は JST 08:00〜24:00 のみです
- `post_buz.yml` は既定で live-post です
- `post_buz.yml` は `from:account` クエリで特定アカウントのバズツイートを収集します
- 候補選定は `likes` / `retweets` / `replies` / `views` / `velocity` / `freshness` / source ごとの `score_boost` を合算します
- `post_buz.yml` は `round_robin` モードで 6 ソースをローテーションします
- 実投稿経路は単発投稿（引用ツイート・スレッドなし）です
- Copilot 要約は 280 文字以内・改行なし の 1 投稿向け本文へ整形します
- `auto_like.yml` は毎時実行ですが JST 02:00〜05:00 を避けます

### 投稿系 workflow に必要な Secrets

- `TWITTER_AUTH_TOKEN`
- `TWITTER_CT0`
- `COPILOT_GITHUB_TOKEN`（Copilot 要約を使う場合）

### 使い方

現状の `config/accounts.yaml` では `post_buz.yml` は **live-post** 既定です。preview に戻したい場合も workflow ではなく config 側を変更します。

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
- `score_boost`
- `filters`

### `config/accounts.yaml`

主なキー:

- `dry_run`
- `post_prefix`
- `max_candidates`
- `summary_prefix`
- `summary_language`
- `summary_max_length`
- `single_post_max_length`
- `state_file`
- `selection_mode`
- `fallback_candidates`
- `rotation_state_file`
- `summary_provider`
- `summary_model`
- `summary_prompt_path`
- `score_weights`
- `filters`

`post_buz.yml` / `post_invest.yml` はこの `dry_run` を読んで実行モードを決めます。`selection_mode: round_robin` は source 単位、`selection_mode: round_robin_account` は account 単位で前回投稿元を回し、どちらも `rotation_state_file` を使って直前 state を保持します。`fallback_candidates` は summary 生成失敗や投稿失敗時に次候補へ進める上限件数です。

`single_post_max_length` は単発投稿を thread に分けずに送れる上限で、`twitter-cli` の実投稿制限に合わせて 280 を上限にします。

## 運用上の注意

- `post_invest` の既定は live-post です
- ローカルの `scripts/fetch_and_post.sh` は `config/accounts.yaml` の `dry_run` を既定値として読み、`--post` / `--dry-run <bool>` で上書きできます
- GitHub Actions の `post_invest.yml` は `config/accounts.yaml` の `dry_run` を参照します
- GitHub Actions 上では環境変数認証のみだと 226 エラーが出る可能性があります
- `twitter-cli` の write 系は Cookie ベース認証のほうが安定します
- state は重複投稿防止のために使います

## 今の前提

この README は **現在の実装状態** に合わせて書いています。

今後の投稿文・要約文の作成方針は `docs/POSTING_STRATEGY.md` を基準にしてください。
将来的に候補選定ロジック、投稿文整形、state 永続化の方式、workflow の運用方針を変えた場合は README も一緒に更新してください。
