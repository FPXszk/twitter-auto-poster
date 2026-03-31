# 実装計画: auto_follow 対象変更と post_buz 再開状態レビュー

## 概要

`auto_follow` の対象アカウントを `@tkzwgrs` から `@suzuka_saga` へ変更する。

あわせて `post_buz` は「停止している前提」では進めず、まず現行の schedule / posting window / account 設定を事実確認したうえで、必要な場合のみ最小限の復旧変更を入れる。

`docs/exec-plans/active/` に競合する進行中計画がないことは確認済み。

## 変更・確認対象ファイル

- `.github/workflows/auto_follow.yml`
  - 実行時の `--target-username` を `suzuka_saga` に変更
- `python/auto_follow.py`
  - CLI 既定値も `suzuka_saga` に合わせるか確認し、必要なら更新
- `tests/test_auto_follow.py`
  - 既定値または引数の期待値を RED -> GREEN で更新
- `README.md`
  - `auto_follow` の対象説明と手動実行例を新アカウントに更新
- `.github/workflows/post_buz.yml`
  - schedule / posting window / dry-run 周りに復旧が必要な場合のみ変更
- `config/accounts.yaml`
  - `post_buz` の `dry_run` と関連設定を確認し、必要な場合のみ変更
- `scripts/lib/posting_window.py`
  - `post_buz` の実行時間帯に不整合があれば修正対象
- `scripts/lib/workflow_summary.py`
  - posting window 表示に不整合があれば修正対象
- `tests/test_posting_window.py`
  - posting window 変更時のみ境界テストを更新
- `tests/test_workflow_summary.py`
  - summary 表示変更時のみ期待値を更新

## 実装内容と影響範囲

### 1. auto_follow 対象変更

- GitHub Actions の `auto_follow` workflow が参照する対象ユーザーを `suzuka_saga` に差し替える
- 本番 CLI の既定値も workflow と同じ値へ揃えるか確認する
- テストと README のハードコード参照も追従させ、運用と手動実行手順の不一致をなくす

### 2. post_buz 再開状態レビュー

- `post_buz` の recent runs を確認し、schedule が本当に止まっているか、単に posting window で skip しているかを切り分ける
- `.github/workflows/post_buz.yml` の cron は現状有効に見えるため、無条件で schedule を触らない
- `config/accounts.yaml` の `buz` 設定と `dry_run` 状態、`scripts/lib/posting_window.py` の判定、`scripts/lib/workflow_summary.py` の表示整合性を確認する
- 復旧に必要な差分が見つかった場合のみ、その箇所へ限定して修正する

## 実装ステップ

- [ ] 現状確認: `auto_follow` / `post_buz` の関連ファイルと recent workflow runs を確認する
- [ ] 現状確認: `tkzwgrs` の残存参照を repo 全体で確認する
- [ ] 方針確定: `auto_follow.py` の CLI 既定値も `suzuka_saga` に揃えるかを判断する
- [ ] RED: `tests/test_auto_follow.py` に対象ユーザー変更を検知できる失敗テストを追加または更新する
- [ ] GREEN: `.github/workflows/auto_follow.yml` を `suzuka_saga` へ更新する
- [ ] GREEN: 必要なら `python/auto_follow.py` の `--target-username` 既定値を更新する
- [ ] GREEN: `README.md` の説明とコマンド例を更新する
- [ ] 現状確認: `post_buz` の schedule / posting window / dry-run 設定を事実ベースで切り分ける
- [ ] RED: `post_buz` 側の不整合が見つかった場合のみ、対応テストを失敗状態で追加または更新する
- [ ] GREEN: `post_buz` 側で必要な最小差分だけ修正する
- [ ] REFACTOR: テスト名や説明文の重複を整理し、設定とドキュメントの整合性を確認する
- [ ] 既存コマンドで回帰確認する

## RED -> GREEN -> REFACTOR 方針

### RED

- `tests/test_auto_follow.py`
  - workflow 側引数または CLI 既定値の期待値が `suzuka_saga` になることを失敗テストで固定する
- `post_buz` 側は不整合が見つかった場合のみ対象テストを更新する
  - 例: `tests/test_posting_window.py` の境界条件
  - 例: `tests/test_workflow_summary.py` の posting window 表示

### GREEN

- `auto_follow` は対象アカウント変更に必要な最小限の本番コード・workflow・README 更新でテストを通す
- `post_buz` は「本当に必要な復旧差分」のみ入れる

### REFACTOR

- テスト名、README 文言、workflow / CLI の既定値の整合性を整理する
- 変更不要と判断した `post_buz` 領域には手を広げない

## 検証コマンド

```bash
python/.venv/bin/python -m unittest discover -s tests
python/.venv/bin/python -m unittest tests.test_auto_follow
python/.venv/bin/python -m py_compile python/auto_follow.py
python3 - <<'PY'
from pathlib import Path
import yaml
for path in [Path('.github/workflows/auto_follow.yml'), Path('.github/workflows/post_buz.yml'), Path('config/accounts.yaml')]:
    yaml.safe_load(path.read_text(encoding='utf-8'))
print('OK')
PY
```

`post_buz` にコード変更が入った場合は、対象テストと `py_compile` 対象を追加で実行する。

## Out of Scope

- `auto_unfollow` ロジック変更
- `post_buz` のソースアカウント入替や選定ロジック変更
- Secret 更新
- 新しい CI / カバレッジ基盤の導入
- 必要性が確認できない `post_buz` の大規模変更

## リスクと確認事項

- `auto_follow` の対象変更により、フォロー候補の傾向が変わる
- `config/follow_state.json` の既存履歴により、初回実行の候補数が想定とずれる可能性がある
- `post_buz` は現時点で schedule run が見えているため、誤って不要な変更を入れると逆に不安定化する
- `dry_run` が `false` の状態で復旧変更を入れると、マージ後すぐに実投稿が再開される可能性がある
