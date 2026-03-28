# Harness improvements plan

## 問題と方針

ハーネスエンジニアリング観点のレビュー結果を踏まえ、改善候補を優先順位付きで整理し、もっともレバレッジの高い項目から実装する。  
最初の着手対象は、既存のテスト・構文チェック・YAML 検証を GitHub Actions 上で自動実行する CI 品質ゲートの追加とする。  
CI の検証対象は固定ファイル列挙ではなく、`scripts/` 配下の `.sh` と `scripts/lib/` 配下の `.py` を網羅する形で定義し、ローカル venv 固定パスに依存しないコマンドで実行する。

## 変更・削除・作成するファイル

- 作成予定: `.github/workflows/ci.yml`
- 変更予定: `README.md`
- 変更予定: `docs/RUNBOOK.md`
- 作成予定: `/home/fpxszk/.copilot/session-state/53d2c2ad-d5e4-46a3-8fbc-c41f8c8f08f9/plan.md`
- 削除予定: なし

## 優先順位付きアクションプラン

1. **CI 品質ゲート追加**
   - `push` / `pull_request` で既存テストと静的検証を自動実行する
   - ハーネスの再現性・安全性・変更検出力を上げる
2. **投稿要約 evaluator 追加**
   - AI 要約の長さ・リンク・禁則・空文字などを検証し、危険な出力を投稿前に止める
3. **失敗通知の改善**
   - workflow 失敗時の原因と再実行導線を summary / artifact でさらに明示する
4. **投稿結果のフィードバックループ**
   - 投稿後メトリクスを集めて source / score の改善に戻す

## 実施内容と影響範囲

- まず CI workflow を追加し、既存の `unittest`、`bash -n`、`py_compile`、YAML `safe_load` を自動化する
- CI では `python3` ベースで検証し、`python/.venv/bin/python` のようなローカル専用パスには依存しない
- README / RUNBOOK に CI の存在と確認方法を反映する
- 既存の live 投稿 workflow には直接手を入れず、品質ゲートを横に足す形で安全に改善する
- 影響範囲は開発フローとドキュメントで、本番投稿ロジック自体の挙動は変えない

## 実装ステップ

- [x] 改善候補を優先順位付きで確定する
- [x] CI workflow の対象コマンドを既存運用に合わせて定義し、対象ディレクトリ全体を漏れなく検証する
- [x] `.github/workflows/ci.yml` を追加する
- [x] `README.md` と `docs/RUNBOOK.md` に CI 利用方法を追記する
- [x] ローカルでベースライン検証と変更後検証を実行する
