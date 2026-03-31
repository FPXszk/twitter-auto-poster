# 実装計画: post_buz 実運用確認 + post_pic ワークフロー追加

**作成日時**: 2026-03-31 09:30 JST  
**ステータス**: PLAN (レビュー待ち)

---

## 概要

2本立ての作業:

1. **post_buz ワークフローの実運用確認** — `workflow_dispatch` で手動実行し、artifact / summary を確認する手順の策定と実行
2. **post_pic ワークフローの新規追加** — 画像のみのアカウント (`japanofcontext`, `kjckikyo`, `yureiyks`) からバズ画像を取得して投稿する

---

## Part 1: post_buz 実運用確認

### 確認手順

#### 1-1. workflow_dispatch による dry-run 実行

```bash
gh workflow run post_buz.yml -f dry_run=true
```

#### 1-2. 実行結果の確認ポイント

| 確認項目 | 確認方法 |
|---|---|
| ワークフロー起動 | `gh run list --workflow=post_buz.yml --limit 3` で status を確認 |
| ジョブ完了 | `gh run view <run_id>` で conclusion=success を確認 |
| posting_window ステップ | Summary の `Posting window allowed` が `true` (JST 7:00–1:00 内の場合) |
| account_mode | Summary の `Requested mode` が `preview` (dry_run=true の場合) |
| 候補取得 | Summary の `Payload files` ≥ 1 を確認 |
| ラウンドロビン | Summary の `Previous source` / `Selected source` / `Next source` が正しくローテーションしているか |
| 要約生成 | Summary の `Summary provider: copilot_cli`、`Summary` に日本語テキストが出ているか |
| 画像交互 | Summary の `Target media mode` / `Selected media mode` を確認 |
| auto-reply | Summary の `Auto reply summary` セクションの status |

#### 1-3. artifact の確認

```bash
gh run view <run_id> --log     # ログ全体
gh run download <run_id>        # artifact をダウンロード
```

ダウンロードした `buz-run/` に以下が含まれていること:
- `runs/candidate-buz.*.json` — 候補選定結果
- `runs/fetch-search-buz.json` — 検索取得ステータス
- `state/` — ローテーション・メディア・フィードバック状態ファイル
- `buz-runtime.json` — ランタイム診断

#### 1-4. 本番実行 (dry_run=false)

posting_window 内であることを確認した上で:

```bash
gh workflow run post_buz.yml -f dry_run=false
```

確認ポイント:
- Summary に `Posted tweet: [tweet_id](url)` が表示されるか
- state cache が保存されるか (`Save post state` ステップ成功)
- 次回実行でラウンドロビンが次のアカウントに進むか

### post_buz に関する実装変更: なし

既存のワークフローをそのまま実行して確認する。コード変更は不要。

---

## Part 2: post_pic ワークフロー追加

### 設計方針

- **既存の `fetch_and_post.sh` ロジックを100%再利用する** — 新しいカテゴリ `pic` を `sources.yaml` / `accounts.yaml` に追加するだけで動作する設計
- `post_buz.yml` とほぼ同じ構造のワークフロー `post_pic.yml` を作成
- 画像のみを対象とするために:
  - `sources.yaml` の検索クエリに `filter:images` を追加
  - `accounts.yaml` の `pic` アカウント設定で `selection_mode: round_robin_account` を使用
  - `media_state_file` を設定し画像優先選択を活用（ただし画像のみアカウントなので常に image になるはず）
- 対象3アカウント: `japanofcontext`, `kjckikyo`, `yureiyks`
- 各アカウントに `big` / `small` の2つのソース定義（buz と同じパターン）
- スケジュール: buz と同じ毎時 cron（`0 * * * *`）
- posting_window: 既存の JST 7:00–1:00 をそのまま利用

### 変更・作成・削除するファイル一覧

| 操作 | ファイル | 内容 |
|---|---|---|
| **作成** | `.github/workflows/post_pic.yml` | post_buz.yml をベースにした pic カテゴリ用ワークフロー |
| **変更** | `config/sources.yaml` | pic カテゴリのソース定義6件追加 (3アカウント × big/small) |
| **変更** | `config/accounts.yaml` | pic アカウント設定追加 |
| **作成** | `tests/test_sources_config_pic.py` | pic 専用のソース設定テスト (ファイル分割で高凝集) |

### 影響範囲

- **影響あり**: `config/sources.yaml`, `config/accounts.yaml`, `.github/workflows/`
- **影響なし**: `scripts/fetch_and_post.sh`, `scripts/lib/*`, 既存のテスト (buz / news のテストは変更しない)
- 既存の `test_sources_config.py` の `test_news_sources_unchanged` は news ソース数の検証なので影響なし
- `test_buz_enabled_count_is_20` も buz ソースのみを数えるので影響なし

### sources.yaml への追加内容

```yaml
# --- pic カテゴリ: 画像バズアカウント ---
- id: pic-japanofcontext-big
  rotation_key: japanofcontext
  category: pic
  type: search
  enabled: true
  query: "from:japanofcontext -is:retweet -is:reply filter:images min_faves:3000"
  timeline: Top
  max_results: 20
  score_boost: 10

- id: pic-japanofcontext-small
  rotation_key: japanofcontext
  category: pic
  type: search
  enabled: true
  query: "from:japanofcontext -is:retweet -is:reply filter:images min_faves:700"
  timeline: Latest
  max_results: 20
  score_boost: 6

- id: pic-kjckikyo-big
  rotation_key: kjckikyo
  category: pic
  type: search
  enabled: true
  query: "from:kjckikyo -is:retweet -is:reply filter:images min_faves:3000"
  timeline: Top
  max_results: 20
  score_boost: 10

- id: pic-kjckikyo-small
  rotation_key: kjckikyo
  category: pic
  type: search
  enabled: true
  query: "from:kjckikyo -is:retweet -is:reply filter:images min_faves:700"
  timeline: Latest
  max_results: 20
  score_boost: 6

- id: pic-yureiyks-big
  rotation_key: yureiyks
  category: pic
  type: search
  enabled: true
  query: "from:yureiyks -is:retweet -is:reply filter:images min_faves:3000"
  timeline: Top
  max_results: 20
  score_boost: 10

- id: pic-yureiyks-small
  rotation_key: yureiyks
  category: pic
  type: search
  enabled: true
  query: "from:yureiyks -is:retweet -is:reply filter:images min_faves:700"
  timeline: Latest
  max_results: 20
  score_boost: 6
```

**ポイント**:
- `filter:images` で画像付き投稿のみに限定
- `min_retweets:52` は buz に特有のしきい値だが、画像アカウントではRT数より faves 重視で `min_faves` のみ使用
- 画像アカウントは比較的バズのしきい値が異なる可能性があるため、big=`min_faves:3000`, small=`min_faves:700` を buz と同等に設定（要調整）

### accounts.yaml への追加内容

```yaml
pic:
  dry_run: true            # 初回は dry_run で確認
  post_prefix: ""
  max_candidates: 1
  summary_prefix: ""
  summary_provider: "copilot_cli"
  summary_model: "gpt-5-mini"
  summary_prompt_path: "config/copilot_summary_prompt_ja.txt"
  summary_max_length: 280
  single_post_max_length: 280
  selection_mode: "round_robin_account"
  fallback_candidates: 3
  rotation_state_file: "state/pic-robin.txt"
  source_reference_mode: "none"
  state_file: "state/pic-posted.txt"
  media_state_file: "state/pic-hot-selection.json"
  reply:
    enabled: false         # 初回はリプライ無効
  score_weights:
    likes: 1.0
    retweets: 3.5
    replies: 4.5
    views: 0.015
    velocity: 2.0
    freshness: 1.5
    image_bonus: 20        # 画像特化のため image_bonus を高めに
    author_virality: 30
  filters:
    max_age_hours: 72
    min_author_followers: 500    # 画像アカウントは小規模でも良質なものがある
    max_author_followers: 10000000
    exclude_keywords:
      - "フォロー"
      - "プレゼント企画"
      - "キャンペーン"
      - "giveaway"
      - "airdrop"
```

### post_pic.yml ワークフロー

`post_buz.yml` との主な差分:
- `name: Post pic`
- `CATEGORY: pic`
- concurrency group: `post-pic`
- cache key prefix: `post-pic-state-`
- artifact name: `pic-run`
- runtime 診断出力: `tmp/pic-runtime.json`
- auto-reply ステップは含めるが、`reply.enabled: false` なので実質スキップ

---

## 実装ステップ (チェックボックス)

### Part 1: post_buz 実運用確認

- [ ] **1-1** `gh workflow run post_buz.yml -f dry_run=true` で dry-run 実行
- [ ] **1-2** `gh run list` / `gh run view` で実行結果確認
- [ ] **1-3** Summary の各項目確認（posting_window, 候補取得, ラウンドロビン, 要約生成）
- [ ] **1-4** `gh run download <run_id>` で artifact 内容確認
- [ ] **1-5** posting_window 内であれば `gh workflow run post_buz.yml -f dry_run=false` で本番実行
  - `workflow_dispatch` の `dry_run` 入力が `accounts.yaml` の `buz.dry_run: false` を上書きすることを意識して実行
- [ ] **1-6** 投稿結果の確認（Posted tweet ID/URL, state cache 保存）

### Part 2: post_pic 追加 — RED フェーズ

- [ ] **2-1** `tests/test_sources_config_pic.py` を作成（失敗するテスト）
  - pic ソースが6件あること
  - rotation_key が3アカウントであること
  - 各アカウントに big/small があること
  - query に `filter:images` が含まれること
  - category が `pic` であること
- [ ] **2-2** テスト実行 → RED を確認

### Part 2: post_pic 追加 — GREEN フェーズ

- [ ] **2-3** `config/sources.yaml` に pic ソース6件追加
- [ ] **2-4** `config/accounts.yaml` に pic アカウント設定追加
- [ ] **2-5** `.github/workflows/post_pic.yml` を作成
- [ ] **2-6** テスト実行 → GREEN を確認

### Part 2: post_pic 追加 — REFACTOR フェーズ

- [ ] **2-7** 既存テスト全体が通ることを確認 (`python -m unittest discover -s tests`)
- [ ] **2-8** YAML バリデーション (`python -c "import yaml; yaml.safe_load(open('config/sources.yaml'))"` 等)
- [ ] **2-9** シェルスクリプト構文チェック (`bash -n` 相当)
- [ ] **2-10** `test_sources_config.py` の news / buz テストが壊れていないことを確認

### Part 2: post_pic 追加 — 実運用確認

- [ ] **2-11** `gh workflow run post_pic.yml -f dry_run=true` で dry-run 実行
- [ ] **2-11b** 候補が0件なら `filter:images` を `has:images` に差し替えて再実行し、再度結果確認
- [ ] **2-12** Summary と artifact で結果確認
  - `selected_media_mode=image` を確認
  - `has_image=true` と `image_urls` 非空を確認
  - candidate payload / post payload に画像情報が残っていることを確認
  - live 実行時に画像添付 fallback に落ちていないことを確認

---

## Out of scope

- post_pic の auto-reply 有効化（初回は `reply.enabled: false`）
- post_pic の `dry_run: false` への切り替え（ユーザー承認後に別タスクで実施）
- 画像ダウンロード＋添付ロジックの変更（既存の `post_media.py` / `post_publish.sh` がそのまま対応）
- posting_window の変更（pic も buz と同じ JST 7:00–1:00）
- score_weights の微調整（運用データを見てから別途調整）
- buz の既存ソース・アカウント設定の変更

---

## テスト方針 (RED → GREEN → REFACTOR)

### RED

1. `tests/test_sources_config_pic.py` を先に作成
2. pic ソースがまだ `sources.yaml` にないので `assertEqual(len(pic_sources), 6)` が `0 != 6` で失敗
3. 同様に accounts.yaml 内の pic 設定を検証するテストも失敗

### GREEN

1. `config/sources.yaml` に pic ソース6件追加 → ソーステスト通過
2. `config/accounts.yaml` に pic 設定追加 → アカウントテスト通過

### REFACTOR

1. 既存テスト全体が通ることを確認
2. ワークフロー YAML の構文確認
3. buz / news のテストが壊れていないことを再確認

### カバレッジ

- ソース設定のバリデーション: テストでカバー
- アカウント設定の存在確認: テストでカバー
- ワークフロー YAML: CI の YAML バリデーションでカバー
- 実際の投稿フロー: `fetch_and_post.sh` は既存テスト群 (`test_post_selection.py`, `test_post_media.py`, `test_post_filters.py`, `test_post_scoring.py` 等) でカバー済み

---

## 実行すべき既存の検証コマンド

```bash
# ユニットテスト全体
PYTHONPATH=scripts/lib python -m unittest discover -s tests

# YAML バリデーション
python -c "import yaml; yaml.safe_load(open('config/sources.yaml', encoding='utf-8'))"
python -c "import yaml; yaml.safe_load(open('config/accounts.yaml', encoding='utf-8'))"

# シェルスクリプト構文チェック
bash -n scripts/fetch_and_post.sh
bash -n scripts/fetch_search.sh
bash -n scripts/fetch_user.sh
bash -n scripts/lib/common.sh
bash -n scripts/lib/post_publish.sh

# ワークフロー YAML 構文
python -c "import yaml; [yaml.safe_load(open(f, encoding='utf-8')) for f in __import__('pathlib').Path('.github/workflows').glob('*.yml')]"

# workflow_dispatch 実行
gh workflow run post_buz.yml -f dry_run=true
gh workflow run post_pic.yml -f dry_run=true
```

---

## リスク / 確認事項

| リスク | 影響 | 対策 |
|---|---|---|
| `filter:images` が twitter-cli の search で正しく動作するか | 候補が0件になる可能性 | dry-run で確認。ダメなら `has:images` 等の代替構文を試す |
| 画像アカウントの `min_faves` しきい値が高すぎる/低すぎる | 候補が出ない or 質が低い | big=3000 / small=700 で開始し、artifact の skipped_candidates を見て調整 |
| posting_window 外での workflow_dispatch | `should_run=false` で全ステップスキップ | JST 7:00–1:00 内に実行するか、posting_window ステップを一時的にコメントアウト（非推奨） |
| `post_buz` の cron 実行 | `accounts.yaml` の `buz.dry_run=false` により実ツイートになる | 本確認は必ず `workflow_dispatch` で `dry_run` を明示し、live 実行はユーザー了承の上で実施 |
| 同時実行 (buz と pic) | concurrency group が別なので干渉しない | 問題なし |
| COPILOT_GITHUB_TOKEN が pic ワークフローで利用可能か | 要約生成に必要 | secrets はリポジトリ全体で共有なので問題なし |
| `test_sources_config.py` の `test_buz_enabled_count_is_20` | pic ソースを buz と誤認する可能性 | テストは `category == "buz"` でフィルタしているので影響なし（確認済み） |
| 3アカウントが実際に画像のみ投稿しているか | テキスト投稿が混ざると期待外れ | `filter:images` で対応。それでも混ざる場合は `media_mode: image` フィルタが post_selection で効く |

---

## 依存関係

```
Part 1 (post_buz 確認) ─── 独立して実行可能
Part 2 (post_pic 追加) ─── 独立して実行可能
  2-1, 2-2 (RED) → 2-3, 2-4, 2-5 (GREEN) → 2-7..2-10 (REFACTOR) → 2-11, 2-12 (確認)
```

Part 1 と Part 2 は並列に進行可能。ただし Part 1 で post_buz の問題が見つかった場合、post_pic に同じ問題が波及する可能性があるため、Part 1 を先に完了させることを推奨。
