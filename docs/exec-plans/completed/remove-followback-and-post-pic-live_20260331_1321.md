# Remove followback-priority & test-run post_pic live

**Plan ID:** `remove-followback-and-post-pic-live_20260331_1321`
**Created:** 2026-03-31 13:21 JST

---

## Overview

本計画は2つのタスクで構成される。

1. **followback-priority の除去** — `auto_follow.py` のフォローバック優先ロジック（Phase 1-2）を完全に削除し、新規フォローのみ（Phase 3-4相当）で動作するようにする。関連テスト・ワークフローのサマリも同時に更新する。
2. **post_pic ワークフローのライブ実行テスト** — `workflow_dispatch` で `dry_run=false` を指定し、pic アカウントで実際にツイートを投稿する。投稿結果をアーティファクト・サマリで検証する。

---

## Overlapping plans check

`docs/exec-plans/active/` は現在 **空（本計画のみ）** — 競合する計画なし。

---

## Files to modify / create / delete

| Action | File | Rationale |
|--------|------|-----------|
| **Modify** | `python/auto_follow.py` | followback 関連の関数削除、`main()` の Phase 1-2 除去、サマリフィールド整理 |
| **Modify** | `tests/test_auto_follow.py` | `FollowbackTests` クラス全体削除、followback インポート削除、followback 除去後の動作テスト追加 |
| **Modify** | `.github/workflows/auto_follow.yml` | サマリステップから followback 関連フィールド除去 |
| **Modify** | `README.md` | auto_follow の説明から followback 優先仕様を削除し、現行挙動へ同期 |
| **変更なし** | `python/auto_unfollow.py` | followback 固有関数をインポートしていないため変更不要 |
| **変更なし** | `config/accounts.yaml` | pic の `dry_run: true` はそのまま（dispatch override で制御） |

---

## Task 1: Remove followback-priority from auto-follow

このタスクの変更対象は **コード本体 + GitHub Actions summary + README** を含む。挙動と表示と運用ドキュメントを一致させる。

### 1.1 削除対象の関数（`python/auto_follow.py`）

| 関数名 | 行範囲 | 用途 |
|--------|--------|------|
| `evaluate_followback_candidate()` | L260-276 | followback 候補の最小フィルタ評価 |
| `collect_followback_usernames()` | L279-289 | followback プール生成 |
| `build_active_followed_username_set()` | L130-141 | アクティブフォロー済みセットの構築（followback 除外用） |

#### `build_active_followed_username_set()` の影響分析

- `main()` 内 L350 でのみ使用 → followback 除去とともに呼び出しも削除可能
- `auto_unfollow.py` はこの関数を **インポートしていない**（独自ロジックで判定）
- テストの `FollowbackTests` でのみテストされている → クラスごと削除

### 1.2 `main()` の変更内容

#### 削除する行と変数

| 項目 | 行範囲 | 内容 |
|------|--------|------|
| `active_followed_usernames` | L350 | `build_active_followed_username_set()` 呼び出し |
| `my_follower_usernames` | L355-357 | 自アカウントのフォロワー取得（followback 専用） |
| Phase 1 コメント + followback_pool 構築 | L378-385 | `collect_followback_usernames()` 呼び出し |
| `attempted_followback_usernames` | L394 | followback 候補の追跡セット |
| `followed_back` リスト | L392 | followback 成功記録 |
| Phase 2 ループ | L391-422 | followback 実行ループ全体 |
| `_total_followed()` 内の `followed_back` 参照 | L397 | → `len(followed_new)` のみに |
| Phase 3 の `attempted_followback_usernames` ガード | L435-436 | 不要になるので削除 |
| サマリの followback フィールド | L517-519 | `followback_candidates`, `followed_back_count`, `followed_back_usernames` |
| `followed` 結合行 | L503 | `followed_back + followed_new` → `followed_new` のみ |

#### 変更後の `main()` フロー（簡略化）

```
1. state / following / target followers を取得（my_follower_usernames は不要）
2. target account の follower から候補を評価（現 Phase 3 相当）
3. 候補をフォロー実行（現 Phase 4 相当）
4. サマリ出力
```

#### 変更後のサマリ JSON フィールド

```json
{
  "status": "ok",
  "run_at_jst": "...",
  "auth_username": "...",
  "target_username": "...",
  "requested_follow_count": 10,
  "follower_candidates": 500,
  "scanned_followers": 200,
  "scan_limit": 1000,
  "recent_post_lookups": 15,
  "new_follow_candidates": 12,
  "followed_new_count": 10,
  "followed_new_usernames": ["..."],
  "followed_count": 10,
  "followed_usernames": ["..."],
  "skipped": [],
  "state_path": "config/follow_state.json"
}
```

削除フィールド: `followback_candidates`, `followed_back_count`, `followed_back_usernames`

### 1.3 `record_follow` の `follow_type` パラメータ

- `follow_type` パラメータ自体は汎用的であり `record_follow()` のシグネチャに残す
- `"followback"` 値での呼び出しはなくなるが、将来の拡張性のためパラメータは保持
- `main()` 内では `follow_type="new_follow"` のみ使用

### 1.4 テスト変更（`tests/test_auto_follow.py`）

#### 削除

- `FollowbackTests` クラス全体（L121-280） — 全13テストメソッド
- インポートから: `collect_followback_usernames`, `evaluate_followback_candidate`, `build_active_followed_username_set`

#### 保持（別クラスへ移動）

- `test_record_follow_defaults_to_new_follow_type`（L220-223）— `record_follow()` のデフォルト `follow_type` テスト。followback 除去後も `record_follow` は残るため、`AutoFollowTests` クラスに移動する。

#### 追加（RED フェーズで先に書く）

- `test_main_does_not_fetch_my_followers` — `fetch_usernames` のモックで `"followers"` + auth_username の呼び出しがないことをアサート
- `test_main_summary_has_no_followback_fields` — サマリ出力に `followback_candidates`, `followed_back_count`, `followed_back_usernames` が含まれないことをアサート
- `test_main_only_new_follows_flow` — 全フォローが `new_follow` タイプで記録され、かつ最低1件はフォロー成功していること、`followed_new_count` / `followed_usernames` が正しいことを検証（既存の `test_main_fills_with_new_follow_when_followback_fails` を followback 除去後の happy path に作り替え）

#### 注意: `tests/test_auto_unfollow.py`

- L14 のテスト名 `test_build_unfollow_candidates_filters_by_age_followback_and_status` に "followback" が含まれるが、これはフォローバックという概念ではなく unfollow 候補のフィルタリングテスト名の一部であり、変更不要。grep チェック時はこのファイルを除外する。

### 1.5 ワークフロー変更（`.github/workflows/auto_follow.yml`）

サマリステップ（L86-113）の auto follow セクションから以下の行を削除:

```python
f"- Followback candidates: `{payload.get('followback_candidates', 0)}`",
f"- Followed back: `{payload.get('followed_back_count', 0)}`",
f"- Followed back usernames: `{', '.join(payload.get('followed_back_usernames') or [])}`",
```

### 1.6 影響面分析

| コンポーネント | 影響 | 対応 |
|---------------|------|------|
| `auto_unfollow.py` | followback 固有関数未使用。`fetch_usernames`, `extract_username` 等は残存 | なし |
| `follow_state.json` | 既存の `follow_type: "followback"` エントリは残る。新規は `"new_follow"` のみ | 後方互換OK |
| GitHub Actions キャッシュ | state ファイルのスキーマ変更なし | なし |
| API 呼び出し回数 | `my_follower_usernames` 取得が1回減る → レート制限改善 | ポジティブ |

---

## Task 2: Test-run post_pic workflow as real tweet

### 2.1 事前確認（Pre-flight checks）

- [ ] posting window 内の時間か確認（JST で投稿ウィンドウに入っている必要あり）
- [ ] `TWITTER_AUTH_TOKEN` / `TWITTER_CT0` / `COPILOT_GITHUB_TOKEN` のシークレットが設定済み
- [ ] `config/accounts.yaml` の `pic` アカウント設定を確認（`dry_run: true` のまま — dispatch override で上書き）

### 2.2 トリガーコマンド

```bash
gh workflow run post_pic.yml -f dry_run=false
```

### 2.3 モニタリングコマンド

```bash
# ワークフラン一覧で最新の run を確認
gh run list --workflow=post_pic.yml --limit 5

# 特定の run ID でステータス監視
gh run watch <RUN_ID>

# run の詳細表示
gh run view <RUN_ID>
```

### 2.4 検証チェックリスト

- [ ] ワークフロー run が `completed` / `success` で終了
- [ ] posting window ステップが `should_run=true` を出力
- [ ] `account_mode` ステップが `dry_run=false` を出力
- [ ] アーティファクト `pic-run` がアップロードされている
- [ ] アーティファクトの candidate JSON に `requested_mode=live` が含まれている
- [ ] アーティファクトの candidate JSON に `result_mode=posted` が含まれている
- [ ] `post_result_file` が存在する
- [ ] run summary に "Posted tweet" 行が表示されている
- [ ] Twitter/X 上で実際にツイートが投稿されている

### 2.5 ロールバック

- ツイートが不適切だった場合: Twitter/X UI または twitter-cli で手動削除
- `config/accounts.yaml` の `dry_run: true` はそのまま — schedule cron は引き続き dry_run で動作
- state キャッシュが更新されるため、同じ候補が再投稿されることはない

---

## Test strategy（RED → GREEN → REFACTOR）

### RED: 失敗するテストを書く

1. `test_main_does_not_fetch_my_followers` を追加
   - `fetch_usernames` のモックで `"followers"` + auth_username の呼び出しがないことをアサート
   - 現状: followback 用に呼ばれるので **FAIL**

2. `test_main_summary_has_no_followback_fields` を追加
   - サマリ dict に `followback_candidates`, `followed_back_count`, `followed_back_usernames` が存在しないことをアサート
   - 現状: これらのフィールドが出力されるので **FAIL**

3. `test_main_only_new_follows_flow` を追加
   - `record_follow` 呼び出しの `follow_type` が全て `"new_follow"` であることをアサート
   - 現状: followback 候補には `"followback"` が渡されるので **FAIL**

### GREEN: 最小限の変更でテストを通す

1. `auto_follow.py` から followback 関連コードを削除
2. `main()` を簡略化
3. サマリから followback フィールドを除去
4. 全テスト PASS を確認

### REFACTOR: 整理

1. 不要になったインポート・変数の除去
2. `FollowbackTests` クラスの削除
3. ワークフロー YAML のサマリステップ整理
4. コメントの更新（Phase 番号のリナンバリング）

## Validation commands

```bash
# 1. 全テスト実行
python -m unittest discover -s tests -v

# 2. auto_follow 関連テストのみ
python -m unittest tests.test_auto_follow -v

# 3. auto_follow.py の構文チェック
python -c "import py_compile; py_compile.compile('python/auto_follow.py', doraise=True)"

# 4. followback 残存チェック（auto_follow 関連ファイルのみ）
rg "followback" python/auto_follow.py tests/test_auto_follow.py README.md .github/workflows/auto_follow.yml

# 5. auto_unfollow.py が壊れていないか確認
python -c "import sys; sys.path.insert(0, 'python'); from auto_unfollow import main"

# 6. auto_follow workflow YAML 検証
python - <<'PY'
from pathlib import Path
import yaml
yaml.safe_load(Path('.github/workflows/auto_follow.yml').read_text(encoding='utf-8'))
print('OK')
PY

# 7. post_pic ワークフロー実行結果確認
gh run list --workflow=post_pic.yml --limit 3
```

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| followback 削除で既存フォロワーへの対応が停止 | 低 — followback は優先フォローであり、候補が target followers に含まれていれば通常フローでフォローされる | 設計意図通り |
| `build_active_followed_username_set` を他で使用 | 低 — grep で確認済み、`auto_unfollow.py` は未使用 | 削除前に最終確認 |
| post_pic ライブ実行で不適切なツイート | 中 — copilot_cli サマリが不適切な内容を生成する可能性 | 投稿後すぐに内容を確認し、必要なら手動削除 |
| posting window 外で dispatch しても skip される | 低 — posting window ステップが `should_run=false` を出力 | JST の投稿ウィンドウ内で実行する |
| state キャッシュの不整合 | 低 — state スキーマに変更なし | 既存エントリはそのまま保持 |
| post_pic live 実行で具体的障害が出る | 中 — その場で実装変更へ広げると調査が雑になる | 実行結果を保存して止め、別PLANで原因切り分けする |

---

## Out of scope

- `auto_unfollow.py` の変更
- `follow_state.json` の既存エントリの `follow_type: "followback"` のマイグレーション
- `config/accounts.yaml` の `pic.dry_run` 値の変更（dispatch override で制御）
- 新しい followback ロジックの再設計・再実装
- `record_follow()` の `follow_type` パラメータの削除（汎用パラメータとして保持）
- `post_pic` live 実行で障害が出た場合のその場での再設計・横展開修正

---

## Checkbox task breakdown

### Task 1: Remove followback-priority

#### RED（失敗テスト作成）

- [ ] `test_auto_follow.py` に `test_main_does_not_fetch_my_followers` を追加
- [ ] `test_auto_follow.py` に `test_main_summary_has_no_followback_fields` を追加
- [ ] `test_auto_follow.py` に `test_main_only_new_follows_flow` を追加
- [ ] `python -m unittest tests.test_auto_follow -v` で3つの新テストが FAIL することを確認

#### GREEN（最小限の実装）

- [ ] `auto_follow.py`: `evaluate_followback_candidate()` 関数を削除（L260-276）
- [ ] `auto_follow.py`: `collect_followback_usernames()` 関数を削除（L279-289）
- [ ] `auto_follow.py`: `build_active_followed_username_set()` 関数を削除（L130-141）
- [ ] `auto_follow.py` `main()`: `active_followed_usernames = build_active_followed_username_set(...)` 行を削除
- [ ] `auto_follow.py` `main()`: `my_follower_usernames = fetch_usernames(...)` 行を削除（L355-357）
- [ ] `auto_follow.py` `main()`: Phase 1 コメントと followback_pool/followback_candidates 構築を削除（L378-385）
- [ ] `auto_follow.py` `main()`: `followed_back` リストと `attempted_followback_usernames` を削除
- [ ] `auto_follow.py` `main()`: Phase 2 ループ全体を削除（L391-422）
- [ ] `auto_follow.py` `main()`: `_total_followed()` を `len(followed_new)` ベースに変更
- [ ] `auto_follow.py` `main()`: Phase 3 の `attempted_followback_usernames` ガードを削除（L435-436）
- [ ] `auto_follow.py` `main()`: `remaining_slots` を `target_follow_count - len(followed_new)` に変更
- [ ] `auto_follow.py` `main()`: `followed = followed_back + followed_new` を `followed = followed_new` に変更
- [ ] `auto_follow.py` `main()`: サマリから `followback_candidates`, `followed_back_count`, `followed_back_usernames` を削除
- [ ] `README.md`: auto_follow の説明から followback 優先記述を削除
- [ ] `python -m unittest tests.test_auto_follow -v` で新テスト3つが PASS することを確認

#### REFACTOR（整理）

- [ ] `test_auto_follow.py`: `FollowbackTests` クラス全体を削除（ただし `test_record_follow_defaults_to_new_follow_type` は `AutoFollowTests` クラスに移動）
- [ ] `test_auto_follow.py`: インポートから `collect_followback_usernames`, `evaluate_followback_candidate`, `build_active_followed_username_set` を削除
- [ ] `auto_follow.py`: Phase コメントのリナンバリング（Phase 1: 候補評価、Phase 2: フォロー実行）
- [ ] `.github/workflows/auto_follow.yml`: サマリステップから followback フィールド3行を削除
- [ ] `rg "followback" python/auto_follow.py tests/test_auto_follow.py README.md .github/workflows/auto_follow.yml` で残存参照がないことを確認（`tests/test_auto_unfollow.py` のテスト名は対象外）
- [ ] `python -m unittest discover -s tests -v` で全テスト PASS を確認
- [ ] `.github/workflows/auto_follow.yml` の YAML が安全に parse できることを確認

### Task 2: Test-run post_pic live

- [ ] posting window 内の時間であることを確認
- [ ] `gh workflow run post_pic.yml -f dry_run=false` を実行
- [ ] `gh run list --workflow=post_pic.yml --limit 3` で run ID を取得
- [ ] `gh run watch <RUN_ID>` で完了を待機
- [ ] `gh run view <RUN_ID>` で success を確認
- [ ] アーティファクトをダウンロードして投稿データを確認（`requested_mode=live`, `result_mode=posted`, `post_result_file` 存在、tweet ID / URL を含む）
- [ ] run summary に `Posted tweet` 行が正しく表示されていることを確認
- [ ] `Save post state` ステップ成功を確認
- [ ] Twitter/X 上でツイートが投稿されていることを確認
- [ ] 問題があれば手動でツイート削除
- [ ] 実投稿が失敗した場合はログと artifact を保存し、別PLANで原因切り分けする

### 完了処理

- [ ] 本計画を `docs/exec-plans/completed/` に移動
