# 実装計画: post_buz テキスト専用化・post_pic 3時間化・定期実行停止整理

**作成日時**: 2026-04-01 00:53 UTC  
**ステータス**: PLAN (レビュー待ち)

---

## 概要

今回の変更は、`buz` と `pic` の役割を分け直しつつ、未完成ワークフローの定期実行を止めるのが目的です。

1. `post_buz` は当面 **テキスト専用** にする  
2. 画像投稿は `post_pic` に寄せ、**3時間に1回** にする  
3. `buz` は最新寄りの候補だけでなく、**より古い候補（目安 100 件）** も拾えるよう取得範囲を広げる  
4. `post_tiktok` の **schedule を停止** する  
5. `post_video` は現状のトリガーを確認し、必要なら停止する  

---

## 変更・確認対象ファイル

| ファイル | 種別 | 予定内容 |
|---|---|---|
| `scripts/fetch_and_post.sh` | 変更 | `buz` の投稿時だけ画像 URL を渡さないようにし、テキスト専用化する |
| `config/sources.yaml` | 変更 | `buz` 系の古め候補も拾えるよう取得件数を広げる |
| `.github/workflows/post_pic.yml` | 変更 | cron を毎時から 3 時間ごとへ変更 |
| `.github/workflows/post_tiktok.yml` | 変更 | `schedule` を無効化し、手動実行だけ残す |
| `.github/workflows/post_video.yml` | 確認中心 | `schedule` の有無を最終確認し、必要時のみ変更する |
| `tests/test_sources_config.py` | 変更 | `buz` ソースの取得件数変更に合わせて期待値を更新する |
| `tests/test_post_publish.py` | 変更候補 | `buz` が画像なしで publish されることを検証できるなら既存テストを拡張する |

---

## 現状理解

### 1. post_buz の画像投稿

- `post_buz.yml` は 15 分ごとに `scripts/fetch_and_post.sh --category buz` を実行している
- `fetch_and_post.sh` は候補の `image_urls` を `publish_selected_post()` に渡す
- `post_publish.sh` は受け取った画像 URL があれば画像を添付して投稿する
- `buz` 側では `source_reference_mode: "none"` のため、**引用投稿は今は使っていない**

### 2. 引用ロジックの現状

- 引用経路自体は `scripts/lib/post_publish.sh` と `scripts/lib/post_quote.py` に存在する
- ただし `config/accounts.yaml` の `source_reference_mode` が `quote` のときだけ通る
- `buz` / `pic` はどちらも `source_reference_mode: "none"` なので、**現在の buz 投稿は通常ポスト**
- 今回ユーザーが言っている「100ツイート前でも拾ってよい」は、現状の構成では **引用方式の変更ではなく、候補取得範囲の拡張** として扱うのが妥当

### 3. 古い候補の取り方

- `config/sources.yaml` の `buz` ソースは主に `search` ベース
- 多くの `buz-*-small` / `buz-*-big` ソースが `max_results: 20`
- 現状のままだと、特に Latest 系は直近寄りに偏りやすい

### 4. ワークフローの定期実行

- `post_pic.yml` は現在毎時実行
- `post_tiktok.yml` は現在 3 時間ごと実行
- `post_video.yml` は事前確認上 `workflow_dispatch` のみで、定期実行は見当たらない

---

## 実装方針

### A. `post_buz` をテキスト専用にする

最小変更で、**投稿直前の 1 箇所で `buz` の画像添付を無効化** します。

- `scripts/fetch_and_post.sh` で `category == "buz"` の場合は `selected_image_urls_json="[]"` を強制
- 将来戻しやすいよう、意図が分かるコメントを添える

この方針なら、候補選定・スコアリング・共通 publish ロジック全体を崩さず、`buz` だけ振る舞いを変えられます。

### B. `post_pic` を 3 時間に 1 回へ変更する

- `.github/workflows/post_pic.yml` の cron を `0 * * * *` から `0 */3 * * *` に変更

これで画像投稿の主担当を `pic` に寄せます。

### C. `buz` の候補取得を古めまで広げる

ユーザー要求の「100 ツイート前くらいでもよい」を優先し、まずは **`buz` 系 source の取得件数を 100 近辺まで広げる案** を主案にします。

主案:

- `config/sources.yaml` の `buz-*-small` (Latest) を `max_results: 100` に拡張

必要に応じて検討する補助判断:

- `buz-*-big` (Top) はアルゴリズム依存なので、まずは据え置き
- もしテストや構成上 `100` が過大なら、実装時に既存テストと整合する上限へ微調整する

この変更は **引用ロジックの有効化ではなく、候補探索範囲の拡張** です。

### D. `post_tiktok` の定期実行を止める

- `.github/workflows/post_tiktok.yml` の `schedule` をコメントアウトまたは削除し、`workflow_dispatch` は維持

### E. `post_video` は実態確認ベースで扱う

- `.github/workflows/post_video.yml` に schedule がないことを再確認
- 本当に手動実行だけなら **コード変更なし**
- もし別経路で自動起動が見つかれば、その時点で対象追加

---

## 影響範囲

### `post_buz`

- 画像付き候補が選ばれても、最終投稿はテキストのみになる
- 候補探索・要約生成・ローテーションの既存ロジックは基本維持
- 引用投稿ロジックには手を入れない

### `post_pic`

- 定期実行頻度が毎時から 3 時間ごとに下がる
- 手動実行は維持される

### `post_tiktok`

- 定期実行停止のみ
- ワークフロー定義や Python 実装の削除は行わない

### `post_video`

- 現状確認のみの可能性が高い
- 手動実行の導線は維持する

---

## チェックボックス形式の実装ステップ

- [ ] `scripts/fetch_and_post.sh` を確認し、`buz` の画像 URL を投稿直前で無効化する位置を特定する
- [ ] `buz` の画像添付停止を実装し、意図が分かるコメントを入れる
- [ ] `.github/workflows/post_pic.yml` の cron を 3 時間ごとへ変更する
- [ ] `config/sources.yaml` の `buz` 系 Latest ソースの `max_results` を、古い候補を拾える値まで拡張する（主案: 100）
- [ ] `tests/test_sources_config.py` の期待値を更新する
- [ ] 可能なら `tests/test_post_publish.py` か既存関連テストに `buz` 無画像投稿の検証を追加する
- [ ] `.github/workflows/post_tiktok.yml` の `schedule` を停止する
- [ ] `.github/workflows/post_video.yml` に定期実行がないことを再確認する
- [ ] 既存の unittest と YAML 検証を実行する
- [ ] 問題なければ exec-plan を `docs/exec-plans/completed/` に移動して次フェーズへ進む

---

## テスト戦略 (RED → GREEN → REFACTOR)

### 1. buz 候補件数拡張

RED:

- `tests/test_sources_config.py` の期待値を先に更新し、失敗を確認する

GREEN:

- `config/sources.yaml` の `buz` 系 `max_results` を更新してテストを通す

REFACTOR:

- 設定値変更のみなら追加整理は最小限

### 2. buz の画像停止

RED:

- 既存の `tests/test_post_publish.py` で拡張可能なら、`buz` が画像なし publish になるケースを先に追加する
- 既存テストで表現しづらい場合は、`fetch_and_post.sh` の変更点が分かる最小テスト追加を検討する

GREEN:

- `buz` だけ画像 URL を空配列にする実装を入れてテストを通す

REFACTOR:

- 画像停止ロジックが `buz` 専用の一時措置だと分かるようコメントだけ整理する

### 3. workflow 変更

- `post_pic.yml` の cron 変更
- `post_tiktok.yml` の schedule 停止
- `post_video.yml` の schedule 不在確認

これらは主に YAML 妥当性確認と差分確認で検証する。

---

## 検証コマンド

```bash
python -m unittest tests.test_sources_config
python -m unittest tests.test_post_publish
python -m unittest discover -s tests
python - <<'PY'
from pathlib import Path
import yaml
for path in [
    'config/sources.yaml',
    '.github/workflows/post_pic.yml',
    '.github/workflows/post_tiktok.yml',
    '.github/workflows/post_video.yml',
]:
    yaml.safe_load(Path(path).read_text(encoding='utf-8'))
print('yaml ok')
PY
```

---

## リスク・注意点

- `search` 系 source の `max_results: 100` が API 応答時間やレートに影響する可能性がある
- `buz` で画像候補自体は選ばれても、投稿時には画像が落ちるため、候補選定の見え方と最終投稿がずれる可能性がある
- `post_video` はすでに定期実行なしの可能性が高く、ユーザー要望に対しては「現状停止済み」と説明する形になる
- 「引用ロジック」と「候補取得範囲」は別概念なので、実装時の説明を混ぜない

---

## 明示的な out-of-scope

- `source_reference_mode: "quote"` を `buz` / `pic` で有効化すること
- 引用投稿ロジック自体 (`post_quote.py`, quote API 経路) の仕様変更
- `tiktok` / `video` 関連 Python 実装の削除や大改修
- 候補選定アルゴリズム全体の再設計
- `post_buz` の 15 分実行頻度そのものの変更

---

## 実装前提

この計画では、要求2の「100ツイート前でもよい」は **引用方式の変更ではなく、候補取得件数の拡張** として解釈しています。  
実装開始前に、`buz` の取得件数を **100 前後まで広げる方針** でよいかをユーザー確認する。
