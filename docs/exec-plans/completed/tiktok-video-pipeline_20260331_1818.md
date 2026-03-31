# TikTok由来動画 → X投稿パイプライン 実装計画

## 概要

TikTok上の**自社保有アカウント動画**のみを対象に、候補選定・ダウンロード・MP4検証を経て、既存の `scripts/lib/post_video.py` 経由でXに投稿する新カテゴリ `tiktok` を追加する。

## deep research 結論

- このリポジトリにはすでに X への動画投稿基盤がある
  - `python/post_video.py`
  - `scripts/lib/post_video.py`
  - `.github/workflows/post_video.yml`
- したがって新規実装の中心は **X 投稿そのものではなく**、TikTok 側の取得・許諾・候補選定・既存 `post_video_tweet()` への橋渡しである。
- GitHub 上で確認できた近い事例は以下だった。
  - `FujiwaraChoki/MoneyPrinterV2`
    - Twitter Bot / YouTube Shorts を掲げるが、README と docs からは **Firefox profile / browser automation 前提**が強い
    - ライセンスは **AGPL-3.0**
    - このリポジトリにそのまま持ち込むには、ライセンス・運用・安定性の面で不適
  - `Folis455/TikTok-to-Shorts-Reels-Reuploader`
    - `tiktok_downloader.py` / `youtube_uploader.py` / `instagram_uploader.py` の分離は参考になる
    - 一方で README の主張に比べて実装品質・運用保証は弱く、X 連携は roadmap 止まり
    - **ダウンロード → metadata → uploader の責務分離**のみ採用候補
  - `sibersentinel/-nstagram-youtube-tiktok-twitter-x-video-downloader-and-uploader-bot`
    - README と単一ファイル中心で、保守性・信頼性の面から参考度は低い
- 結論として、**外部実装を模倣するよりも**、
  - 既存の `post_video` 基盤を再利用しつつ
  - TikTok 取り込み部分だけを小さく独立追加し
  - 外部事例からは「パイプライン分割」の考え方のみ借りる
  方針が最も安全。

## 方針制約の理由

- ユーザー要望の「ランダム探索して再投稿」は、第三者動画の無許諾転載や規約違反に直結しやすい。
- v1 を **owner 限定**にすることで、著作権・音源権利・再利用許諾・クレジット要否の不確実性を大きく減らせる。
- 将来 `explicit` を扱う場合も、少なくとも allowlist + 許諾根拠 + platform user id 一致が必要であり、v1 では扱わない。

**著作権ポリシー**:
- v1 の live 対象は `consent_type: owner` のみ。**第三者クリエイターの動画は、明示許諾があっても v1 では live 対象にしない**。
- 将来 `consent_type: explicit` を扱う場合でも、**allowlist 登録に加えて、そのクリエイター本人の TikTok OAuth 認可と `platform_user_id` 一致確認が必須**。
- allowlist にないアカウント、`enabled: false`、`expires_at` 超過、`consent_reference` 欠落、`platform_user_id` 不一致のいずれかに該当する動画は処理対象外。
- 手動 URL 指定や arbitrary URL ダウンロードによる迂回は許可しない。

---

## 1) 変更・作成ファイル

### 新規作成

| ファイル | 責務 | 想定行数 |
|---|---|---|
| `scripts/lib/tiktok_client.py` | TikTok Open API `/v2/video/list/` ラッパー。OAuth refresh/access token 管理、動画一覧取得、レスポンス正規化 | ~220行 |
| `scripts/lib/tiktok_allowlist.py` | allowlist YAML の読み込み・スキーマ検証・有効期限/所有権判定 | ~150行 |
| `scripts/lib/tiktok_scoring.py` | TikTok動画のスコア計算。既存 `post_scoring.py` と同じ分解パターンを維持 | ~150行 |
| `scripts/lib/tiktok_filters.py` | TikTok動画のフィルタリング。既存 `post_filters.py` と同名関数パターンを維持 | ~140行 |
| `scripts/lib/tiktok_downloader.py` | TikTok動画ダウンロード + MP4検証。TikTok ドメイン制限、yt-dlp 呼び出し、後片付け | ~170行 |
| `scripts/lib/tiktok_state.py` | 投稿済み TikTok video_id の行ベース state 管理。既存 `*-posted.txt` / `append_unique_tweet_id` パターンに合わせる | ~100行 |
| `scripts/lib/tiktok_pipeline.py` | API取得→allowlist→フィルタ→スコア→選定→ダウンロード→`post_video_tweet()` 呼び出しのオーケストレーション | ~260行 |
| `config/tiktok_allowlist.yaml` | 自社保有 TikTok アカウント allowlist と取得パラメータ定義 | ~40行 |
| `.github/workflows/post_tiktok.yml` | GitHub Actions ワークフロー。schedule + workflow_dispatch + posting_window + state cache | ~200行 |
| `tests/test_tiktok_client.py` | `tiktok_client.py` のユニットテスト | ~220行 |
| `tests/test_tiktok_allowlist.py` | `tiktok_allowlist.py` のユニットテスト | ~180行 |
| `tests/test_tiktok_scoring.py` | `tiktok_scoring.py` のユニットテスト | ~150行 |
| `tests/test_tiktok_filters.py` | `tiktok_filters.py` のユニットテスト | ~170行 |
| `tests/test_tiktok_downloader.py` | `tiktok_downloader.py` のユニットテスト | ~180行 |
| `tests/test_tiktok_state.py` | `tiktok_state.py` のユニットテスト | ~120行 |
| `tests/test_tiktok_pipeline.py` | `tiktok_pipeline.py` の統合テスト | ~280行 |

### 既存変更

| ファイル | 変更内容 |
|---|---|
| `config/accounts.yaml` | `tiktok` アカウント設定を追加（dry_run, score_weights, filters, state_file, allowlist_path など） |
| `README.md` | ローカル実行・必要 secrets・TikTok パイプラインの制約を最小限追記（実装と同時に必要な範囲のみ） |

### 変更しないファイル

| ファイル | 理由 |
|---|---|
| `config/sources.yaml` | 既存バリデータと `scripts/fetch_user.sh` / `scripts/fetch_search.sh` は `user/search` のみ対応。独立パイプラインに不要なため触らない |
| `scripts/fetch_and_post.sh` | X検索/ユーザー取得用フロー。TikTokパイプラインは独立実装の方が影響範囲が小さい |
| `scripts/lib/common.sh` | `sources.yaml` を拡張しない前提なら TikTok 実装のための変更は不要 |
| `scripts/lib/post_video.py` | 既存の動画投稿ロジックをそのまま再利用 |
| `python/post_video.py` | CLI インターフェース変更は不要 |

---

## 2) 影響範囲

### 既存機能への影響
- **限定的**: 既存カテゴリ（buz/pic/news/invest）の収集・投稿フローには影響しない
- 既存の `post_video_tweet()` / `validate_video_path()` を再利用するため、動画投稿経路の一貫性は維持される
- `config/accounts.yaml` と `README.md` には新カテゴリ/運用制約ぶんの追記が入る

### TikTok API 前提
- v1 は **TikTok Open API の `/v2/video/list/`** を前提にする
- `Research API` は**研究用途前提であり、運用用の再投稿パイプラインの基盤にしない**
- `Content Posting API` / `Business API` は **TikTok へ投稿するための API 群であり、X への再投稿候補取得の主経路にはしない**
- `authenticate()` は client credentials ではなく、**refresh token → user access token 更新**を前提にする

### ワークフロー連携
- 新規ワークフロー `post_tiktok.yml` を追加
- `concurrency.group: post-tiktok` で既存 workflow と独立
- 既存の secrets（`TWITTER_AUTH_TOKEN`, `TWITTER_CT0`）を共用
- 新規 secrets:
  - `TIKTOK_CLIENT_KEY`
  - `TIKTOK_CLIENT_SECRET`
  - `TIKTOK_REFRESH_TOKEN`
- run summary / artifact には**JSON 結果とログのみ**を残し、ダウンロードした動画本体はアップロードしない

### 依存パッケージ
- `yt-dlp`: TikTok動画ダウンロード
- `ffmpeg` / `ffprobe`: MP4 検証・必要時のコンテナ整備
- **HTTP クライアントは標準 `urllib` を採用**
  - 理由: このリポジトリは `scripts/lib/post_media.py` や `python/update_tickers_jp.py` で既に `urllib` を採用しており、依存追加を避けられるため
  - `httpx` は v1 では採用しない

---

## 3) 非対象（スコープ外）

- `consent_type: explicit` クリエイターの live 投稿対応
- クリエイターごとの OAuth オンボーディング UI / 永続 credential ストア
- TikTok Research API を使った大規模検索・横断探索
- TikTok コメント返信、フォロー、いいね等の自動化
- 動画編集・加工（字幕、透かし、切り抜き等）
- `config/sources.yaml` の新 source type 追加
- `scripts/fetch_and_post.sh` / `scripts/fetch_user.sh` / `scripts/fetch_search.sh` の拡張
- 複数 TikTok アカウントの同時 live 運用
- 動画本体の長期保存や GitHub Artifact への保存

---

## 4) RED → GREEN → REFACTOR テスト戦略

### Phase 1: allowlist / state / client のユニットテスト

**RED**: 失敗テストを先に追加

- `tests/test_tiktok_allowlist.py`
  - `owner` 以外は live 対象にならない
  - `platform_user_id` 欠落や `consent_reference` 欠落を reject する
  - `enabled: false` / `expires_at` 超過を reject する
- `tests/test_tiktok_state.py`
  - 行ベース state の重複排除
  - dry_run 時に state を更新しない
- `tests/test_tiktok_client.py`
  - refresh token リクエスト生成
  - `/v2/video/list/` レスポンス正規化
  - 401 / 429 / malformed payload のエラー処理

**GREEN**: 最小実装で通す

**REFACTOR**: リクエスト生成、レスポンス正規化、エラー型を整理

### Phase 2: filters / scoring / downloader のユニットテスト

**RED**:

- `tests/test_tiktok_filters.py`
  - 年齢フィルタ
  - exclude_keywords
  - 最低エンゲージメント
  - allowlist 未許可 creator の reject
- `tests/test_tiktok_scoring.py`
  - `like/share/comment/view` の重み付け
  - freshness bonus
  - score breakdown の安定性
- `tests/test_tiktok_downloader.py`
  - TikTok ドメイン以外を reject
  - yt-dlp 呼び出し引数検証
  - MP4 以外 / サイズ超過 / 壊れた動画の reject
  - 失敗時 cleanup

**GREEN**: 最小実装で通す

**REFACTOR**: `post_filters.py` / `post_scoring.py` と同じ関数粒度・戻り値に寄せる

### Phase 3: pipeline 統合テスト

**RED**: `tests/test_tiktok_pipeline.py`

- `test_pipeline_selects_best_owner_video`
- `test_pipeline_rejects_non_owner_allowlist_entries_for_live_run`
- `test_pipeline_skips_expired_or_disabled_allowlist_entries`
- `test_pipeline_skips_already_posted_video_ids`
- `test_pipeline_dry_run_validates_but_does_not_post_or_mark_state`
- `test_pipeline_handles_download_failure_gracefully`
- `test_pipeline_passes_validated_mp4_to_post_video`

**GREEN**: `tiktok_pipeline.py` 実装

**REFACTOR**: エラーハンドリングとログを共通化

### Phase 4: workflow / dry-run 検証

- `workflow_dispatch` で `dry_run=true`
- posting_window 内でのみ実行されることを確認
- state cache が restore/save されることを確認
- artifact に MP4 が含まれないことを確認

### カバレッジ目標

- 追加する TikTok 関連モジュール群: **80%以上**
- 重要モジュール（allowlist / client / pipeline）: **90%前後を目標**
- 全体 fail-under: **80%**

---

## 5) 検証コマンド

### ローカル実行

```bash
# dry_run で TikTok パイプライン実行
TIKTOK_CLIENT_KEY=test \
TIKTOK_CLIENT_SECRET=test \
TIKTOK_REFRESH_TOKEN=test \
python -m scripts.lib.tiktok_pipeline --category tiktok --dry-run true

# allowlist 設定の検証
python - <<'PY'
from pathlib import Path
import yaml

data = yaml.safe_load(Path('config/tiktok_allowlist.yaml').read_text(encoding='utf-8')) or {}
print(len(data.get('creators') or []))
PY
```

### テスト実行

```bash
# 追加ユニット/統合テスト
python -m unittest tests.test_tiktok_allowlist -v
python -m unittest tests.test_tiktok_client -v
python -m unittest tests.test_tiktok_filters -v
python -m unittest tests.test_tiktok_scoring -v
python -m unittest tests.test_tiktok_downloader -v
python -m unittest tests.test_tiktok_state -v
python -m unittest tests.test_tiktok_pipeline -v

# 既存テストを含む全体確認（既存 CI パターン）
python -m unittest discover -s tests

# カバレッジ確認
python -m coverage run -m unittest discover -s tests
python -m coverage report --fail-under=80
```

### 補助確認

```bash
python -m py_compile scripts/lib/tiktok_client.py scripts/lib/tiktok_allowlist.py scripts/lib/tiktok_filters.py scripts/lib/tiktok_scoring.py scripts/lib/tiktok_downloader.py scripts/lib/tiktok_state.py scripts/lib/tiktok_pipeline.py
python - <<'PY'
from pathlib import Path
import yaml
for path in ['config/accounts.yaml', 'config/tiktok_allowlist.yaml', '.github/workflows/post_tiktok.yml']:
    yaml.safe_load(Path(path).read_text(encoding='utf-8'))
print('yaml ok')
PY
```

---

## 6) 実装ステップ（チェックボックス形式）

### Phase A: スキーマと state（並列実装可能）

- [ ] **A-1**: `config/tiktok_allowlist.yaml` を作成
  - `platform_user_id`, `tiktok_username`, `enabled`, `consent_type`, `consent_reference`, `consent_checked_at`, `expires_at`, `max_results`, `score_boost` を持たせる
  - v1 の live 例は `consent_type: owner` のみを記載

- [ ] **A-2**: `scripts/lib/tiktok_allowlist.py` + `tests/test_tiktok_allowlist.py`
  - RED: スキーマ不備、owner 制約、期限切れ拒否のテストを書く
  - GREEN: `load_allowlist(path)`, `get_allowed_creator(username, platform_user_id, allowlist, *, live_run)` を実装
  - REFACTOR: バリデーションとエラーメッセージ整理

- [ ] **A-3**: `scripts/lib/tiktok_state.py` + `tests/test_tiktok_state.py`
  - RED: 投稿済み読み込み、追加、重複排除、dry_run 非更新のテストを書く
  - GREEN: `load_posted_ids(path)`, `is_posted(video_id, posted_ids)`, `mark_posted(video_id, path)` を実装
  - REFACTOR: 既存 line-based state パターンとの一貫性確認

### Phase B: TikTok API クライアント

- [ ] **B-1**: `scripts/lib/tiktok_client.py` + `tests/test_tiktok_client.py`
  - RED: refresh token 交換、`/v2/video/list/` パース、429/401 処理のテストを書く
  - GREEN: `TikTokClient` を実装
    - `refresh_access_token()`
    - `fetch_user_videos(max_count, cursor=None)`
    - レスポンスを pipeline 用の共通 dict に正規化
  - REFACTOR: `urllib` 呼び出しとエラーラップを整理

### Phase C: 選定ロジック（B / A-2 に依存）

- [ ] **C-1**: `scripts/lib/tiktok_filters.py` + `tests/test_tiktok_filters.py`
  - RED: allowlist 判定、年齢、除外キーワード、最低エンゲージメントのテストを書く
  - GREEN: 既存名に合わせて `candidate_rejection_reasons(...)` を実装
  - REFACTOR: `post_filters.py` と同じ入力/戻り値パターンへ寄せる

- [ ] **C-2**: `scripts/lib/tiktok_scoring.py` + `tests/test_tiktok_scoring.py`
  - RED: スコア計算、breakdown、freshness のテストを書く
  - GREEN: 既存名に合わせて `calculate_score(...)` を実装
  - REFACTOR: `post_scoring.py` と同じ breakdown キー体系に寄せる

### Phase D: ダウンロード

- [ ] **D-1**: `scripts/lib/tiktok_downloader.py` + `tests/test_tiktok_downloader.py`
  - RED: 非 TikTok URL 拒否、yt-dlp 引数、MP4 検証、cleanup のテストを書く
  - GREEN: `download_tiktok_video(video_page_url, output_dir, max_size_bytes)` を実装
    - 許可ホスト: `www.tiktok.com`, `m.tiktok.com`, `vm.tiktok.com` のみ
    - yt-dlp をサブプロセスで実行
    - ダウンロード後に既存 `validate_video_path()` で検証
  - REFACTOR: 例外型と後片付けを整理

### Phase E: 設定ファイル拡張

- [ ] **E-1**: `config/accounts.yaml` に `tiktok` 設定を追加
  - `dry_run: true` を初期値にする
  - `state_file: "state/tiktok-posted.txt"`
  - `allowlist_path: "config/tiktok_allowlist.yaml"`
  - `selection_mode: "score"`
  - `score_weights` / `filters` を TikTok 用に追加

### Phase F: パイプライン統合（A〜E に依存）

- [ ] **F-1**: `scripts/lib/tiktok_pipeline.py` + `tests/test_tiktok_pipeline.py`
  - RED: 正常/拒否/dry_run/失敗系統合テストを書く
  - GREEN: `run_tiktok_pipeline(category, config, dry_run)` を実装
    - `accounts.yaml` から category 設定を読み込む
    - `tiktok_allowlist.yaml` から creator 設定を読み込む
    - API で owner 動画取得 → allowlist / filters → score → 上位選定
    - ダウンロード → `post_video_tweet()` に委譲
    - live 実行時のみ state 更新
  - REFACTOR: ログ、例外、結果 payload を整理

### Phase G: GitHub Actions ワークフロー（F に依存）

- [ ] **G-1**: `.github/workflows/post_tiktok.yml` を作成
  - `workflow_dispatch`（dry_run 入力）+ `schedule`
  - 既存 `post_buz.yml` / `post_pic.yml` と同じ `posting_window` 評価を入れる
  - Python venv + yt-dlp + twikit + ffmpeg をインストール
  - `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` を secrets から取得
  - `tmp/state` のみ cache restore/save
  - summary / artifacts には JSON とログのみを保存し、動画本体は保存しない

### Phase H: 最終検証

- [ ] **H-1**: 対象テストと全体テストを実行
- [ ] **H-2**: `coverage report --fail-under=80` を確認
- [ ] **H-3**: workflow_dispatch の dry_run 実行結果と artifact 内容を確認

---

## 設定ファイル設計（参考）

### config/tiktok_allowlist.yaml

```yaml
creators:
  - platform_user_id: "1234567890123456789"
    tiktok_username: "example_owner"
    enabled: false
    consent_type: "owner"
    consent_reference: "self-owned account"
    consent_checked_at: "2026-03-31"
    expires_at: null
    max_results: 10
    score_boost: 0
```

### config/accounts.yaml（追加分）

```yaml
  tiktok:
    dry_run: true
    post_prefix: ""
    max_candidates: 1
    summary_prefix: ""
    summary_provider: "copilot_cli"
    summary_model: "gpt-5-mini"
    summary_prompt_path: "config/copilot_summary_prompt_ja.txt"
    summary_max_length: 280
    single_post_max_length: 280
    selection_mode: "score"
    state_file: "state/tiktok-posted.txt"
    allowlist_path: "config/tiktok_allowlist.yaml"
    score_weights:
      likes: 1.0
      retweets: 5.0  # TikTok の share_count 相当
      replies: 3.0   # TikTok の comment_count 相当
      views: 0.01
      velocity: 0.0
      freshness: 2.0
      image_bonus: 0.0
      author_virality: 0.0
    filters:
      max_age_hours: 168
      exclude_keywords:
        - "広告"
        - "PR"
        - "プロモーション"
        - "sponsored"
      min_engagement: 1000
```

> 実装時は `post_scoring.py` との整合性を優先し、TikTok の `share_count` / `comment_count` を内部で `retweets` / `replies` 相当として正規化する。

---

## 依存関係グラフ

```text
A-1 (allowlist yaml) ───┐
A-2 (allowlist module) ─┼────┐
A-3 (state module) ─────┘    │
                              │
B-1 (tiktok client) ──────────┤
                              │
C-1 (filters) ← A-2, B-1 ────┤
C-2 (scoring) ← B-1 ─────────┤
                              │
D-1 (downloader) ─────────────┤
                              │
E-1 (accounts.yaml) ──────────┤
                              │
F-1 (pipeline) ← A,B,C,D,E ──┤
                              │
G-1 (workflow) ← F-1 ─────────┤
                              │
H-1/H-2 ← F-1 ────────────────┤
H-3 ← G-1 ────────────────────┘
```

**並列実装可能**:
- A-1 / A-2 / A-3 は並列可能
- B-1 は A 系と並列可能
- C-1 / C-2 は相互並列可能
- D-1 は A〜C と並列可能
- E-1 以降は順次実装

---

## リスクと注意点

- TikTok Open API は **user access token 前提**なので、client credentials 前提で設計すると実装不能になる
- allowlist が username のみだと rename / impersonation に弱いため、`platform_user_id` を必須にする
- 動画を artifact や cache に保存すると権利・漏えいリスクが上がるため、**state と JSON のみ**永続化する
- `config/sources.yaml` を流用すると既存 validator (`user/search` 限定) と衝突するため、v1 は独立設定に留める

---

## レビューコメント（修正理由）

- **著作権/権利ポリシーを厳格化**: 元計画は `explicit` 許諾クリエイターまで v1 live 対象に見えたが、API 認可と権利運用の両面で抜け道があったため、v1 live を `owner` のみに限定した。`platform_user_id`・`consent_reference`・`expires_at` を必須化し、username だけで通らないように修正した。
- **TikTok API 前提を修正**: 元計画の `Research API / Business API` と `client_credentials` 前提は、運用用の動画取得パイプラインとして不適切または不足がある。v1 は TikTok Open API `/v2/video/list/` + refresh token ベースに限定した。
- **既存コードとの整合性を改善**: `config/sources.yaml` に `tiktok_user` を追加すると、既存 `common.sh` の source type 検証 (`user/search` のみ) と衝突するため、独立設定に切り替えた。これにより既存 `fetch_*` 系へ不要な変更が波及しない。
- **HTTP クライアント選定を明確化**: repo 既存実装は `urllib` ベースなので、v1 で `httpx` を増やす必然性が薄い。依存削減と一貫性のため `urllib` 採用に修正した。
- **テスト/検証コマンドを既存運用に合わせた**: 元計画は `pytest` / `pytest-cov` 前提だったが、既存 CI と README は `unittest discover` が基準。RED→GREEN→REFACTOR を維持しつつ、最終検証を `unittest` / `coverage` に揃えた。
- **GitHub Actions の権利・セキュリティ設計を補強**: 動画本体を artifact に残す案は権利面で危険なので削除した。cache 対象も `tmp/state` のみに限定し、secrets も refresh token 前提へ修正した。
- **依存関係を簡素化**: `sources.yaml` 拡張や `fetch_and_post.sh` への統合を外し、独立パイプラインとして成立する最小構成へ整理した。不要な複雑化を避けつつ、既存 `post_video.py` / state パターンは再利用する方針にした。
- **依存関係グラフを修正**: 元計画の順序では pipeline が `accounts.yaml` 追加より先に見えていたため、設定→pipeline→workflow の依存順に直した。これで並列可能範囲と後続検証の前提が明確になった。
